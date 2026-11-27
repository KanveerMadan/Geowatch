#!/bin/sh
# v2 DEV worker (one heavy job at a time): tables + corridor on labels so far, then labels (resume),
# tables, corridor. Resumable at every stage.
#   nohup caffeinate -i sh experiments/flood_m678/v2/run/dev_chain.sh >/dev/null 2>&1 &
#   check: grep -v "EE ok" ~/.cache/geowatch/m678v2/dev_chain.log | tail -20
LOG="$HOME/.cache/geowatch/m678v2/dev_chain.log"
PY="$HOME/geowatch/geowatch-env/bin/python"
V2="$HOME/gw-m678v2/experiments/flood_m678/v2"
cd "$HOME/gw-r3pin-r35" || exit 1
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 PYTHONPATH=".:$HOME/gw-m678v2/experiments/flood_m678:$HOME/.cache/geowatch/flood_learned/pylib"
guard() { while [ "$(memory_pressure | tail -1 | grep -o '[0-9]*')" -lt 20 ]; do echo "$(date -u) memory < 20 %: paused" >> "$LOG"; sleep 300; done; }
step() { guard; echo "== $(date -u) $*" >> "$LOG"; "$PY" -B "$V2/$1" ${2:+$2} >> "$LOG" 2>&1; }
step dev_tables.py
step corridor.py
step labels.py dev
step dev_tables.py
step corridor.py
echo "== $(date -u) done" >> "$LOG"
