#!/bin/sh
# Round-3 unattended chain (R32). Every step is idempotent; the outer loop reruns the chain after a crash
# until ALL_DONE exists. Start: nohup caffeinate -i sh experiments/flood_round3/run/run_chain_r3.sh &
# Log: ~/.cache/geowatch/flood_round3/run_chain.log
R="$HOME/gw-floodproto"; L="$HOME/.cache/geowatch/flood_round3"; LOG="$L/run_chain.log"; DONE="$L/ALL_DONE"
cd "$R" || exit 1
set -a; . "$HOME/geowatch/.env"; set +a
export PYTHONPATH="$HOME/.cache/geowatch/flood_learned/pylib"
PY="$HOME/geowatch/geowatch-env/bin/python"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
publish() {   # commit + push STATUS and the DEV result; the secrets scan gates both
  cd "$R" && git add experiments/flood_round3/STATUS.md experiments/flood_round3/results/dev_cv_r3.json 2>/dev/null
  if ! git diff --cached --quiet; then
    python3 tools/secrets_scan.py --staged >> "$LOG" 2>&1 && git commit -q -m "Round 3: DEV comparison update ($1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && sh tools/safe_push.sh origin exp/flood-round3 >> "$LOG" 2>&1 && log "pushed: $1"
  fi
}
cv() {
  while pgrep -f "dev_cv_r3 cv" >/dev/null 2>&1; do sleep 120; done
  log "DEV comparison start ($1)"
  "$PY" -m experiments.flood_round3.dev_cv_r3 cv > "$L/dev_cv.log" 2>&1 && log "DEV comparison done ($1)" || log "DEV comparison FAILED ($1), see $L/dev_cv.log"
  "$PY" experiments/flood_round3/run/status_dev_cv.py >> "$LOG" 2>&1
  publish "$1"
}
chain() {
  # stop the older 2-shard build and its guard (parents only; a running unit finishes cleanly)
  pkill -TERM -f "s1feat_shards.sh" 2>/dev/null; pkill -TERM -f "memguard.sh" 2>/dev/null
  for P in $(pgrep -f "build_r3 s1feat se_flash_candidates [01] 2"); do kill -TERM $P 2>/dev/null; done
  # 1. river event features (skips units already done)
  while pgrep -f "dev_cv_r3 ev" >/dev/null 2>&1; do sleep 120; done
  log "river event features start"; "$PY" -m experiments.flood_round3.dev_cv_r3 ev >> "$L/dev_cv_ev.log" 2>&1; log "river event features done"
  # 2. flash / waterlogging feature tables to the targets: 4 shards + memory guard (shards skip built tables)
  for k in 0 1 2 3; do
    if ! pgrep -f "build_r3 s1feat se_flash_candidates $k 4" >/dev/null; then
      nohup "$PY" -m experiments.flood_round3.build_r3 s1feat se_flash_candidates $k 4 >> "$L/s1feat_${k}of4.log" 2>&1 &
      log "shard $k of 4 started"; sleep 30
    fi
  done
  pgrep -f "memguard4.sh" >/dev/null || { nohup sh "$R/experiments/flood_round3/run/memguard4.sh" >/dev/null 2>&1 & }
  # 3. DEV comparison now, then every 3 h while shards run, then once at the end
  cv "first run on finished units"
  while pgrep -f "build_r3 s1feat se_flash_candidates [0-3] 4" >/dev/null 2>&1; do
    sleep 10800
    cv "rerun, $(ls "$L/big/tables" | grep -c '^r3') flash/waterlogging tables"
  done
  cv "final, $(ls "$L/big/tables" | grep -c '^r3') flash/waterlogging tables"
  touch "$DONE"; log "ALL DONE"
}
log "chain start"
until [ -f "$DONE" ]; do
  ( chain ) || log "chain exited with an error; restarting in 5 min"
  [ -f "$DONE" ] || sleep 300
done
