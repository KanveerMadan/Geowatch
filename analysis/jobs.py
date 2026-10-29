"""
Analysis jobs: POST starts a run and returns at once; GET reports it as it goes.

    job:    queued -> running -> complete | failed
    stage:  running -> ok | failed | timeout      (analysis/stages.py's outcomes)

A job wraps store.analyze, so the cache and the store's rules are unchanged:
an area already stored is a job born complete, with no run; a run with any
stage not ok completes UNSTORED (result_id None, not_stored_because set).
`partial` holds each output group as the run finalises it, in the result
contract's own shape (analysis/run.py `progress`); the final `result` is the
same result /api/analyze returns.

A job is `failed` only when the run itself raised (the road layer or the
fraction producer did not finish, so there is nothing to report); `error`
then names the exception class.
"""
from __future__ import annotations

import copy
import re
import secrets
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from analysis import store

# Fixed 2026-10-29 with the job API, before any real-data run through it.
MAX_CONCURRENT_RUNS = 2       # each run is EE- and Overpass-bound; more would queue at them anyway
MAX_JOBS_KEPT = 200           # oldest finished jobs are forgotten first
JOB_ID_PATTERN = re.compile(r"j[0-9a-f]{24}")

# shortcut: jobs live in this process's memory, so a restart forgets them
# (stored results stay); move to a shared store if the API runs several workers.
_jobs: "OrderedDict[str, dict]" = OrderedDict()
_guard = threading.Lock()
_pool = ThreadPoolExecutor(MAX_CONCURRENT_RUNS, thread_name_prefix="analysis-job")


def valid_id(jid: str) -> bool:
    return isinstance(jid, str) and JOB_ID_PATTERN.fullmatch(jid) is not None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get(jid: str) -> dict | None:
    with _guard:
        j = _jobs.get(jid)
        return copy.deepcopy(j) if j is not None else None


def _update(jid: str, fn) -> None:
    with _guard:
        fn(_jobs[jid])


def _remember(job: dict) -> None:
    with _guard:
        _jobs[job["job_id"]] = job
        while len(_jobs) > MAX_JOBS_KEPT:
            old = next((k for k, v in _jobs.items() if v["status"] in ("complete", "failed")), None)
            if old is None:
                break
            del _jobs[old]


def _on_event(jid: str, event: dict) -> None:
    def apply(j):
        if "outputs" in event:
            j["partial"].update(event["outputs"])
        elif "stage" in event:
            j["stages"][event["stage"]] = {k: v for k, v in event.items() if k != "stage"}
    _update(jid, apply)


def _finish(jid: str, out: dict) -> None:
    def apply(j):
        r = out["result"]
        j.update(status="complete", finished_utc=_now(), result_id=out["result_id"],
                 cached=out["cached"], stored=out["stored"], result=r,
                 stages=r.get("stages", j["stages"]), partial={},
                 not_stored_because=out.get("not_stored_because"))
    _update(jid, apply)


def _run(jid: str, args: tuple, kw: dict, analyze) -> None:
    _update(jid, lambda j: j.update(status="running", started_utc=_now()))
    try:
        out = analyze(*args, run_kwargs={"progress": lambda e: _on_event(jid, e)}, **kw)
    except Exception as e:                       # noqa: BLE001 -- recorded, never swallowed
        _update(jid, lambda j: j.update(status="failed", finished_utc=_now(),
                                        error={"exception_class": type(e).__name__,
                                               "message": str(e)[:500]}))
        return
    _finish(jid, out)


def submit(bbox, start, end, *, name: str, boundary_id: str | None = None,
           root: str = store.RESULTS_ROOT, executor=None, analyze=None, **analyze_kw) -> dict:
    """Start a job and return its first snapshot. A stored area is returned
    complete, without queueing a run."""
    analyze = analyze or store.analyze
    jid = "j" + secrets.token_hex(12)
    job = {"job_id": jid, "status": "queued", "created_utc": _now(),
           "request": {"bbox": list(bbox), "start_date": start, "end_date": end,
                       "aoi_label": name, "boundary_layer_id": boundary_id},
           "stages": {}, "partial": {}, "result_id": None, "result": None,
           "cached": False, "stored": False, "error": None}
    rid, hit = store.cached(bbox, start, end, boundary_id=boundary_id, root=root,
                            producer=analyze_kw.get("producer"), commit=analyze_kw.get("commit"))
    if hit is not None:
        job.update(status="complete", finished_utc=job["created_utc"], result_id=rid,
                   cached=True, stored=True, result=hit, stages=hit.get("stages", {}))
        _remember(job)
        return get(jid)
    _remember(job)
    kw = {"name": name, "boundary_id": boundary_id, "root": root, **analyze_kw}
    (executor or _pool).submit(_run, jid, (bbox, start, end), kw, analyze)
    return get(jid)
