import requests
import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

import pandas as pd
import sqlite3
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

NREL_URL = "https://developer.nrel.gov/api/pvwatts/v8.json"
BUCKET_NAME = "solar-forecast-data-phuwanet"
DATA_DIR = "data"


class MonthlyForecastRecord(BaseModel):
    """Data contract: defines what a valid monthly solar forecast record looks like."""
    month: str
    ac_power_kwh: float
    solar_radiation: float

    @field_validator('month')
    @classmethod
    def month_must_be_valid(cls, v):
        valid_months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        if v not in valid_months:
            raise ValueError(f"'{v}' is not a valid month abbreviation")
        return v

    @field_validator('ac_power_kwh')
    @classmethod
    def power_must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError(f"ac_power_kwh cannot be negative, got {v}")
        if v > 2000:
            raise ValueError(f"ac_power_kwh {v} exceeds plausible maximum for this system size")
        return v

    @field_validator('solar_radiation')
    @classmethod
    def radiation_must_be_in_range(cls, v):
        if not (0 <= v <= 10):
            raise ValueError(f"solar_radiation {v} outside plausible range (0-10)")
        return v


def validate_records(df):
    """Validate each row against the data contract. Returns (valid_records, failures)."""
    valid_records = []
    failures = []
    for _, row in df.iterrows():
        try:
            record = MonthlyForecastRecord(
                month=row['month'],
                ac_power_kwh=row['ac_power_kwh'],
                solar_radiation=row['solar_radiation']
            )
            valid_records.append(record)
        except Exception as e:
            failures.append({'row': row.to_dict(), 'error': str(e)})
    return valid_records, failures


def compute_quality_score(valid_records, failures, total):
    """Grade the day's data based on what fraction of records passed the contract."""
    completeness = len(valid_records) / total if total else 0
    score = completeness * 100
    if score == 100:
        grade = 'A'
    elif score >= 90:
        grade = 'B'
    elif score >= 75:
        grade = 'C'
    elif score >= 50:
        grade = 'D'
    else:
        grade = 'F'
    return score, grade


def update_quality_log(score, grade, valid_count, total_count, failed_count, log_path=os.path.join(DATA_DIR, "quality_log.json")):
    """Append today's score to the running quality history, replacing any existing entry for today."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    entry = {
        "date": today_str,
        "score": round(score, 1),
        "grade": grade,
        "valid_count": valid_count,
        "total_count": total_count,
        "failed_count": failed_count,
    }

    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            quality_log = json.load(f)
    else:
        quality_log = []

    quality_log = [e for e in quality_log if e["date"] != today_str]
    quality_log.append(entry)
    quality_log.sort(key=lambda e: e["date"])

    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(quality_log, f, indent=2)

    return quality_log


def send_quality_alert(score, grade, failures, date_str):
    """Send an email alert when the daily quality grade drops below B."""
    sender = os.getenv("ALERT_EMAIL_FROM")
    recipient = os.getenv("ALERT_EMAIL_TO")
    app_password = os.getenv("ALERT_EMAIL_APP_PASSWORD")

    if not all([sender, recipient, app_password]):
        print("Alert email skipped: ALERT_EMAIL_* not configured in .env")
        return

    failure_lines = "\n".join(
        f"  - {f['row']} -> {f['error']}" for f in failures
    ) or "  (no individual failures logged)"

    body = (
        f"Solar Forecast Pipeline — Data Quality Alert\n\n"
        f"Date: {date_str}\n"
        f"Score: {score:.1f}%\n"
        f"Grade: {grade}\n\n"
        f"Failed records:\n{failure_lines}\n"
    )

    msg = MIMEText(body)
    msg["Subject"] = f"[ALERT] Solar Pipeline Data Quality: Grade {grade} ({score:.1f}%)"
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.send_message(msg)
        print(f"Alert email sent to {recipient}")
    except Exception as e:
        print(f"ERROR: Failed to send alert email — {e}")


MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def fetch_forecast_data():
    """Call the NREL PVWatts API and return the parsed JSON response."""
    load_dotenv()
    api_key = os.getenv("NREL_API_KEY")
    params = {
        "api_key": api_key,
        "lat": 13.7563,
        "lon": 100.5018,
        "system_capacity": 4,
        "module_type": 0,
        "losses": 14,
        "array_type": 1,
        "tilt": 20,
        "azimuth": 180
    }

    response = requests.get(NREL_URL, params=params)
    data = response.json()
    if "errors" in data:
        raise RuntimeError(f"NREL API returned an error: {data['errors']}")
    return data


def upload_to_s3(csv_filename, log_path=os.path.join(DATA_DIR, "quality_log.json")):
    """Upload the day's CSV export and the running quality log to S3."""
    try:
        s3 = boto3.client("s3")
        today_str = datetime.now().strftime("%Y-%m-%d")
        s3_key = f"solar_forecast/{today_str}.csv"
        s3.upload_file(csv_filename, BUCKET_NAME, s3_key)
        print(f"อัปโหลดขึ้น S3 สำเร็จ: s3://{BUCKET_NAME}/{s3_key}")
    except NoCredentialsError:
        print("ERROR: ไม่พบ AWS credentials — เช็ค aws configure อีกครั้ง")
        return
    except ClientError as e:
        print(f"ERROR: อัปโหลด S3 ไม่สำเร็จ — {e}")
        return

    try:
        s3.upload_file(log_path, BUCKET_NAME, "quality_log.json")
        print("อัปโหลด quality_log.json ขึ้น S3 สำเร็จ")
    except (NoCredentialsError, ClientError) as e:
        print(f"ERROR: อัปโหลด quality_log.json ไม่สำเร็จ — {e}")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    data = fetch_forecast_data()
    print(data)

    df = pd.DataFrame({
        'month': MONTHS,
        'ac_power_kwh': data['outputs']['ac_monthly'],
        'solar_radiation': data['outputs']['solrad_monthly']
    })
    print(df)

    # === Data Contract Validation ===
    valid_records, failures = validate_records(df)
    print(f"\nValidation: {len(valid_records)}/{len(df)} records passed the data contract")
    if failures:
        print(f"WARNING: {len(failures)} record(s) failed validation:")
        for f in failures:
            print(f"  - {f['row']} -> {f['error']}")

    # === Quality Scorecard ===
    score, grade = compute_quality_score(valid_records, failures, len(df))
    print(f"Data Quality Score: {score:.1f}% (Grade {grade})")
    quality_log = update_quality_log(score, grade, len(valid_records), len(df), len(failures))
    print(f"Quality log updated — {len(quality_log)} day(s) of history tracked")

    # === Email Alert (only fires if grade drops below B) ===
    if grade not in ("A", "B"):
        send_quality_alert(score, grade, failures, datetime.now().strftime("%Y-%m-%d"))
    else:
        print(f"No alert needed — grade {grade} is within acceptable range")

    # === Load: local SQLite + JSON ===
    conn = sqlite3.connect(os.path.join(DATA_DIR, 'solar_forecast.db'))
    df.to_sql('bangkok_monthly_forecast', conn, if_exists='replace', index=False)
    conn.close()
    print("บันทึกข้อมูลลง database เรียบร้อย")

    df.to_json(os.path.join(DATA_DIR, 'solar_forecast.json'), orient='records')
    print("Export เป็น JSON เรียบร้อย")

    # === Load: CSV + Upload to S3 ===
    csv_filename = os.path.join(DATA_DIR, "solar_forecast.csv")
    df.to_csv(csv_filename, index=False)
    print(f"Export เป็น {csv_filename} เรียบร้อย")

    upload_to_s3(csv_filename)


if __name__ == "__main__":
    main()