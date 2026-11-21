"""One Earth Engine task per local GeoWatch round-2 work session."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
import runpy
import sys
from threading import RLock

LOCKFILE = Path("/private/tmp/geowatch-change-round2-ee.lock")
_LOCAL = RLock()
_DEPTH = 0


@contextmanager
def ee_lock(path=LOCKFILE):
    """Block other processes; nested use on the owning thread is reentrant."""
    global _DEPTH
    with _LOCAL:
        if _DEPTH:
            yield
            return
        with path.open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            _DEPTH = 1
            try:
                yield
            finally:
                _DEPTH = 0
                fcntl.flock(stream, fcntl.LOCK_UN)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m experiments.change_round2.monitor_lock MODULE [ARGS]")
    module = sys.argv.pop(1)
    from .monitor_lock import ee_lock as shared_lock
    with shared_lock():
        runpy.run_module(module, run_name="__main__")
