"""
Generates a weekly data quality summary report from quality_log.json.
Run with: python weekly_quality_report.py
"""

import json
import csv
import os
from datetime import datetime, timedelta
from collections import Counter

DATA_DIR = "data"


def load_quality_log(log_path=os.path.join(DATA_DIR, "quality_log.json")):
    with open(log_path, "r") as f:
        return json.load(f)


def filter_last_n_days(quality_log, days=7):
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return [entry for entry in quality_log if entry["date"] >= cutoff]


def build_summary(entries):
    if not entries:
        return None

    scores = [e["score"] for e in entries]
    grades = Counter(e["grade"] for e in entries)
    total_records = sum(e["total_count"] for e in entries)
    total_failed = sum(e["failed_count"] for e in entries)
    worst_day = min(entries, key=lambda e: e["score"])
    best_day = max(entries, key=lambda e: e["score"])

    return {
        "period_start": min(e["date"] for e in entries),
        "period_end": max(e["date"] for e in entries),
        "days_tracked": len(entries),
        "average_score": round(sum(scores) / len(scores), 1),
        "grade_distribution": dict(grades),
        "total_records_processed": total_records,
        "total_records_failed": total_failed,
        "overall_pass_rate": round((total_records - total_failed) / total_records * 100, 1) if total_records else 0,
        "worst_day": {"date": worst_day["date"], "score": worst_day["score"], "grade": worst_day["grade"]},
        "best_day": {"date": best_day["date"], "score": best_day["score"], "grade": best_day["grade"]},
    }


def write_report_csv(summary, entries, output_path=os.path.join(DATA_DIR, "weekly_quality_report.csv")):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow(["Weekly Data Quality Report"])
        writer.writerow(["Period", f"{summary['period_start']} to {summary['period_end']}"])
        writer.writerow(["Days Tracked", summary["days_tracked"]])
        writer.writerow(["Average Score", f"{summary['average_score']}%"])
        writer.writerow(["Overall Pass Rate", f"{summary['overall_pass_rate']}%"])
        writer.writerow(["Total Records Processed", summary["total_records_processed"]])
        writer.writerow(["Total Records Failed", summary["total_records_failed"]])
        writer.writerow([])
        writer.writerow(["Grade Distribution"])
        for grade in ["A", "B", "C", "D", "F"]:
            writer.writerow([grade, summary["grade_distribution"].get(grade, 0)])
        writer.writerow([])
        writer.writerow(["Best Day", summary["best_day"]["date"], f"{summary['best_day']['score']}%", summary["best_day"]["grade"]])
        writer.writerow(["Worst Day", summary["worst_day"]["date"], f"{summary['worst_day']['score']}%", summary["worst_day"]["grade"]])
        writer.writerow([])
        writer.writerow(["Date", "Score (%)", "Grade", "Valid", "Total", "Failed"])
        for e in sorted(entries, key=lambda x: x["date"]):
            writer.writerow([e["date"], e["score"], e["grade"], e["valid_count"], e["total_count"], e["failed_count"]])


def print_summary(summary):
    print("=" * 50)
    print("WEEKLY DATA QUALITY REPORT")
    print("=" * 50)
    print(f"Period: {summary['period_start']} to {summary['period_end']} ({summary['days_tracked']} days)")
    print(f"Average Score: {summary['average_score']}%")
    print(f"Overall Pass Rate: {summary['overall_pass_rate']}% ({summary['total_records_processed'] - summary['total_records_failed']}/{summary['total_records_processed']} records)")
    print(f"Grade Distribution: {summary['grade_distribution']}")
    print(f"Best Day: {summary['best_day']['date']} ({summary['best_day']['score']}%, Grade {summary['best_day']['grade']})")
    print(f"Worst Day: {summary['worst_day']['date']} ({summary['worst_day']['score']}%, Grade {summary['worst_day']['grade']})")


if __name__ == "__main__":
    quality_log = load_quality_log()
    recent_entries = filter_last_n_days(quality_log, days=7)

    if not recent_entries:
        print("No quality data found in the last 7 days.")
    else:
        summary = build_summary(recent_entries)
        print_summary(summary)
        write_report_csv(summary, recent_entries)
        print(f"\nReport saved to {os.path.join(DATA_DIR, 'weekly_quality_report.csv')}")