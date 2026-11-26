"""
Round 3 (R33): cooperate with other local Earth Engine clients (Codex's tools/ee_batch uses an exclusive flock on
LOCK). Every Earth Engine API call from a round-3 process takes a SHARED lock on the same file: round-3 jobs run in
parallel with each other, and an exclusive holder (another client) runs alone.

    from experiments.flood_round3 import ee_lock; ee_lock.install()     # once per process, before EE calls
"""
from __future__ import annotations

import fcntl
import os

LOCK = "/private/tmp/geowatch-change-round2-ee.lock"
_done = {"v": False}


def install():
    if _done["v"]:
        return
    import ee.data as D
    orig = D._execute_cloud_call

    def locked(*a, **k):
        with open(LOCK, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                return orig(*a, **k)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    D._execute_cloud_call = locked
    _done["v"] = True
    os.environ["GEOWATCH_EE_LOCK"] = LOCK
