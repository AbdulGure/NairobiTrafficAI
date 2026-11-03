
import csv
from pathlib import Path

import traci

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "2026-11-03-16-39-48/osm.sumocfg"
OUTPUT = ROOT / "results/junction_congestion.csv"

DURATION = 900
SAMPLE_INTERVAL = 5


def analyse():
    OUTPUT.parent.mkdir(exist_ok=True)

    traci.start([
        "sumo",
        "-c", str(CONFIG),
        "--seed", "42",
        "--no-step-log", "true",
    ])

    try:
        lights = traci.trafficlight.getIDList()

        # Remove duplicate lanes from each controller.
        controlled_lanes = {
            light: list(dict.fromkeys(
                traci.trafficlight.getControlledLanes(light)
            ))
            for light in lights
        }

        queue_totals = {light: 0 for light in lights}
        peak_queues = {light: 0 for light in lights}
        samples = 0

        print(f"Analysing {len(lights)} intersections...")

        for second in range(1, DURATION + 1):
            traci.simulationStep()

            if second % SAMPLE_INTERVAL != 0:
                continue

            samples += 1

            for light in lights:
                queue = sum(
                    traci.lane.getLastStepHaltingNumber(lane)
                    for lane in controlled_lanes[light]
                )

                queue_totals[light] += queue
                peak_queues[light] = max(
                    peak_queues[light], queue
                )

        results = []

        for light in lights:
            lane_count = len(controlled_lanes[light])
            average_queue = queue_totals[light] / samples

            results.append({
                "traffic_light": light,
                "incoming_lanes": lane_count,
                "average_stopped": round(average_queue, 2),
                "peak_stopped": peak_queues[light],
                "average_per_lane": round(
                    average_queue / lane_count, 2
                ) if lane_count else 0,
            })

        results.sort(
            key=lambda r: r["average_stopped"],
            reverse=True,
        )

        with OUTPUT.open("w", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=results[0].keys()
            )
            writer.writeheader()
            writer.writerows(results)

        print("\n--- TOP 10 CONGESTED INTERSECTIONS ---")

        for i, item in enumerate(results[:10], start=1):
            print(
                f"{i}. {item['traffic_light']} | "
                f"Average stopped: {item['average_stopped']} | "
                f"Peak stopped: {item['peak_stopped']}"
            )

        print(f"\nResults saved to: {OUTPUT}")

    finally:
        traci.close()


if __name__ == "__main__":
    analyse()
