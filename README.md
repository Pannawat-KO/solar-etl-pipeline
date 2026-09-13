# Solar Data ETL Pipeline

Automated daily pipeline that pulls solar generation forecast data from the NREL PVWatts API, stores it locally, and syncs it to cloud storage — running unattended via Windows Task Scheduler.

## Problem

Manually pulling solar forecast data for analysis meant repeated one-off API calls and no consistent historical record. This pipeline automates that process end-to-end and adds a cloud storage layer so data isn't trapped on a single machine.

## Architecture

```
NREL PVWatts API
      │
      ▼
  extract.py ── Data Contract validation (Pydantic) ── Quality Scorecard
      │                                                      │
      ▼                                                      ▼
  SQLite (local, bangkok_monthly_forecast table)      quality_log.json
      │
      ├──────────────────────►  JSON export (solar_forecast.json)
      │
      └──────────────────────►  CSV export ──► AWS S3 (solar_forecast/YYYY-MM-DD.csv,
                                                        quality_log.json)

Triggered daily by Windows Task Scheduler → run_pipeline.bat → logged to log.txt
```

## What it does

1. **Extract** — Calls the NREL PVWatts v8 API for a fixed location (Bangkok, 4kW system) and pulls monthly AC power output and solar radiation forecasts.
2. **Transform** — Loads the API response into a pandas DataFrame (`month`, `ac_power_kwh`, `solar_radiation`).
3. **Validate** — Checks every record against a data contract (see below) before it's allowed into storage.
4. **Score** — Grades the day's data quality (A-F) based on how many records passed, and appends it to a running history log.
5. **Load (local)** — Writes the DataFrame to a local SQLite database (`solar_forecast.db`) and exports a JSON snapshot.
6. **Load (cloud)** — Exports the same data as CSV and uploads it to an AWS S3 bucket, keyed by date (`solar_forecast/2026-09-11.csv`), along with the quality history log.
7. **Automate** — A `.bat` script runs the whole pipeline daily via Task Scheduler, redirecting all output to `log.txt` for later debugging.

## Data Contract & Quality Scorecard

Before any record reaches SQLite or S3, it's checked against a **data contract** (defined with Pydantic) that encodes what a physically plausible reading looks like:
- `month` must be a valid three-letter abbreviation
- `ac_power_kwh` must be non-negative and under a sane ceiling for a 4kW system
- `solar_radiation` must fall within a physically realistic range (0-10 kWh/m²/day)

Records that fail are logged with the specific reason, not silently dropped or silently accepted — this is the difference between catching a bad reading immediately versus finding it the way the [Solar Generation Analysis](../solar-generation-analysis) project did (tracing a 12x anomaly back after the fact).

**Chaos testing** (`chaos_test.py`) verifies the contract actually works by injecting six known-bad record types — negative power, out-of-range values, wrong data types, an invalid month string — and checking that each one is caught without rejecting valid data. Current result: **100% detection rate, 0 false positives** on the tested scenarios.

**Unit tests** (`test_data_contract.py`, pytest) cover the contract more formally: boundary values, type validation, integration with `validate_records()`, and the quality-scoring logic — **15 tests, all passing**.

Each run also computes a **quality score** (% of records that passed) and letter grade for the day, appended to `quality_log.json`. This log is synced to S3 alongside the forecast data and consumed by the [Solar Forecast App](../solar-forecast-app)'s Data Quality tab, so a data quality dip is visible on a chart rather than buried in a log file.

**Weekly reporting** (`weekly_quality_report.py`) aggregates the last 7 days of `quality_log.json` into a summary — average score, overall pass rate, grade distribution, best/worst day — and exports it as a CSV, the kind of rollup a non-technical stakeholder could read without touching a log file.

**Email alerting** — if a day's grade drops below B, the pipeline sends an email alert (via Gmail SMTP) summarizing the score and the specific records that failed, instead of relying on someone to notice a bad day by checking `quality_log.json` manually.

## Why AWS S3

The pipeline originally only wrote to a local SQLite file — if the machine failed, the data was gone, and it wasn't accessible from anywhere else. Adding an S3 sync means:
- Daily snapshots are durable and timestamped, giving a queryable history instead of just the latest state
- Data is accessible outside the local machine
- It mirrors how cloud data pipelines are structured in production, beyond just working against a local database

Uploads are wrapped in a try/except block so that a network or credentials failure doesn't crash the whole pipeline — it logs the error and the local SQLite write still succeeds.

## Fixes along the way

- **Silent failures on schedule** — Task Scheduler was invoking a different Python installation than the one `pip install` targeted, so `dotenv` (and later `boto3`, `pydantic`) wasn't found when the job ran unattended even though it worked fine run manually. Fixed by pointing the scheduled task at the exact Python executable path used for installation.

## Tech stack

Python · pandas · Pydantic · pytest · SQLite · AWS S3 (boto3) · Gmail SMTP · Windows Task Scheduler · REST APIs

## Setup

1. Install dependencies: `pip install requests pandas python-dotenv boto3 pydantic pytest`
2. Create a `.env` file with:
   ```
   NREL_API_KEY=your_key_here
   ALERT_EMAIL_FROM=your_email@gmail.com
   ALERT_EMAIL_TO=your_email@gmail.com
   ALERT_EMAIL_APP_PASSWORD=your_gmail_app_password
   ```
   (the alert email settings are optional — the pipeline skips alerting if they're not configured)
3. Configure AWS credentials: `aws configure` (requires an IAM user with S3 write access)
4. Run manually: `python extract.py`, or schedule via `run_pipeline.bat`
5. Run the chaos test independently: `python scripts/chaos_test.py`
6. Run the unit tests: `pytest tests/test_data_contract.py -v`
7. Generate a weekly summary: `python weekly_quality_report.py`

## Sample output

| month | ac_power_kwh | solar_radiation |
|-------|-------------|------------------|
| Jan   | 514.69      | 5.64             |
| Feb   | 502.17      | 6.26             |
| ...   | ...         | ...              |
