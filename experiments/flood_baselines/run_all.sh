#!/bin/sh
# Overnight build + score for exp/flood-baselines. Run from the repo root:
#   caffeinate -i sh experiments/flood_baselines/run_all.sh
# GEE_PROJECT_ID must be in the environment. Each pass skips work already
# cached, so the script can be re-run after an interruption.
set -u
PY="${PY:-$HOME/geowatch/geowatch-env/bin/python}"
LOG="${HOME}/.cache/geowatch/flood_baselines/run_all.log"
mkdir -p "$(dirname "$LOG")"
stamp() { date "+%Y-%m-%d %H:%M:%S"; }
echo "$(stamp) start" >> "$LOG"
echo "$(stamp) pass 1: rasters, JRC, water" >> "$LOG"
"$PY" -m experiments.flood_baselines.build --qualifying >> "$LOG" 2>&1
echo "$(stamp) pass 2: OSM water refresh" >> "$LOG"
"$PY" -m experiments.flood_baselines.build --qualifying --refresh-water >> "$LOG" 2>&1
echo "$(stamp) pass 3: pluvial" >> "$LOG"
"$PY" -m experiments.flood_baselines.build --qualifying --pluvial >> "$LOG" 2>&1
echo "$(stamp) pass 4: OSM water refresh (second try)" >> "$LOG"
"$PY" -m experiments.flood_baselines.build --qualifying --refresh-water >> "$LOG" 2>&1
echo "$(stamp) score" >> "$LOG"
"$PY" -m experiments.flood_baselines.score >> "$LOG" 2>&1
"$PY" -m experiments.flood_baselines.tables >> "$LOG" 2>&1
echo "$(stamp) done (exit $?)" >> "$LOG"
