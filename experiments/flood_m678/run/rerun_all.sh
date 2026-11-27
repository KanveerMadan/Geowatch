#!/bin/sh
# One-command rerun of M6–M8 (metadata catalogue -> seal check -> DEV -> CV). The reserve test is
# one-shot: rerunning `score_m678 test` refuses once results/test_m678.json exists.
#   sh experiments/flood_m678/run/rerun_all.sh            (from ~/gw-m678)
set -e
PY="$HOME/geowatch/geowatch-env/bin/python"
CACHE="$HOME/.cache/geowatch/flood_m678"
[ -d "$HOME/gw-r3pin" ] || git worktree add --detach "$HOME/gw-r3pin" f28d71446f0c3f9d180b4415b7e6f8a4fe204f5f
cd "$HOME/gw-m678/experiments/flood_m678"
"$PY" gauge_crests.py "$CACHE/stage"
"$PY" geoglows_crests.py
"$PY" screen_acquisitions.py "$CACHE/stac"
"$PY" overlap.py "$HOME/gw-m678"
"$PY" select_m678.py
shasum -a 256 reserve_m678.json        # compare with RESERVE_HASH_M678.txt
"$PY" -m unittest -q test_catalog
cd "$HOME/gw-r3pin"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=".:$HOME/gw-m678/experiments/flood_m678:$HOME/.cache/geowatch/flood_learned/pylib"  # LightGBM lives in round 2/3's private pylib
"$PY" -B -m labels_m678 dev
"$PY" -B -m features_m678 dev
"$PY" -B -m dev_cv_m678 feats dev
"$PY" -B -m dev_cv_m678 cv
