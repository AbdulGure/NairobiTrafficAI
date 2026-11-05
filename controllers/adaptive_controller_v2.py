
import csv
from pathlib import Path

import traci


# =========================================================
# NAIROBI TRAFFIC AI — ADAPTIVE CONTROLLER V2
# =========================================================

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "2026-11-03-16-39-48" / "osm.sumocfg"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

CSV_OUTPUT = RESULTS / "adaptive_v2_3x_metrics.csv"
TRIP_OUTPUT = RESULTS / "adaptive_v2_3x_tripinfo.xml"

DURATION = 900
TRAFFIC_SCALE = 3
RANDOM_SEED = 42

# Controller parameters
DECISION_INTERVAL = 5
MIN_GREEN = 12.0
MAX_EXTRA_GREEN = 10.0
GREEN_EXTENSION = 5.0

MIN_PRESSURE = 1.5
SWITCH_ADVANTAGE = 1.5
EXTEND_ADVANTAGE = 1.0

# How much downstream queues reduce pressure
DOWNSTREAM_WEIGHT = 0.5

# Small weight for approaching but non-stopped traffic
APPROACH_WEIGHT = 0.25


def is_green_phase(state):
    """Accept green phases without mixed yellow signals."""
    return (
        any(c in "Gg" for c in state)
        and not any(c in "yY" for c in state)
    )


def is_transition_phase(state):
    """Recognise yellow or all-red clearance phases."""
    has_green = any(c in "Gg" for c in state)
    has_yellow = any(c in "yY" for c in state)
    all_red = bool(state) and all(c in "rR" for c in state)

    return not has_green and (has_yellow or all_red)


def find_next_green(phases, current_index):
    """Find the next green in a simple cyclic programme."""
    for offset in range(1, len(phases)):
        index = (current_index + offset) % len(phases)

        if is_green_phase(phases[index].state):
            return index

    return None


def get_lane_data(lane, cache):
    """Retrieve each lane's measurements once per decision."""
    if lane not in cache:
        cache[lane] = {
            "halted": traci.lane.getLastStepHaltingNumber(lane),
            "vehicles": traci.lane.getLastStepVehicleNumber(lane),
            "occupancy": traci.lane.getLastStepOccupancy(lane),
        }

    return cache[lane]


def calculate_pressure(state, links, cache):
    """
    Estimate the ability of a phase to discharge traffic.

    Upstream queues increase pressure.
    Downstream queues and occupancy reduce pressure.

    Shared incoming lanes are counted once, using their
    highest estimated movement pressure.
    """

    lane_pressures = {}

    for signal_index, signal in enumerate(state):
        if signal not in "Gg":
            continue

        if signal_index >= len(links):
            continue

        for connection in links[signal_index]:
            if not connection:
                continue

            incoming, outgoing, _via = connection

            if not incoming or not outgoing:
                continue

            upstream = get_lane_data(incoming, cache)
            downstream = get_lane_data(outgoing, cache)

            approaching = max(
                0,
                upstream["vehicles"] - upstream["halted"]
            )

            demand = (
                upstream["halted"]
                + APPROACH_WEIGHT * approaching
            )

            downstream_queue = downstream["halted"]

            free_capacity = max(
                0.0,
                1.0 - downstream["occupancy"] / 100.0
            )

            pressure = max(
                0.0,
                demand - DOWNSTREAM_WEIGHT * downstream_queue
            )

            pressure *= free_capacity

            lane_pressures[incoming] = max(
                lane_pressures.get(incoming, 0.0),
                pressure
            )

    return sum(lane_pressures.values())


def load_controllers():
    """Load supported static signal plans for all junctions."""
    light_ids = traci.trafficlight.getIDList()

    controllers = {}

    for light in light_ids:
        active_program = traci.trafficlight.getProgram(light)

        logic = next(
            (
                item
                for item in traci.trafficlight.getAllProgramLogics(light)
                if item.programID == active_program
            ),
            None,
        )

        if logic is None or not logic.phases:
            continue

        # V2 supports simple static, sequential programmes.
        # Branching programmes need separate handling.
        if logic.type != 0:
            continue

        if any(phase.next for phase in logic.phases):
            continue

        controllers[light] = {
            "phases": logic.phases,
            "links": traci.trafficlight.getControlledLinks(light),
        }

    return light_ids, controllers


