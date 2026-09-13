"""
Unit tests for the solar forecast data contract, written with pytest.
Run with: pytest tests/test_data_contract.py -v
"""

import pytest
from pydantic import ValidationError
from extract import MonthlyForecastRecord, validate_records, compute_quality_score
import pandas as pd


# ===================== Valid record tests =====================

def test_valid_record_accepted():
    """A normal, realistic record should pass without error."""
    record = MonthlyForecastRecord(
        month="Jan", ac_power_kwh=514.68, solar_radiation=5.64
    )
    assert record.month == "Jan"
    assert record.ac_power_kwh == 514.68


def test_valid_record_at_boundary():
    """Values exactly at the allowed boundary should still pass."""
    record = MonthlyForecastRecord(
        month="Dec", ac_power_kwh=2000.0, solar_radiation=10.0
    )
    assert record.ac_power_kwh == 2000.0
    assert record.solar_radiation == 10.0


# ===================== Invalid month tests =====================

def test_invalid_month_string_rejected():
    with pytest.raises(ValidationError):
        MonthlyForecastRecord(
            month="Smarch", ac_power_kwh=500.0, solar_radiation=5.0
        )


def test_lowercase_month_rejected():
    """Month must match the exact 3-letter capitalized format."""
    with pytest.raises(ValidationError):
        MonthlyForecastRecord(
            month="jan", ac_power_kwh=500.0, solar_radiation=5.0
        )


# ===================== Power validation tests =====================

def test_negative_power_rejected():
    with pytest.raises(ValidationError):
        MonthlyForecastRecord(
            month="Jan", ac_power_kwh=-150.0, solar_radiation=5.0
        )


def test_zero_power_accepted():
    """Zero power is physically valid (e.g. nighttime), unlike negative."""
    record = MonthlyForecastRecord(
        month="Jan", ac_power_kwh=0.0, solar_radiation=0.0
    )
    assert record.ac_power_kwh == 0.0


def test_excessive_power_rejected():
    with pytest.raises(ValidationError):
        MonthlyForecastRecord(
            month="Feb", ac_power_kwh=99999.0, solar_radiation=5.0
        )


# ===================== Radiation validation tests =====================

def test_negative_radiation_rejected():
    with pytest.raises(ValidationError):
        MonthlyForecastRecord(
            month="Apr", ac_power_kwh=500.0, solar_radiation=-2.0
        )


def test_radiation_above_max_rejected():
    with pytest.raises(ValidationError):
        MonthlyForecastRecord(
            month="Mar", ac_power_kwh=500.0, solar_radiation=45.0
        )


# ===================== Type validation tests =====================

def test_string_instead_of_number_rejected():
    with pytest.raises(ValidationError):
        MonthlyForecastRecord(
            month="May", ac_power_kwh="error", solar_radiation=5.0
        )


# ===================== validate_records() integration tests =====================

def test_validate_records_all_pass():
    """A clean 12-month DataFrame should produce zero failures."""
    df = pd.DataFrame({
        "month": ["Jan", "Feb", "Mar"],
        "ac_power_kwh": [500.0, 480.0, 550.0],
        "solar_radiation": [5.5, 5.2, 6.0],
    })
    valid, failures = validate_records(df)
    assert len(valid) == 3
    assert len(failures) == 0


def test_validate_records_catches_bad_row():
    """A DataFrame with one bad row should isolate exactly that failure."""
    df = pd.DataFrame({
        "month": ["Jan", "Feb", "Mar"],
        "ac_power_kwh": [500.0, -999.0, 550.0],  # Feb is bad
        "solar_radiation": [5.5, 5.2, 6.0],
    })
    valid, failures = validate_records(df)
    assert len(valid) == 2
    assert len(failures) == 1
    assert failures[0]["row"]["month"] == "Feb"


# ===================== Quality score tests =====================

def test_quality_score_perfect():
    score, grade = compute_quality_score(valid_records=[1, 2, 3], failures=[], total=3)
    assert score == 100.0
    assert grade == "A"


def test_quality_score_grade_boundaries():
    # 10/12 = 83.3% -> Grade C
    score, grade = compute_quality_score(valid_records=list(range(10)), failures=list(range(2)), total=12)
    assert grade == "C"

    # 11/12 = 91.7% -> Grade B
    score, grade = compute_quality_score(valid_records=list(range(11)), failures=list(range(1)), total=12)
    assert grade == "B"


def test_quality_score_zero_total_handled():
    """Edge case: an empty DataFrame shouldn't crash with a division by zero."""
    score, grade = compute_quality_score(valid_records=[], failures=[], total=0)
    assert score == 0
    assert grade == "F"