
import xml.etree.ElementTree as ET
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def load_trips(filename):
    path = RESULTS / filename

    print(f"Loading: {path}")

    root = ET.parse(path).getroot()

    return {
        trip.get("id"): trip.attrib
        for trip in root.iter("tripinfo")
    }


def completed(trip):
    return float(trip.get("arrival", "-1")) >= 0


fixed = load_trips("fixed_3x_tripinfo.xml")
adaptive = load_trips("adaptive_3x_tripinfo.xml")

fixed_completed = {
    vid for vid, trip in fixed.items()
    if completed(trip)
}

adaptive_completed = {
    vid for vid, trip in adaptive.items()
    if completed(trip)
}

common = sorted(fixed_completed & adaptive_completed)

print("\n--- NAIROBI 3X TRAFFIC COMPARISON ---")
print("Fixed completed:", len(fixed_completed))
print("Adaptive completed:", len(adaptive_completed))
print("Completed in both:", len(common))

for metric in ("duration", "waitingTime", "timeLoss"):
    if not common:
        break

    fixed_avg = mean(
        float(fixed[vid][metric]) for vid in common
    )

    adaptive_avg = mean(
        float(adaptive[vid][metric]) for vid in common
    )

    difference = adaptive_avg - fixed_avg

    percent = (
        100 * difference / fixed_avg
        if fixed_avg else 0
    )

    print(f"\n{metric}")
    print(f"Fixed-time: {fixed_avg:.2f}s")
    print(f"Adaptive: {adaptive_avg:.2f}s")
    print(f"Difference: {difference:+.2f}s ({percent:+.2f}%)")

if common:
    improved = sum(
        float(adaptive[vid]["duration"])
        < float(fixed[vid]["duration"])
        for vid in common
    )

    print(f"\nFaster journeys: {improved}/{len(common)}")

print("\n--- THROUGHPUT COMPARISON ---")
print("Fixed completed:", len(fixed_completed))
print("Adaptive completed:", len(adaptive_completed))
print(
    "Difference:",
    len(adaptive_completed) - len(fixed_completed)
)
