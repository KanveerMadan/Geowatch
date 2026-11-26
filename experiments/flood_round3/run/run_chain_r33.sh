#!/bin/sh
# R33 unattended chain: MRMS flash features -> waterlogging features -> HWM diagnostic -> DEV comparison for flash
# and waterlogging -> STATUS -> commit + push. Steps are idempotent (cached per unit); the outer loop reruns after a
# crash until R33_DONE exists. Log: ~/.cache/geowatch/flood_round3/run_chain_r33.log
R="$HOME/gw-floodproto"; L="$HOME/.cache/geowatch/flood_round3"; LOG="$L/run_chain_r33.log"; DONE="$L/R33_DONE"
cd "$R" || exit 1
set -a; . "$HOME/geowatch/.env"; set +a
export PYTHONPATH="$HOME/.cache/geowatch/flood_learned/pylib"
PY="$HOME/geowatch/geowatch-env/bin/python"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
publish() {
  cd "$R" && git add experiments/flood_round3/STATUS.md experiments/flood_round3/results/dev_cv_r3.json experiments/flood_round3/results/hwm_diagnostic.json 2>/dev/null
  if ! git diff --cached --quiet; then
    python3 tools/secrets_scan.py --staged >> "$LOG" 2>&1 && git commit -q -m "Round 3 R33: $1

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && sh tools/safe_push.sh origin exp/flood-round3 >> "$LOG" 2>&1 && log "pushed: $1"
  fi
}
chain() {
  log "MRMS flash features start"; "$PY" -m experiments.flood_round3.flash_mrms 4 >> "$L/flash_mrms.log" 2>&1; log "MRMS done ($(grep -c ' h$' "$L/flash_mrms.log") units with hours)"
  log "waterlogging features start"; "$PY" -m experiments.flood_round3.wl_feats >> "$L/wl_feats.log" 2>&1; log "waterlogging features done"
  [ -f "$R/experiments/flood_round3/results/hwm_diagnostic.json" ] || { log "HWM diagnostic start"; "$PY" -m experiments.flood_round3.label_ceiling hwm >> "$L/hwm_diag.log" 2>&1; log "HWM diagnostic done"; }
  while pgrep -f "dev_cv_r3 cv" >/dev/null 2>&1; do sleep 120; done
  log "DEV comparison (flash, waterlogging) start"
  "$PY" -m experiments.flood_round3.dev_cv_r3 cv flash_flood,waterlogging > "$L/dev_cv_r33.log" 2>&1 && log "DEV comparison done" || { log "DEV comparison FAILED, see $L/dev_cv_r33.log"; return 1; }
  "$PY" experiments/flood_round3/run/status_dev_cv.py >> "$LOG" 2>&1
  publish "DEV comparison with MRMS (flash) and ponding/soil/canal features (waterlogging)"
  touch "$DONE"; log "R33 ALL DONE"
}
log "R33 chain start"
until [ -f "$DONE" ]; do
  ( chain ) || log "chain error; restarting in 5 min"
  [ -f "$DONE" ] || sleep 300
done
