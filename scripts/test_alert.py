"""Standalone script to verify the email alert actually fires and sends correctly.

Not a pytest test — run it directly (`python scripts/test_alert.py`) since it
sends a real email. Guarded behind __main__ so pytest collection doesn't
trigger it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from extract import send_quality_alert

if __name__ == "__main__":
    load_dotenv()

    fake_failures = [
        {"row": {"month": "Jun", "ac_power_kwh": -999.0, "solar_radiation": 5.0}, "error": "ac_power_kwh cannot be negative, got -999.0"}
    ]

    send_quality_alert(score=75.0, grade="C", failures=fake_failures, date_str="2026-09-13")
