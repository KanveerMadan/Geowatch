"""
Stage runner: every external call in the analysis pipeline runs inside a
stage with an explicit timeout, and its outcome is recorded, never guessed.

Two limits on every Earth Engine stage, because neither covers the other:

  * ee.data.setDeadline(timeout) -- EE's own per-request HTTP deadline.
    Its default is no limit (C56: a reduction stalled for hours without
    raising). Callees can reset it (vector.sources.fetch_open_buildings
    restores 0 in its finally), so it is re-set at the start of every stage.
  * a wall-clock join on a daemon thread -- bounds the stage as a whole,
    however many requests it makes, and survives a callee resetting the
    deadline. An abandoned thread cannot be killed; daemon=True means it
    cannot keep the interpreter alive (same design as ee_timeout.py).

A stage returns {"status": "ok" | "timeout" | "failed", ...}. A timeout is
its own status and never becomes a value (item 38, C27).
"""
from __future__ import annotations

import threading
import time

# Seconds. Fixed 2026-10-28 before any real-data run of this pipeline.
STAGE_TIMEOUT_S = {
    "road_layer": 1200,          # Overpass clauses + Open Buildings download
    "s2_composite": 600,
    "observability": 600,
    "dem": 300,
    "waterways": 300,
    "context": 240,              # each AOI-wide context layer (HAND, CHIRPS, ...)
    "change": 1800,              # four S2 composites + three OB Temporal years
}


class StageTimeout(RuntimeError):
    pass


def _set_ee_deadline(ms: int) -> None:
    try:
        import ee
        ee.data.setDeadline(ms)
    except Exception:            # noqa: BLE001 -- ee absent or not initialised
        pass


def run_stage(name: str, fn, *args, timeout_s: float, **kwargs) -> dict:
    """Run fn(*args, **kwargs) under both limits. Never raises for the
    callee's failure: the outcome is returned."""
    box = {}

    def target():
        _set_ee_deadline(int(timeout_s * 1000))
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as e:            # noqa: BLE001
            box["error"] = e

    t0 = time.time()
    th = threading.Thread(target=target, daemon=True, name=f"stage:{name}")
    th.start()
    th.join(timeout_s)
    elapsed = round(time.time() - t0, 1)
    if th.is_alive():
        print(f"[stage {name}] TIMEOUT after {elapsed}s", flush=True)
        return {"status": "timeout", "stage": name, "timeout_s": timeout_s,
                "elapsed_s": elapsed, "error": f"{name} exceeded {timeout_s}s"}
    _set_ee_deadline(0)
    if "error" in box:
        e = box["error"]
        print(f"[stage {name}] FAILED in {elapsed}s: {type(e).__name__}: {e}", flush=True)
        return {"status": "failed", "stage": name, "elapsed_s": elapsed,
                "exception_class": type(e).__name__, "error": str(e)[:500]}
    print(f"[stage {name}] ok in {elapsed}s", flush=True)
    return {"status": "ok", "stage": name, "elapsed_s": elapsed, "value": box.get("value")}


def summary(outcome: dict) -> dict:
    """The outcome without its value, for the result's provenance."""
    return {k: v for k, v in outcome.items() if k != "value"}
