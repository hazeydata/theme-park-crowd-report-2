#!/bin/bash
# install_daily_report_cron.sh — Install daily crowd report cron job
#
# Adds a cron job that runs tpcr-discord-bot/daily_report.py once per day.
# Posts the daily crowd report to #crowd-reports after the pipeline finishes.
#
# Schedule: 11:00 AM ET (after the 6–8 AM pipeline window completes)
# Matches the schedule in docs/TPCR_CUSTOMER_SERVICE_DESIGN_SPEC.md Domain 4.
#
# The daily_report.py quality gate will skip posting if the pipeline
# hasn't produced fresh data, so running at a fixed time is safe.
#
# Usage:
#   bash scripts/install_daily_report_cron.sh           # Install
#   bash scripts/install_daily_report_cron.sh --remove   # Remove
#   bash scripts/install_daily_report_cron.sh --show     # Preview

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PROJECT_ROOT="$(get_project_root)"
OUTPUT_BASE="$(get_output_base "$PROJECT_ROOT")"
PYTHON="$(get_python)"
LOGS_DIR="$OUTPUT_BASE/logs"

if [[ ! -d "$LOGS_DIR" ]]; then
    LOGS_DIR="$PROJECT_ROOT/logs"
    mkdir -p "$LOGS_DIR" 2>/dev/null || true
fi

VENV_ACTIVATE="$PROJECT_ROOT/.venv/bin/activate"

CRON_MARKER="# daily-crowd-report"
CRON_ENTRY="0 11 * * * export PATH=\"\$HOME/.local/bin:\$PATH\" && cd $PROJECT_ROOT && source $VENV_ACTIVATE && $PYTHON $PROJECT_ROOT/tpcr-discord-bot/daily_report.py >> \"$LOGS_DIR/daily_report.log\" 2>&1 $CRON_MARKER"

show_cron() {
    echo "=== Daily crowd report cron entry ==="
    echo ""
    echo "$CRON_ENTRY"
    echo ""
    echo "Runs: tpcr-discord-bot/daily_report.py at 11:00 AM (server local time)"
    echo "Log:  $LOGS_DIR/daily_report.log"
    echo ""
    echo "The quality gate inside daily_report.py checks pipeline freshness"
    echo "before posting. If the pipeline hasn't run, the post is skipped."
    echo ""
}

install_cron() {
    echo "Installing daily crowd report cron job..."
    mkdir -p "$LOGS_DIR" 2>/dev/null || true
    (crontab -l 2>/dev/null | grep -v "$CRON_MARKER" || true; echo "# Daily: post crowd report to #crowd-reports at 11 AM ET"; echo "$CRON_ENTRY") | crontab -
    echo "Done. Job runs daily at 11:00 AM and survives reboot."
    echo "View: crontab -l"
    echo "Log:  tail -f $LOGS_DIR/daily_report.log"
}

remove_cron() {
    echo "Removing daily crowd report cron job..."
    crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | crontab - || true
    echo "Done."
}

case "${1:-}" in
    --show)
        show_cron
        ;;
    --remove)
        remove_cron
        ;;
    --help|-h)
        echo "Usage: $0 [--show|--remove|--help]"
        echo ""
        echo "  (none)    Install daily crowd report cron job (11 AM ET)"
        echo "  --show    Preview what would be installed"
        echo "  --remove  Remove the cron job"
        exit 0
        ;;
    "")
        install_cron
        ;;
    *)
        echo "Unknown option: $1"
        exit 1
        ;;
esac
