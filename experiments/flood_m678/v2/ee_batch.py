"""
M6–M8 v2: Earth Engine on the free tier (owner decision 2026-11-28: no quota raise).

- `install(ee, project)` wraps round 3's `susceptibility.hydro_rasters.compute_pixels`, which every v2 label,
  table and corridor fetch goes through. The pinned round-3 code itself is not edited. When an interactive request
  fails on memory or time (the failures restricted mode produces), the same image on the same grid is sent as a
  BATCH export to an Earth Engine asset, waited for, read back with one cheap computePixels, and the asset deleted.
  The pixels are therefore the same image on the same grid; only the route changes.
- `round3_active()` reports whether round 3 is using Earth Engine (a round-3 process is running, or the shared
  lock is held by someone else), so v2 workers pause between units instead of interleaving.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import time

LOCK = "/private/tmp/geowatch-change-round2-ee.lock"
FOLDER = "m678v2_batch"
FALLBACK_ON = ("memory limit", "timed out", "timeout", "too many concurrent", "computation was cancelled",
               "capacity exceeded", "eetimeout")
BATCH_WAIT_S = 3 * 3600
_state = {"on": False, "project": None}


def _fallback(e: BaseException) -> bool:
    s = f"{type(e).__name__} {e}".lower()
    return any(k in s for k in FALLBACK_ON)


def _ensure_folder(ee, project):
    path = f"projects/{project}/assets/{FOLDER}"
    try:
        ee.data.getAsset(path)
    except Exception:            # noqa: BLE001
        ee.data.createAsset({"type": "FOLDER"}, path)
    return path


def batch_pixels(ee, img, transform, shape, crs, label):
    import numpy as np
    import susceptibility.hydro_rasters as HR
    from ee_timeout import call
    project = _state["project"]
    folder = _ensure_folder(ee, project)
    H, W = shape
    grid = HR.ee_grid(transform, shape, crs)
    expr = img.unmask(HR.NODATA).toFloat()
    key = hashlib.sha1((expr.serialize() + json.dumps(grid, sort_keys=True)).encode()).hexdigest()[:24]
    aid = f"{folder}/px_{key}"
    try:
        ee.data.getAsset(aid)
        have = True
    except Exception:            # noqa: BLE001
        have = False
    if not have:
        task = ee.batch.Export.image.toAsset(
            image=expr, description=f"m678v2_{key}"[:100], assetId=aid, crs=crs,
            crsTransform=[transform.a, 0, transform.c, 0, transform.e, transform.f],
            dimensions=f"{W}x{H}", maxPixels=int(1e10), pyramidingPolicy={".default": "sample"})
        task.start()
        t0 = time.time()
        while True:
            st = task.status()
            if st["state"] == "COMPLETED":
                break
            if st["state"] in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"batch export [{label}] {st['state']}: {st.get('error_message', '')[:200]}")
            if time.time() - t0 > BATCH_WAIT_S:
                task.cancel()
                raise TimeoutError(f"batch export [{label}] not done after {BATCH_WAIT_S} s")
            time.sleep(30)
        print(f"  EE BATCH ok [{label}] in {time.time() - t0:.0f}s", flush=True)
    arr = call(lambda: ee.data.computePixels({"expression": ee.Image(aid), "fileFormat": "NUMPY_NDARRAY",
                                              "grid": grid}), timeout=HR.EE_TIMEOUT_S, retries=HR.EE_RETRIES,
               label=f"{label} (from batch asset)")
    try:
        ee.data.deleteAsset(aid)
    except Exception:            # noqa: BLE001
        pass
    return {b: np.where(arr[b] == HR.NODATA, np.nan, arr[b]).astype(np.float64) for b in arr.dtype.names}


def install(ee, project):
    if _state["on"]:
        return
    import susceptibility.hydro_rasters as HR
    _state["project"] = project
    try:
        _ensure_folder(ee, project)
    except Exception as e:       # noqa: BLE001
        print(f"  EE batch export unavailable (no asset destination: {str(e)[:90]}); interactive only", flush=True)
        _state["on"] = True
        return
    orig = HR.compute_pixels

    def compute_pixels(img, transform, shape, crs, label, timeout=HR.EE_TIMEOUT_S):
        try:
            return orig(img, transform, shape, crs, label, timeout)
        except Exception as e:   # noqa: BLE001
            if not _fallback(e):
                raise
            print(f"  EE -> BATCH [{label}]: {str(e)[:100]}", flush=True)
            return batch_pixels(ee, img, transform, shape, crs, label)

    HR.compute_pixels = compute_pixels
    _state["on"] = True


def round3_active() -> bool:
    """True while round 3 uses Earth Engine: a round-3 process runs, or another client holds the shared lock."""
    try:
        out = subprocess.run(["pgrep", "-f", "[Pp]ython.*flood_round3"], capture_output=True, text=True).stdout.split()
        if [p for p in out if int(p) != os.getpid()]:
            return True
    except Exception:            # noqa: BLE001
        pass
    with open(LOCK, "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True


def wait_for_round3(log=print, poll_s=300):
    """Between units: pause while round 3 is using Earth Engine (owner decision 2026-11-28)."""
    while round3_active():
        log(f"{time.strftime('%H:%M:%S')} round 3 is using Earth Engine: paused", flush=True)
        time.sleep(poll_s)
