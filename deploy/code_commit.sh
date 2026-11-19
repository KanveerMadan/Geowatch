#!/bin/sh
# The commit that determines results (analysis/contract.py's code_commit():
# the last commit touching CODE_PATHS, serving files excluded). Pass it to
# the image build so a container's version_id matches a checkout's.
#   docker build --build-arg GEOWATCH_CODE_COMMIT=$(deploy/code_commit.sh) ...
set -e
cd "$(dirname "$0")/.."
python3 -c "import sys; sys.path.insert(0, '.'); from analysis.contract import code_commit; c = code_commit(); assert not c['dirty'], 'uncommitted changes under CODE_PATHS: commit first'; print(c['commit'])"
