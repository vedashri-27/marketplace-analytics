#!/usr/bin/env bash
# Rebuild the whole project from scratch, end to end.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 1/5  Generating synthetic marketplace data (CSVs + SQLite)"
python python/01_generate_data.py

echo "==> 2/5  Running + verifying all SQL analyses"
python python/02_run_sql.py

echo "==> 3/5  Analysis: charts + dashboard_data.json + experiment stats"
python python/03_analysis.py

echo "==> 4/5  Building the self-contained dashboard (dashboard/index.html)"
python python/05_build_dashboard.py

echo "==> 5/5  Weekly Business Review (automation demo)"
python python/04_weekly_report.py

echo
echo "Done. Open dashboard/index.html, browse charts/, and read docs/INSIGHTS.md."
echo "Optional dbt build:  cd dbt && export DATA_DIR=\$(cd ../data && pwd) && dbt build --profiles-dir ."
