
import csv
from pathlib import Path

import traci


# Project configuration
ROOT = Path(__file__).resolve().parents[1]

CONFIG = ROOT / "2026-11-03-16-39-48" / "osm.sumocfg"

RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

OUTPUT = RESULTS / "adaptive_3x_metrics.csv"
TRIPINFO = RESULTS / "adaptive_3x_tripinfo.xml"

DURATION = 900
TRAFFIC_SCALE = 3
RANDOM_SEED = 42

# Adaptive controller parameters
EXTENSION = 5.0
MAX_EXTRA_GREEN = 15.0
MIN_GREEN_QUEUE = 2


def get_queues(light_id, lanes):
    """
    Count stopped vehicles on green and red approaches.
    """

    state = traci.trafficlight.getRedYellowGreenState(
        light_id
    )

    green_lanes = {
        lane
        for lane, signal in zip(lanes, state)
        if signal in ("G", "g")
    }

    red_lanes = {
        lane
        for lane, signal in zip(lanes, state)
        if signal == "r"
    } - green_lanes

    green_queue = sum(
        traci.lane.getLastStepHaltingNumber(lane)
        for lane in green_lanes
    )

    red_queue = sum(
        traci.lane.getLastStepHaltingNumber(lane)
        for lane in red_lanes
    )

    return green_queue, red_queue, state


def run_simulation():

    print("\n--- NAIROBI ADAPTIVE CONTROLLER ---")

    traci.start([
        "sumo",
        "-c", str(CONFIG),
        "--begin", "0",
        "--end", str(DURATION),
        "--seed", str(RANDOM_SEED),
        "--scale", str(TRAFFIC_SCALE),
        "--no-step-log", "true",
        "--duration-log.statistics", "true",
        "--tripinfo-output", str(TRIPINFO),
        "--tripinfo-output.write-unfinished", "true",
    ])

    try:
        # Detect all traffic-light controllers
        lights = traci.trafficlight.getIDList()

        # Cache the lanes controlled by each signal
        controlled_lanes = {
            light: traci.trafficlight.getControlledLanes(light)
            for light in lights
        }

        print(f"Traffic lights: {len(lights)}")
        print(f"Traffic multiplier: {TRAFFIC_SCALE}x")
        print(f"Simulation duration: {DURATION}s")

        metrics = []

        extensions = 0
        total_arrived = 0
        total_departed = 0
        total_teleports = 0

        for second in range(DURATION):

            # Advance simulation
            traci.simulationStep()

            now = traci.simulation.getTime()

            # Evaluate every traffic-light controller
            for light in lights:

                green_q, red_q, state = get_queues(
                    light,
                    controlled_lanes[light]
                )

                # Preserve yellow transition phases
                if "y" in state or "Y" in state:
                    continue

                # Only extend phases with a green signal
                if not any(c in "Gg" for c in state):
                    continue

                # Time remaining in the current phase
                remaining = (
                    traci.trafficlight.getNextSwitch(light)
                    - now
                )

                # Only consider extending phases nearing their end
                if not 0 < remaining <= 2:
                    continue

                elapsed = (
                    traci.trafficlight.getSpentDuration(light)
                )

                nominal = (
                    traci.trafficlight.getPhaseDuration(light)
                )

                # Cap additional green time
                max_remaining = (
                    nominal + MAX_EXTRA_GREEN - elapsed
                )

                # Extend green if its approach has more queued demand
                if (
                    green_q >= MIN_GREEN_QUEUE
                    and green_q > red_q
                    and max_remaining > remaining
                ):

                    new_remaining = min(
                        remaining + EXTENSION,
                        max_remaining
                    )

                    if new_remaining > remaining + 0.01:

                        traci.trafficlight.setPhaseDuration(
                            light,
                            new_remaining
                        )

                        extensions += 1

            # Collect network-wide statistics
            vehicles = traci.vehicle.getIDList()

            stopped = sum(
                traci.vehicle.getSpeed(vehicle) < 0.1
                for vehicle in vehicles
            )

            arrived = traci.simulation.getArrivedNumber()
            departed = traci.simulation.getDepartedNumber()
            teleports = traci.simulation.getStartingTeleportNumber()

            total_arrived += arrived
            total_departed += departed
            total_teleports += teleports

            metrics.append({
                "time": now,
                "active_vehicles": len(vehicles),
                "stopped_vehicles": stopped,
                "arrived_vehicles": total_arrived,
                "departed_vehicles": total_departed,
                "teleports": total_teleports,
                "green_extensions": extensions,
            })

            if (second + 1) % 60 == 0:
                print(
                    f"Time: {second + 1}s | "
                    f"Active: {len(vehicles)} | "
                    f"Stopped: {stopped} | "
                    f"Arrived: {total_arrived}"
                )

        # Save metrics
        with OUTPUT.open("w", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=metrics[0].keys()
            )

            writer.writeheader()
            writer.writerows(metrics)

        average_stopped = sum(
            row["stopped_vehicles"]
            for row in metrics
        ) / len(metrics)

        print("\n--- ADAPTIVE RESULTS ---")
        print(f"Traffic lights: {len(lights)}")
        print(f"Green extensions: {extensions}")
        print(f"Vehicles departed: {total_departed}")
        print(f"Vehicles completed: {total_arrived}")
        print(f"Average stopped vehicles: {average_stopped:.2f}")
        print(f"Total teleports: {total_teleports}")
        print(f"Vehicles still active: {len(vehicles)}")

        print(f"\nCSV saved to: {OUTPUT}")
        print(f"Trip information saved to: {TRIPINFO}")

    finally:
        traci.close()


if __name__ == "__main__":
    run_simulation()
