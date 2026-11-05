
import xml.etree.ElementTree as ET
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def load_trips(filename):
    path = RESULTS / filename

    if not path.exists():
        raise FileNotFoundError(f"Missing results file: {path}")

    print(f"Loading: {path}")

    root = ET.parse(path).getroot()

    return {
        trip.get("id"): trip.attrib
        for trip in root.iter("tripinfo")
    }


def completed(trip):
    return float(trip.get("arrival", "-1")) >= 0


# Compare Fixed-Time against Adaptive V2
fixed = load_trips("fixed_3x_tripinfo.xml")
adaptive = load_trips("adaptive_v2_3x_tripinfo.xml")

fixed_completed = {
    vid for vid, trip in fixed.items()
    if completed(trip)
}

adaptive_completed = {
    vid for vid, trip in adaptive.items()
    if completed(trip)
}

common = sorted(fixed_completed & adaptive_completed)

print("\n--- NAIROBI 3X TRAFFIC: FIXED VS V2 ---")

print("Fixed-time completed:", len(fixed_completed))
print("Adaptive V2 completed:", len(adaptive_completed))
print("Completed in both:", len(common))

print(
    "Fixed-only completions:",
    len(fixed_completed - adaptive_completed)
)

print(
    "V2-only completions:",
    len(adaptive_completed - fixed_completed)
)

# Compare identical completed journeys
for metric in ("duration", "waitingTime", "timeLoss"):

    if not common:
        break

    fixed_avg = mean(
        float(fixed[vid][metric])
        for vid in common
    )

    adaptive_avg = mean(
        float(adaptive[vid][metric])
        for vid in common
    )

    difference = adaptive_avg - fixed_avg

    percent = (
        100 * difference / fixed_avg
        if fixed_avg else 0
    )

    print(f"\n{metric}")
    print(f"Fixed-time: {fixed_avg:.2f}s")
    print(f"Adaptive V2: {adaptive_avg:.2f}s")
    print(f"Difference: {difference:+.2f}s ({percent:+.2f}%)")


if common:

    improved = sum(
        float(adaptive[vid]["duration"])
        < float(fixed[vid]["duration"])
        for vid in common
    )

    worsened = sum(
        float(adaptive[vid]["duration"])
        > float(fixed[vid]["duration"])
        for vid in common
    )

    unchanged = len(common) - improved - worsened

    print("\n--- INDIVIDUAL JOURNEY RESULTS ---")
    print(f"Faster journeys: {improved}/{len(common)}")
    print(f"Slower journeys: {worsened}/{len(common)}")
    print(f"Unchanged journeys: {unchanged}")
    print(f"Percentage faster: {100 * improved / len(common):.2f}%")


# Network throughput comparison
fixed_count = len(fixed_completed)
adaptive_count = len(adaptive_completed)

difference = adaptive_count - fixed_count

percentage = (
    100 * difference / fixed_count
    if fixed_count else 0
)

print("\n--- THROUGHPUT COMPARISON ---")
print(f"Fixed-time: {fixed_count}")
print(f"Adaptive V2: {adaptive_count}")
print(f"Additional completed journeys: {difference:+d}")
print(f"Throughput change: {percentage:+.2f}%")

print("\n--- COMPARISON COMPLETE ---")
