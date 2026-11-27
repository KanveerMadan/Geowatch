#!/bin/sh
# R34 unattended chain: lean, checkpointed DEV comparison (flash, waterlogging) -> STATUS -> commit + push.
# Restarts after a crash until R34_DONE exists; finished fits are skipped. Log: ~/.cache/geowatch/flood_round3/run_chain_r34.log
R="$HOME/gw-floodproto"; L="$HOME/.cache/geowatch/flood_round3"; LOG="$L/run_chain_r34.log"; DONE="$L/R34_DONE"
cd "$R" || exit 1
set -a; . "$HOME/geowatch/.env"; set +a
export PYTHONPATH="$R:$HOME/.cache/geowatch/flood_learned/pylib"
PY="$HOME/geowatch/geowatch-env/bin/python"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
chain() {
  log "lean DEV comparison (flash, waterlogging) start"
  "$PY" -m experiments.flood_round3.cv_lean flash_flood,waterlogging >> "$L/cv_lean.log" 2>&1 || { log "cv_lean FAILED (see cv_lean.log)"; return 1; }
  log "lean DEV comparison done"
  "$PY" experiments/flood_round3/run/status_dev_cv.py >> "$LOG" 2>&1
  git add experiments/flood_round3/STATUS.md experiments/flood_round3/results/dev_cv_r3.json
  if ! git diff --cached --quiet; then
    python3 tools/secrets_scan.py --staged >> "$LOG" 2>&1 && git commit -q -m "Round 3 R34: DEV comparison with MRMS (flash) and ponding/soil/canal features (waterlogging)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && sh tools/safe_push.sh origin exp/flood-round3 >> "$LOG" 2>&1 && log "pushed"
  fi
  touch "$DONE"; log "R34 ALL DONE"
}
log "R34 chain start"
until [ -f "$DONE" ]; do
  ( chain ) || log "chain error; restarting in 5 min"
  [ -f "$DONE" ] || sleep 300
done
