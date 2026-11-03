
import traci

CONFIG = "2026-11-03-16-39-48/osm.sumocfg"

traci.start([
    "sumo",
    "-c", CONFIG,
    "--no-step-log", "true"
])

try:
    lights = traci.trafficlight.getIDList()

    print("\n--- NAIROBI TRAFFIC SYSTEM ---")
    print(f"Traffic lights detected: {len(lights)}")

    if lights:
        light_id = lights[0]

        print(f"First traffic light: {light_id}")
        print(
            "Current phase:",
            traci.trafficlight.getPhase(light_id)
        )
        print(
            "Signal state:",
            traci.trafficlight.getRedYellowGreenState(light_id)
        )

        print("\nAdvancing simulation by 30 seconds...")

        for _ in range(30):
            traci.simulationStep()

        print(
            "Signal state after 30 seconds:",
            traci.trafficlight.getRedYellowGreenState(light_id)
        )

finally:
    traci.close()
