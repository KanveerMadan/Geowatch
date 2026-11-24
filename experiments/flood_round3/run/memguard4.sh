#!/bin/sh
# Pause the highest-numbered running shard (3, 2, 1) when free memory < 15 %; resume one above 25 %. Shard 0 never pauses.
L="$HOME/.cache/geowatch/flood_round3/run_chain.log"
while true; do
  pgrep -f "build_r3 s1feat se_flash_candidates [0-3] 4" >/dev/null || exit 0
  free=$(memory_pressure | awk '/free percentage/ {gsub("%","",$5); print $5}')
  [ -z "$free" ] && { sleep 30; continue; }
  if [ "$free" -lt 15 ]; then
    for k in 3 2 1; do
      P=$(pgrep -f "build_r3 s1feat se_flash_candidates $k 4"); [ -z "$P" ] && continue
      st=$(ps -o state= -p $P | cut -c1); [ "$st" = "T" ] && continue
      kill -STOP $P $(pgrep -P $P) 2>/dev/null; echo "$(date) memguard: free ${free}%, paused shard $k" >> "$L"; break
    done
  elif [ "$free" -gt 25 ]; then
    for k in 1 2 3; do
      P=$(pgrep -f "build_r3 s1feat se_flash_candidates $k 4"); [ -z "$P" ] && continue
      st=$(ps -o state= -p $P | cut -c1); [ "$st" = "T" ] || continue
      kill -CONT $P $(pgrep -P $P) 2>/dev/null; echo "$(date) memguard: free ${free}%, resumed shard $k" >> "$L"; break
    done
  fi
  sleep 30
done
