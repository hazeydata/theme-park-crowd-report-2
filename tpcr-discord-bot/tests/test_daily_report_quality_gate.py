"""Tests for daily_report.py quality gate.

Validates that the quality gate correctly rejects posts when:
- pipeline_state.json is missing
- forecast_completed timestamp is absent
- forecast_completed timestamp is stale (>26h)
- WTI data is missing for any WDW park
- WTI data is out of bounds

And correctly passes when all checks are satisfied.
"""

import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from daily_report import quality_gate, WDW_PARKS

PARK_GROUPS = [
    ("Walt Disney World", [
        ("MK", "Magic Kingdom"), ("EP", "EPCOT"),
        ("HS", "Hollywood Studios"), ("AK", "Animal Kingdom"),
    ]),
    ("Disneyland Resort", [
        ("DL", "Disneyland"), ("CA", "California Adventure"),
    ]),
]


def _make_wti_fn(scores: dict):
    """Return a get_wti function that returns scores from a dict."""
    def get_wti(park_code: str, target_date: date) -> float:
        return scores.get(park_code)
    return get_wti


GOOD_WTI = {"MK": 20.0, "EP": 18.0, "HS": 25.0, "AK": 15.0, "DL": 22.0, "CA": 19.0}


class TestQualityGatePipelineState:
    """Check 1: Pipeline state freshness."""

    def test_missing_state_file_fails(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with patch("daily_report.PIPELINE_STATE", missing):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(GOOD_WTI), date.today())
        assert not passed
        assert "missing" in reason.lower()

    def test_missing_forecast_completed_fails(self, tmp_path):
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"training_completed": "2026-09-15T06:00:00"}))
        with patch("daily_report.PIPELINE_STATE", state_file):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(GOOD_WTI), date.today())
        assert not passed
        assert "forecast_completed" in reason

    def test_null_forecast_completed_fails(self, tmp_path):
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(json.dumps({"forecast_completed": None}))
        with patch("daily_report.PIPELINE_STATE", state_file):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(GOOD_WTI), date.today())
        assert not passed
        assert "forecast_completed" in reason

    def test_stale_forecast_fails(self, tmp_path):
        state_file = tmp_path / "pipeline_state.json"
        stale_ts = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        state_file.write_text(json.dumps({"forecast_completed": stale_ts}))
        with patch("daily_report.PIPELINE_STATE", state_file):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(GOOD_WTI), date.today())
        assert not passed
        assert "stale" in reason.lower()

    def test_fresh_forecast_passes_check1(self, tmp_path):
        state_file = tmp_path / "pipeline_state.json"
        fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        state_file.write_text(json.dumps({"forecast_completed": fresh_ts}))
        with patch("daily_report.PIPELINE_STATE", state_file):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(GOOD_WTI), date.today())
        assert passed
        assert "passed" in reason.lower()

    def test_corrupt_json_fails(self, tmp_path):
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text("NOT VALID JSON {{{")
        with patch("daily_report.PIPELINE_STATE", state_file):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(GOOD_WTI), date.today())
        assert not passed
        assert "check failed" in reason.lower()


class TestQualityGateWTI:
    """Check 2: WDW parks must all have valid WTI scores."""

    def _with_fresh_state(self, tmp_path):
        state_file = tmp_path / "pipeline_state.json"
        fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        state_file.write_text(json.dumps({"forecast_completed": fresh_ts}))
        return patch("daily_report.PIPELINE_STATE", state_file)

    def test_missing_wti_for_park_fails(self, tmp_path):
        scores = {"MK": 20.0, "EP": 18.0, "HS": 25.0}  # AK missing
        with self._with_fresh_state(tmp_path):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(scores), date.today())
        assert not passed
        assert "Missing WTI" in reason
        assert "AK" in reason

    def test_zero_wti_fails(self, tmp_path):
        scores = {"MK": 20.0, "EP": 0.0, "HS": 25.0, "AK": 15.0, "DL": 22.0, "CA": 19.0}
        with self._with_fresh_state(tmp_path):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(scores), date.today())
        assert not passed
        assert "Zero/negative" in reason

    def test_out_of_bounds_wti_fails(self, tmp_path):
        scores = {"MK": 20.0, "EP": 18.0, "HS": 75.0, "AK": 15.0, "DL": 22.0, "CA": 19.0}
        with self._with_fresh_state(tmp_path):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(scores), date.today())
        assert not passed
        assert "out of bounds" in reason.lower()

    def test_all_valid_passes(self, tmp_path):
        with self._with_fresh_state(tmp_path):
            passed, reason = quality_gate(PARK_GROUPS, _make_wti_fn(GOOD_WTI), date.today())
        assert passed
        assert "passed" in reason.lower()
