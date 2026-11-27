#!/bin/sh
# v2 recruitment downloads (metadata only). Resumable (raw files cached); stops under 15 GB free disk.
#   nohup caffeinate -i sh experiments/flood_m678/v2/run/recruit_chain.sh >/dev/null 2>&1 &
#   check: tail -20 ~/.cache/geowatch/m678v2/recruit.log
LOG="$HOME/.cache/geowatch/m678v2/recruit.log"; mkdir -p "$(dirname "$LOG")"
cd "$HOME/gw-m678v2" || exit 1
PY="$HOME/geowatch/geowatch-env/bin/python"
echo "== $(date -u) wsc" >> "$LOG"
"$PY" -B -m experiments.flood_m678.v2.recruit wsc_ice wsc_melt >> "$LOG" 2>&1
echo "== $(date -u) usgs" >> "$LOG"
"$PY" -B -m experiments.flood_m678.v2.recruit usgs_peaks >> "$LOG" 2>&1
echo "== $(date -u) done" >> "$LOG"