def optimise_intersections(controllers):
    """Evaluate every eligible junction using shared lane data."""

    now = traci.simulation.getTime()
    lane_cache = {}

    extensions = 0
    early_switches = 0

    for light, controller in controllers.items():
        phases = controller["phases"]
        links = controller["links"]

        current_index = traci.trafficlight.getPhase(light)

        if not 0 <= current_index < len(phases):
            continue

        current_phase = phases[current_index]

        if not is_green_phase(current_phase.state):
            continue

        next_green_index = find_next_green(
            phases, current_index
        )

        if next_green_index is None:
            continue

        current_pressure = calculate_pressure(
            current_phase.state, links, lane_cache
        )

        next_pressure = calculate_pressure(
            phases[next_green_index].state,
            links,
            lane_cache,
        )

        elapsed = traci.trafficlight.getSpentDuration(light)
        remaining = traci.trafficlight.getNextSwitch(light) - now

        if remaining <= 0:
            continue

        nominal_duration = current_phase.duration

        following_phase = phases[
            (current_index + 1) % len(phases)
        ]

        # -------------------------------------------------
        # Decision A: End an unproductive green early.
        #
        # Only allow this when the next phase is a clearance
        # phase, so SUMO retains its planned transitions.
        # -------------------------------------------------

        can_end_early = (
            elapsed >= MIN_GREEN
            and remaining > 1.0
            and is_transition_phase(following_phase.state)
        )

        if (
            can_end_early
            and next_pressure >= MIN_PRESSURE
            and next_pressure >
                current_pressure + SWITCH_ADVANTAGE
        ):
            traci.trafficlight.setPhaseDuration(
                light, 1.0
            )

            early_switches += 1
            continue

        # -------------------------------------------------
        # Decision B: Extend a useful green.
        #
        # Bound total phase time to its nominal duration
        # plus MAX_EXTRA_GREEN.
        # -------------------------------------------------

        max_total_green = (
            nominal_duration + MAX_EXTRA_GREEN
        )

        available_remaining = max(
            0.0,
            max_total_green - elapsed
        )

        if (
            remaining <= DECISION_INTERVAL
            and current_pressure >= MIN_PRESSURE
            and current_pressure >
                next_pressure + EXTEND_ADVANTAGE
            and available_remaining > remaining + 0.01
        ):
            new_remaining = min(
                remaining + GREEN_EXTENSION,
                available_remaining,
            )

            if new_remaining > remaining + 0.01:
                traci.trafficlight.setPhaseDuration(
                    light, new_remaining
                )

                extensions += 1

    return extensions, early_switches


def run_simulation():
    if not CONFIG.exists():
        raise FileNotFoundError(
            f"SUMO configuration not found: {CONFIG}"
        )

    print("\n--- NAIROBI ADAPTIVE CONTROLLER V2 ---")

    traci.start([
        "sumo",
        "-c", str(CONFIG),
        "--begin", "0",
        "--end", str(DURATION),
        "--seed", str(RANDOM_SEED),
        "--scale", str(TRAFFIC_SCALE),
        "--no-step-log", "true",
        "--duration-log.statistics", "true",
        "--tripinfo-output", str(TRIP_OUTPUT),
        "--tripinfo-output.write-unfinished", "true",
    ])

    try:
        lights, controllers = load_controllers()

        print(f"Detected traffic lights: {len(lights)}")
        print(f"Eligible V2 controllers: {len(controllers)}")
        print(f"Traffic multiplier: {TRAFFIC_SCALE}x")
        print(f"Simulation duration: {DURATION}s")

        if len(lights) != 103:
            raise RuntimeError(
                "Expected 103 traffic lights. "
                "Check the network configuration."
            )

        if not controllers:
            raise RuntimeError(
                "No supported static signal programmes found."
            )

        metrics = []

        total_arrived = 0
        total_departed = 0
        total_teleports = 0
        total_extensions = 0
        total_early_switches = 0

        for second in range(1, DURATION + 1):
            traci.simulationStep()

            if second % DECISION_INTERVAL == 0:
                extended, shortened = optimise_intersections(
                    controllers
                )

                total_extensions += extended
                total_early_switches += shortened

            vehicles = traci.vehicle.getIDList()

            stopped = sum(
                traci.vehicle.getSpeed(vehicle) < 0.1
                for vehicle in vehicles
            )

            total_arrived += (
                traci.simulation.getArrivedNumber()
            )

            total_departed += (
                traci.simulation.getDepartedNumber()
            )

            total_teleports += (
                traci.simulation.getStartingTeleportNumber()
            )

            metrics.append({
                "time": traci.simulation.getTime(),
                "active_vehicles": len(vehicles),
                "stopped_vehicles": stopped,
                "completed_vehicles": total_arrived,
                "departed_vehicles": total_departed,
                "teleports": total_teleports,
                "green_extensions": total_extensions,
                "early_switches": total_early_switches,
            })

            if second % 60 == 0:
                print(
                    f"{second}s | "
                    f"Active: {len(vehicles)} | "
                    f"Stopped: {stopped} | "
                    f"Completed: {total_arrived} | "
                    f"Extensions: {total_extensions} | "
                    f"Early switches: {total_early_switches}"
                )

        with CSV_OUTPUT.open("w", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=metrics[0].keys()
            )

            writer.writeheader()
            writer.writerows(metrics)

        avg_stopped = sum(
            row["stopped_vehicles"] for row in metrics
        ) / len(metrics)

        print("\n--- ADAPTIVE V2 RESULTS ---")
        print(f"Traffic lights detected: {len(lights)}")
        print(f"Eligible controllers: {len(controllers)}")
        print(f"Vehicles departed: {total_departed}")
        print(f"Vehicles completed: {total_arrived}")
        print(f"Vehicles still active: {len(vehicles)}")
        print(f"Average stopped vehicles: {avg_stopped:.2f}")
        print(f"Green extensions: {total_extensions}")
        print(f"Early phase endings: {total_early_switches}")
        print(f"Teleports: {total_teleports}")

        print(f"\nCSV saved: {CSV_OUTPUT}")
        print(f"Tripinfo saved: {TRIP_OUTPUT}")

    finally:
        traci.close()


if __name__ == "__main__":
    run_simulation()
