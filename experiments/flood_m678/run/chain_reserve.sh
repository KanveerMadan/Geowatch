#!/bin/sh
# M6–M8 one-shot reserve chain, after tag m678-freeze. Resumable; the scorer refuses a second run.
#   nohup caffeinate -i sh experiments/flood_m678/run/chain_reserve.sh >/dev/null 2>&1 &
#   check: tail -20 ~/.cache/geowatch/flood_m678/chain_reserve.log
LOG="$HOME/.cache/geowatch/flood_m678/chain_reserve.log"
PY="$HOME/geowatch/geowatch-env/bin/python"
cd "$HOME/gw-r3pin" || exit 1
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=".:$HOME/gw-m678/experiments/flood_m678:$HOME/.cache/geowatch/flood_learned/pylib"
heavy_wait() {   # owner rule: one heavy job at a time on this 8 GB machine
  while pgrep -f "flood_round3.(cv_lean|dev_cv_r3|build_r3)" >/dev/null || \
        [ "$(memory_pressure | tail -1 | grep -o '[0-9]*')" -lt 25 ]; do
    echo "$(date -u) waiting: round-3 heavy job or memory < 25 %" >> "$LOG"; sleep 300; done
}
echo "== $(date -u) labels reserve" >> "$LOG"
"$PY" -B -m labels_m678 reserve >> "$LOG" 2>&1
heavy_wait
echo "== $(date -u) features reserve" >> "$LOG"
"$PY" -B -m features_m678 reserve >> "$LOG" 2>&1
heavy_wait
echo "== $(date -u) event features reserve" >> "$LOG"
"$PY" -B -m dev_cv_m678 feats reserve >> "$LOG" 2>&1
echo "== $(date -u) ONE-SHOT TEST" >> "$LOG"
"$PY" -B -m score_m678 test >> "$LOG" 2>&1
echo "== $(date -u) chain done" >> "$LOG"
