#!/bin/sh
# Batch-0 run of the learned flood model. From the repo root:
#   caffeinate -i sh experiments/flood_learned/run_all.sh
# Needs GEE_PROJECT_ID in the environment (fetch only) and LightGBM on
# PYTHONPATH (installed outside geowatch-env; see REPORT.md, Reproduce).
# Every step skips what it has cached, so the script resumes.
set -u
PY="${PY:-$HOME/geowatch/geowatch-env/bin/python}"
LOG="${HOME}/.cache/geowatch/flood_learned/run_all.log"
mkdir -p "$(dirname "$LOG")"
stamp() { date "+%Y-%m-%d %H:%M:%S"; }
echo "$(stamp) start" >> "$LOG"
"$PY" -m experiments.flood_learned.fetch >> "$LOG" 2>&1
"$PY" -m experiments.flood_learned.fetch --redo-step settings >> "$LOG" 2>&1
"$PY" -m experiments.flood_learned.fetch --redo-step gedtm30 >> "$LOG" 2>&1
"$PY" -m experiments.flood_learned.features >> "$LOG" 2>&1
echo "$(stamp) model" >> "$LOG"
"$PY" -m experiments.flood_learned.model >> "$LOG" 2>&1
echo "$(stamp) evaluate" >> "$LOG"
"$PY" -m experiments.flood_learned.evaluate >> "$LOG" 2>&1
"$PY" -m experiments.flood_learned.tables >> "$LOG" 2>&1
"$PY" -m experiments.flood_learned.maps >> "$LOG" 2>&1
echo "$(stamp) done" >> "$LOG"
