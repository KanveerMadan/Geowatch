"""
The long-job worker: a separate process from the web API.

SFINCS runs take tens of minutes to hours and gigabytes of memory; they must
never run inside the web process (which also serves reads and polls). This
is the stub of that worker: a queue protocol, a claim/finish loop and a
heartbeat, with no SFINCS handler yet. The flood branch's SFINCS code plugs
in as a handler (`HANDLERS["sfincs"]`) when it merges.

Queue: a directory (GEOWATCH_QUEUE_DIR, default data/queue) with

    pending/<job>.json   written by the API (atomic rename), {"kind", "params", ...}
    running/<job>.json   claimed by exactly one worker (os.rename is atomic)
    done/<job>.json      the job plus {"result": ...}
    failed/<job>.json    the job plus {"error": ...}
    worker.heartbeat     touched every loop; its age is the worker's health

A directory queue works when the API and the worker share a filesystem
(docker compose, one machine). On a platform where services cannot share a
disk (Render, Railway) the same protocol moves to an object store or Redis
before SFINCS is switched on; DEPLOY.md says so.

    python -m deploy.worker            run the loop
    python -m deploy.worker --once     process what is pending, then exit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
import traceback
import uuid

log = logging.getLogger("geowatch.worker")

QUEUE_DIR = os.getenv("GEOWATCH_QUEUE_DIR", os.path.join("data", "queue"))
POLL_S = float(os.getenv("GEOWATCH_WORKER_POLL_S", "5"))
STATES = ("pending", "running", "done", "failed")


class NotBuilt(RuntimeError):
    pass


def _sfincs_not_built(params: dict) -> dict:
    raise NotBuilt("SFINCS jobs are not wired into the worker yet (flood branch); "
                   "the job is recorded as failed, not dropped")


HANDLERS = {"sfincs": _sfincs_not_built}


def _paths(root):
    for s in STATES:
        os.makedirs(os.path.join(root, s), exist_ok=True)
    return {s: os.path.join(root, s) for s in STATES}


def enqueue(kind: str, params: dict, root: str = QUEUE_DIR) -> str:
    """Write a job atomically into pending/. Returns its id."""
    p = _paths(root)
    jid = "w" + uuid.uuid4().hex[:24]
    tmp = os.path.join(p["pending"], f".{jid}.tmp")
    with open(tmp, "w") as fh:
        json.dump({"id": jid, "kind": kind, "params": params, "enqueued_utc": time.time()}, fh)
    os.rename(tmp, os.path.join(p["pending"], f"{jid}.json"))
    return jid


def claim(root: str = QUEUE_DIR):
    """Move the oldest pending job to running/ and return it, or None. The
    rename is the lock: two workers cannot both claim one job."""
    p = _paths(root)
    names = sorted((n for n in os.listdir(p["pending"]) if n.endswith(".json")),
                   key=lambda n: os.path.getmtime(os.path.join(p["pending"], n)))
    for n in names:
        src, dst = os.path.join(p["pending"], n), os.path.join(p["running"], n)
        try:
            os.rename(src, dst)
        except FileNotFoundError:
            continue                                    # another worker took it
        with open(dst) as fh:
            return json.load(fh)
    return None


def finish(job: dict, *, result=None, error=None, root: str = QUEUE_DIR) -> str:
    p = _paths(root)
    state = "failed" if error is not None else "done"
    job = {**job, "finished_utc": time.time(),
           **({"error": error} if error is not None else {"result": result})}
    tmp = os.path.join(p[state], f".{job['id']}.tmp")
    with open(tmp, "w") as fh:
        json.dump(job, fh)
    os.rename(tmp, os.path.join(p[state], f"{job['id']}.json"))
    try:
        os.remove(os.path.join(p["running"], f"{job['id']}.json"))
    except FileNotFoundError:
        pass
    return state


def run_one(root: str = QUEUE_DIR, handlers=None) -> str | None:
    handlers = HANDLERS if handlers is None else handlers
    job = claim(root)
    if job is None:
        return None
    h = handlers.get(job.get("kind"))
    if h is None:
        return finish(job, error=f"no handler for kind {job.get('kind')!r}", root=root)
    try:
        return finish(job, result=h(job.get("params") or {}), root=root)
    except Exception as e:                              # recorded, never dropped
        log.error("job failed", extra={"fields": {"job": job["id"], "kind": job.get("kind")}})
        err = traceback.format_exc() if os.getenv("GEOWATCH_WORKER_TRACEBACKS") \
            else f"{type(e).__name__}: {e}"
        return finish(job, error=err, root=root)


def heartbeat(root: str = QUEUE_DIR) -> None:
    path = os.path.join(root, "worker.heartbeat")
    with open(path, "w") as fh:
        fh.write(str(time.time()))


def main(argv=None) -> int:
    from deploy import runtime
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)
    runtime.setup()
    _paths(QUEUE_DIR)
    log.info("worker up", extra={"fields": {"queue": QUEUE_DIR, "handlers": sorted(HANDLERS)}})
    while True:
        heartbeat()
        state = run_one()
        if state is None:
            if args.once:
                return 0
            time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
