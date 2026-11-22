#!/bin/sh
# Scan every commit not yet on the remote branch, then push. Exits non-zero
# (and does not push) when the scan finds anything.
#   tools/safe_push.sh [remote] [branch]
set -e
remote="${1:-origin}"
branch="${2:-$(git rev-parse --abbrev-ref HEAD)}"
here="$(cd "$(dirname "$0")" && pwd)"
if git rev-parse --verify --quiet "$remote/$branch" >/dev/null; then
  base="$remote/$branch"
else
  base="$(git merge-base HEAD "$remote/master")"
fi
python3 "$here/secrets_scan.py" --range "$base..HEAD"
git push "$remote" "$branch"
