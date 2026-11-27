#!/bin/sh
# v2 metadata screen (STAC metadata only). Resumable.
#   nohup caffeinate -i sh experiments/flood_m678/v2/run/screen_chain.sh >/dev/null 2>&1 &
#   check: tail -5 ~/.cache/geowatch/m678v2/screen.log
LOG="$HOME/.cache/geowatch/m678v2/screen.log"
cd "$HOME/gw-m678v2" || exit 1
PY="$HOME/geowatch/geowatch-env/bin/python"
echo "== $(date -u) reserve" >> "$LOG"; "$PY" -B -m experiments.flood_m678.v2.screen_v2 reserve >> "$LOG" 2>&1
echo "== $(date -u) dev" >> "$LOG"; "$PY" -B -m experiments.flood_m678.v2.screen_v2 dev >> "$LOG" 2>&1
echo "== $(date -u) done" >> "$LOG"
