#!/bin/sh
# M6–M8 DEV chain: labels then round-3 feature tables. Resumable; safe to rerun.
#   nohup caffeinate -i sh experiments/flood_m678/run/chain_dev.sh >/dev/null 2>&1 &
#   check: tail -20 ~/.cache/geowatch/flood_m678/chain_dev.log
LOG="$HOME/.cache/geowatch/flood_m678/chain_dev.log"
PY="$HOME/geowatch/geowatch-env/bin/python"
mkdir -p "$(dirname "$LOG")"
cd "$HOME/gw-r3pin" || exit 1
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=".:$HOME/gw-m678/experiments/flood_m678"
echo "== $(date -u) labels dev" >> "$LOG"
"$PY" -B -m labels_m678 dev >> "$LOG" 2>&1
echo "== $(date -u) features dev" >> "$LOG"
"$PY" -B -m features_m678 dev >> "$LOG" 2>&1
echo "== $(date -u) chain done" >> "$LOG"
