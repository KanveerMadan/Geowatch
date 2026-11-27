#!/bin/sh
# v2 DEV labels (one heavy worker; exclusive EE lock per call via labels_m678.init_ee). Resumable.
#   nohup caffeinate -i sh experiments/flood_m678/v2/run/labels_dev_chain.sh >/dev/null 2>&1 &
#   check: grep -v "EE ok" ~/.cache/geowatch/m678v2/labels_dev.log | tail -20
LOG="$HOME/.cache/geowatch/m678v2/labels_dev.log"
PY="$HOME/geowatch/geowatch-env/bin/python"
cd "$HOME/gw-r3pin-r35" || exit 1
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
       PYTHONPATH=".:$HOME/gw-m678v2/experiments/flood_m678:$HOME/.cache/geowatch/flood_learned/pylib"
while [ "$(memory_pressure | tail -1 | grep -o '[0-9]*')" -lt 20 ]; do echo "$(date -u) memory < 20 %: paused" >> "$LOG"; sleep 300; done
echo "== $(date -u) labels dev" >> "$LOG"
"$PY" -B "$HOME/gw-m678v2/experiments/flood_m678/v2/labels.py" dev >> "$LOG" 2>&1
echo "== $(date -u) done" >> "$LOG"
