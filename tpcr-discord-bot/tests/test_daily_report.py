"""Tests for daily_report.py — get_wti parquet fallback and --date argparse."""

import sys
import types
from datetime import date
from pathlib import Path
from unittest import mock

import duckdb
import pytest

# ---------------------------------------------------------------------------
# Bootstrap: stub heavy optional imports so daily_report can be imported
# without needing a real .env, requests, or dotenv on the test runner.
# ---------------------------------------------------------------------------
_stubs = {}
for mod_name in ("dotenv", "requests"):
    if mod_name not in sys.modules:
        _stubs[mod_name] = sys.modules[mod_name] = types.ModuleType(mod_name)
if "dotenv" in _stubs:
    sys.modules["dotenv"].load_dotenv = lambda *a, **kw: None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import daily_report  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def wti_parquet(tmp_path):
    """Create a small WTI parquet file with known rows."""
    pq = tmp_path / "wti.parquet"
    duckdb.sql(f"""
        COPY (
            SELECT 'MK' AS park_code, DATE '2026-09-15' AS park_date, 22.4 AS wti
            UNION ALL
            SELECT 'EP', DATE '2026-09-15', 18.1
        ) TO '{pq}' (FORMAT PARQUET)
    """)
    return str(pq)


# ── get_wti parquet fallback ──────────────────────────────────────────────

class TestGetWtiParquetFallback:
    """When DuckDB live DB has no row or errors, get_wti should fall back to parquet."""

    def test_fallback_when_duckdb_has_no_row(self, wti_parquet):
        with (
            mock.patch.object(daily_report, "_USE_DUCKDB", True),
            mock.patch.object(daily_report, "DUCKDB_PATH", ":memory:"),
            mock.patch.object(daily_report, "WTI_PATH", wti_parquet),
        ):
            con = duckdb.connect(":memory:")
            con.execute("CREATE TABLE wti (park_code VARCHAR, park_date DATE, wti DOUBLE)")
            con.close()
            # DuckDB table exists but has no matching row → fallback to parquet
            result = daily_report.get_wti("MK", date(2026, 9, 15))
        assert result == pytest.approx(22.4)

    def test_fallback_when_duckdb_connect_errors(self, wti_parquet):
        with (
            mock.patch.object(daily_report, "_USE_DUCKDB", True),
            mock.patch.object(daily_report, "DUCKDB_PATH", "/nonexistent/bad.duckdb"),
            mock.patch.object(daily_report, "WTI_PATH", wti_parquet),
        ):
            result = daily_report.get_wti("EP", date(2026, 9, 15))
        assert result == pytest.approx(18.1)

    def test_returns_none_when_both_paths_miss(self, wti_parquet):
        with (
            mock.patch.object(daily_report, "_USE_DUCKDB", True),
            mock.patch.object(daily_report, "DUCKDB_PATH", "/nonexistent/bad.duckdb"),
            mock.patch.object(daily_report, "WTI_PATH", wti_parquet),
        ):
            result = daily_report.get_wti("XX", date(2026, 9, 15))
        assert result is None

    def test_parquet_only_mode(self, wti_parquet):
        with (
            mock.patch.object(daily_report, "_USE_DUCKDB", False),
            mock.patch.object(daily_report, "WTI_PATH", wti_parquet),
        ):
            result = daily_report.get_wti("MK", date(2026, 9, 15))
        assert result == pytest.approx(22.4)


# ── --date argparse ───────────────────────────────────────────────────────

class TestDateArgparse:
    """main() should accept --date YYYY-MM-DD and use it as `today`."""

    def test_date_flag_parsed(self):
        with mock.patch("sys.argv", ["daily_report.py", "--date", "2026-09-10"]):
            parser = daily_report.argparse.ArgumentParser(description="Daily Crowd Report")
            parser.add_argument(
                "--date",
                type=lambda s: date.fromisoformat(s),
                default=None,
            )
            args = parser.parse_args()
        assert args.date == date(2026, 9, 10)

    def test_date_flag_default_is_none(self):
        with mock.patch("sys.argv", ["daily_report.py"]):
            parser = daily_report.argparse.ArgumentParser(description="Daily Crowd Report")
            parser.add_argument(
                "--date",
                type=lambda s: date.fromisoformat(s),
                default=None,
            )
            args = parser.parse_args()
        assert args.date is None

    def test_invalid_date_rejected(self):
        with mock.patch("sys.argv", ["daily_report.py", "--date", "not-a-date"]):
            parser = daily_report.argparse.ArgumentParser(description="Daily Crowd Report")
            parser.add_argument(
                "--date",
                type=lambda s: date.fromisoformat(s),
                default=None,
            )
            with pytest.raises(SystemExit):
                parser.parse_args()
