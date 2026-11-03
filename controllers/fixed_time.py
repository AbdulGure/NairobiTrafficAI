
import csv
from pathlib import Path

import traci


# Project configuration
ROOT = Path(__file__).resolve().parents[1]

CONFIG = ROOT / "2026-11-03-16-39-48" / "osm.sumocfg"

RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

OUTPUT = RESULTS / "fixed_3x_metrics.csv"
TRIPINFO = RESULTS / "fixed_3x_tripinfo.xml"

DURATION = 900
TRAFFIC_SCALE = 3
RANDOM_SEED = 42


def run_simulation():

    print("\n--- NAIROBI FIXED-TIME CONTROLLER ---")

    # Start SUMO with the existing fixed-time signal programmes
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
        lights = traci.trafficlight.getIDList()

        print(f"Traffic lights: {len(lights)}")
        print(f"Traffic multiplier: {TRAFFIC_SCALE}x")
        print(f"Simulation duration: {DURATION}s")

        metrics = []

        total_arrived = 0
        total_departed = 0
        total_teleports = 0

        for second in range(DURATION):

            # Advance SUMO by one simulation step
            traci.simulationStep()

            vehicles = traci.vehicle.getIDList()

            # Count vehicles that are stopped
            stopped = sum(
                traci.vehicle.getSpeed(vehicle) < 0.1
                for vehicle in vehicles
            )

            # Collect simulation statistics
            arrived = traci.simulation.getArrivedNumber()
            departed = traci.simulation.getDepartedNumber()
            teleports = traci.simulation.getStartingTeleportNumber()

            total_arrived += arrived
            total_departed += departed
            total_teleports += teleports

            waiting_to_depart = (
                traci.simulation.getDepartDelay()
                if hasattr(traci.simulation, "getDepartDelay")
                else 0
            )

            metrics.append({
                "time": second + 1,
                "active_vehicles": len(vehicles),
                "stopped_vehicles": stopped,
                "arrived_vehicles": total_arrived,
                "departed_vehicles": total_departed,
                "teleports": total_teleports,
            })

            if (second + 1) % 60 == 0:
                print(
                    f"Time: {second + 1}s | "
                    f"Active: {len(vehicles)} | "
                    f"Stopped: {stopped} | "
                    f"Arrived: {total_arrived}"
                )

        # Save results to CSV
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

        print("\n--- FIXED-TIME RESULTS ---")
        print(f"Traffic lights: {len(lights)}")
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
