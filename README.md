# Solar Data ETL Pipeline

Automated daily pipeline that pulls solar generation forecast data from the NREL PVWatts API, stores it locally, and syncs it to cloud storage — running unattended via Windows Task Scheduler.

## Problem

Manually pulling solar forecast data for analysis meant repeated one-off API calls and no consistent historical record. This pipeline automates that process end-to-end and adds a cloud storage layer so data isn't trapped on a single machine.

## Architecture

```
NREL PVWatts API
      │
      ▼
  extract.py  ──────────────►  SQLite (local, bangkok_monthly_forecast table)
      │
      ├──────────────────────►  JSON export (solar_forecast.json)
      │
      └──────────────────────►  CSV export ──► AWS S3 (solar_forecast/YYYY-MM-DD.csv)

Triggered daily by Windows Task Scheduler → run_pipeline.bat → logged to log.txt
```

## What it does

1. **Extract** — Calls the NREL PVWatts v8 API for a fixed location (Bangkok, 4kW system) and pulls monthly AC power output and solar radiation forecasts.
2. **Transform** — Loads the API response into a pandas DataFrame (`month`, `ac_power_kwh`, `solar_radiation`).
3. **Load (local)** — Writes the DataFrame to a local SQLite database (`solar_forecast.db`) and exports a JSON snapshot.
4. **Load (cloud)** — Exports the same data as CSV and uploads it to an AWS S3 bucket, keyed by date (`solar_forecast/2026-09-11.csv`), so each day's run is preserved as a separate object.
5. **Automate** — A `.bat` script runs the whole pipeline daily via Task Scheduler, redirecting all output to `log.txt` for later debugging.

## Why AWS S3

The pipeline originally only wrote to a local SQLite file — if the machine failed, the data was gone, and it wasn't accessible from anywhere else. Adding an S3 sync means:
- Daily snapshots are durable and timestamped, giving a queryable history instead of just the latest state
- Data is accessible outside the local machine
- It mirrors how cloud data pipelines are structured in production, beyond just working against a local database

Uploads are wrapped in a try/except block so that a network or credentials failure doesn't crash the whole pipeline — it logs the error and the local SQLite write still succeeds.

## Fixes along the way

- **Silent failures on schedule** — Task Scheduler was invoking a different Python installation than the one `pip install` targeted, so `dotenv` (and later `boto3`) wasn't found when the job ran unattended even though it worked fine run manually. Fixed by pointing the scheduled task at the exact Python executable path used for installation.

## Tech stack

Python · pandas · SQLite · AWS S3 (boto3) · Windows Task Scheduler · REST APIs

## Setup

1. Install dependencies: `pip install requests pandas python-dotenv boto3`
2. Create a `.env` file with `NREL_API_KEY=your_key_here`
3. Configure AWS credentials: `aws configure` (requires an IAM user with S3 write access)
4. Run manually: `python extract.py`, or schedule via `run_pipeline.bat`

## Sample output

| month | ac_power_kwh | solar_radiation |
|-------|-------------|------------------|
| Jan   | 514.69      | 5.64             |
| Feb   | 502.17      | 6.26             |
| ...   | ...         | ...              |
