"""Hard timeout for Earth Engine calls.

Every `getInfo`, `computeFeatures` and `computePixels` in this pipeline is a
blocking HTTP request against EE's servers with no client-side deadline. Two of
them hung for 80 minutes during site recon and produced nothing -- the process
sat there holding a socket with no way to tell whether it was slow or dead.

`call()` runs the request on a DAEMON thread and abandons it if it overruns.
Daemon matters: an abandoned thread cannot be killed, but a daemon one will not
keep the interpreter alive at exit, so a hung request costs one leaked thread
instead of a hung process. Retries get a fresh thread each time.

Usage:
    from ee_timeout import call
    info = call(lambda: proj.getInfo(), label="s2 grid")
"""

import threading
import time

DEFAULT_TIMEOUT = 120      # seconds; a single EE request must beat this
DEFAULT_RETRIES = 3


class EETimeout(RuntimeError):
    pass


def call(fn, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES, label=""):
    """Run fn() with a hard deadline. Raise EETimeout if every attempt overruns.

    Returns fn()'s value. Exceptions raised inside fn propagate on the final
    attempt, so a genuine EE error is not silently retried into a timeout.
    """
    tag = f" [{label}]" if label else ""
    last_exc = None
    for attempt in range(1, retries + 1):
        box = {}

        def runner():
            try:
                box["v"] = fn()
            except BaseException as e:            # noqa: BLE001
                box["e"] = e

        t = threading.Thread(target=runner, daemon=True)
        t0 = time.time()
        t.start()
        t.join(timeout)
        dt = time.time() - t0

        if t.is_alive():
            print(f"  EE TIMEOUT{tag} after {dt:.0f}s "
                  f"(attempt {attempt}/{retries}) -- abandoning and retrying",
                  flush=True)
            last_exc = EETimeout(f"EE call{tag} exceeded {timeout}s")
            continue
        if "e" in box:
            last_exc = box["e"]
            if attempt == retries:
                raise last_exc
            print(f"  EE ERROR{tag} after {dt:.0f}s "
                  f"(attempt {attempt}/{retries}): {str(last_exc)[:100]}",
                  flush=True)
            time.sleep(2 * attempt)
            continue
        if attempt > 1 or dt > 20:
            print(f"  EE ok{tag} in {dt:.0f}s", flush=True)
        return box["v"]

    raise last_exc
