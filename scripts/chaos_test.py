"""
Chaos testing for the solar forecast data contract.
Injects known-bad records to measure how well the validation catches them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract import MonthlyForecastRecord


# === Chaos scenarios: each one is a known-bad record that SHOULD fail validation ===
chaos_scenarios = [
    {
        "name": "Negative power (sensor glitch)",
        "record": {"month": "Jan", "ac_power_kwh": -150.0, "solar_radiation": 5.0},
    },
    {
        "name": "Power far exceeding system capacity",
        "record": {"month": "Feb", "ac_power_kwh": 99999.0, "solar_radiation": 5.0},
    },
    {
        "name": "Invalid month string",
        "record": {"month": "Smarch", "ac_power_kwh": 500.0, "solar_radiation": 5.0},
    },
    {
        "name": "Radiation above physical maximum",
        "record": {"month": "Mar", "ac_power_kwh": 500.0, "solar_radiation": 45.0},
    },
    {
        "name": "Negative radiation",
        "record": {"month": "Apr", "ac_power_kwh": 500.0, "solar_radiation": -2.0},
    },
    {
        "name": "Wrong data type (string instead of number)",
        "record": {"month": "May", "ac_power_kwh": "error", "solar_radiation": 5.0},
    },
]

# === A few known-good records to confirm the contract doesn't over-reject ===
good_scenarios = [
    {"name": "Normal January reading", "record": {"month": "Jan", "ac_power_kwh": 514.68, "solar_radiation": 5.64}},
    {"name": "Normal June reading", "record": {"month": "Jun", "ac_power_kwh": 394.93, "solar_radiation": 4.49}},
]


def run_chaos_test():
    print("=" * 60)
    print("CHAOS TEST: Injecting bad records into the data contract")
    print("=" * 60)

    caught = 0
    missed = []
    for scenario in chaos_scenarios:
        try:
            MonthlyForecastRecord(**scenario["record"])
            missed.append(scenario["name"])
            print(f"[MISSED]  {scenario['name']} — bad record was NOT caught!")
        except Exception as e:
            caught += 1
            print(f"[CAUGHT]  {scenario['name']}")

    print("\n" + "-" * 60)
    print("SANITY CHECK: Good records should NOT be rejected")
    print("-" * 60)
    false_positives = 0
    for scenario in good_scenarios:
        try:
            MonthlyForecastRecord(**scenario["record"])
            print(f"[PASS]    {scenario['name']} — correctly accepted")
        except Exception as e:
            false_positives += 1
            print(f"[FALSE POSITIVE] {scenario['name']} — wrongly rejected: {e}")

    total = len(chaos_scenarios)
    detection_rate = (caught / total) * 100

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Bad records injected:     {total}")
    print(f"Caught by data contract:  {caught}")
    print(f"Missed (slipped through): {len(missed)}")
    print(f"Detection rate:           {detection_rate:.1f}%")
    print(f"False positives on good data: {false_positives}")

    if missed:
        print(f"\nScenarios that need stronger validation rules: {missed}")


if __name__ == "__main__":
    run_chaos_test()