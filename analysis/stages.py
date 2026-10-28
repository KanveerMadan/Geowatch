"""
Stage runner: every external call in the analysis pipeline runs inside a
stage with an explicit timeout, and its outcome is recorded, never guessed.

Two limits on every Earth Engine stage, because neither covers the other:

  * ee.data.setDeadline -- EE's own per-request HTTP deadline,
    EE_REQUEST_DEADLINE_S for every request.
    Its default is no limit (C56: a reduction stalled for hours without
    raising). Callees can reset it (vector.sources.fetch_open_buildings
    restores 0 in its finally), so it is checked at the start of every stage.
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
    # item 26 Phase 1a: MERIT/FABDEM terrain + CHIRPS + a 10-year IMERG
    # percentile (314 s at one point; its one request has its own deadline,
    # hydro_rasters.IMERG_DEADLINE_S, C71)
    "hydro_rasters": 1500,
}


# One per-REQUEST deadline for every stage. A stage's own wall-clock limit is
# STAGE_TIMEOUT_S; this bounds each single EE request inside it. Kept constant
# so the client is rebuilt once per process, not once per stage. The one
# exception is the IMERG percentile request (C71), which sets its own longer
# deadline and puts this one back.
EE_REQUEST_DEADLINE_S = 240                 # = the shortest stage limit


class StageTimeout(RuntimeError):
    pass


def _set_ee_deadline(ms: int) -> None:
    """Set EE's request deadline on an initialised session, and only when it
    changes: setDeadline rebuilds the Cloud API client (about 2 s each), and
    on an uninitialised session there is no request to bound."""
    try:
        import ee
        if not ee.data.is_initialized() or ee.data._get_state().deadline_ms == ms:
            return
        ee.data.setDeadline(ms)
    except Exception:            # noqa: BLE001 -- ee absent
        pass


def run_stage(name: str, fn, *args, timeout_s: float, **kwargs) -> dict:
    """Run fn(*args, **kwargs) under both limits. Never raises for the
    callee's failure: the outcome is returned."""
    box = {}

    def target():
        _set_ee_deadline(EE_REQUEST_DEADLINE_S * 1000)
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as e:            # noqa: BLE001
            box["error"] = e

    t0 = time.time()
    th = threading.Thread(target=target, daemon=True, name=f"stage:{name}")
    th.start()
    th.join(timeout_s)
    elapsed = round(time.time() - t0, 1)
    # The deadline is left in place after the stage: the next stage sets its
    # own, and a bounded deadline is the safer leftover.
    if th.is_alive():
        print(f"[stage {name}] TIMEOUT after {elapsed}s", flush=True)
        return {"status": "timeout", "stage": name, "timeout_s": timeout_s,
                "elapsed_s": elapsed, "error": f"{name} exceeded {timeout_s}s"}
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
