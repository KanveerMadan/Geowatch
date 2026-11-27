#!/bin/sh
# Runs after the DEV label chain (one heavy worker at a time). Resumable.
#   nohup caffeinate -i sh experiments/flood_m678/v2/run/tables_dev_chain.sh >/dev/null 2>&1 &
#   check: grep -v "EE ok" ~/.cache/geowatch/m678v2/tables_dev.log | tail -20
LOG="$HOME/.cache/geowatch/m678v2/tables_dev.log"
PY="$HOME/geowatch/geowatch-env/bin/python"
while pgrep -f "v2/labels.py dev" >/dev/null; do sleep 600; done
while [ "$(memory_pressure | tail -1 | grep -o '[0-9]*')" -lt 20 ]; do echo "$(date -u) memory < 20 %: paused" >> "$LOG"; sleep 300; done
cd "$HOME/gw-r3pin-r35" || exit 1
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 PYTHONPATH=".:$HOME/gw-m678v2/experiments/flood_m678:$HOME/.cache/geowatch/flood_learned/pylib"
echo "== $(date -u) tables dev" >> "$LOG"
"$PY" -B "$HOME/gw-m678v2/experiments/flood_m678/v2/dev_tables.py" >> "$LOG" 2>&1
echo "== $(date -u) done" >> "$LOG"
