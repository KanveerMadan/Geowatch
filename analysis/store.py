"""
Permanent result IDs and the never-recompute cache.

A result's ID is a hash of what determines it: the AOI box, the resolved
date window, the boundary layer, and model_version's version_id (code commit
+ uncommitted diff + every artifact hash). The same request at the same
version therefore gets the same ID, and a stored ID is served, never
recomputed. A new commit or a new producer artifact is a new version and a
new ID; the old result stays where it is.

Stored results are immutable: put() refuses to overwrite.

Only a COMPLETE run is stored -- every stage "ok". A run with a timed-out or
failed stage is returned to the caller unstored, so retrying can produce the
complete one; storing it would make the gap permanent under an ID that says
nothing changed (item 38, C27).

Layout:  data/results/<result_id>/result.json   the contract-shaped result
                                 /units.json    compact ward units
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading

from analysis.contract import sha256_json

RESULTS_ROOT = os.path.join("data", "results")
RESULT_ID_PATTERN = re.compile(r"r[0-9a-f]{24}")
BBOX_DECIMALS = 6

_locks: dict = {}
_locks_guard = threading.Lock()


def result_id(bbox, window: dict, boundary_id: str | None, version_id: str) -> str:
    """aoi_label and the window's mode are deliberately NOT in the key: they
    do not change what is computed."""
    key = {"bbox": [round(float(v), BBOX_DECIMALS) for v in bbox],
           "start": window["start"], "end": window["end"],
           "boundary_layer_id": boundary_id, "version_id": version_id}
    return "r" + sha256_json(key)[:24]


def valid_id(rid: str) -> bool:
    return isinstance(rid, str) and RESULT_ID_PATTERN.fullmatch(rid) is not None


def _dir(rid: str, root: str) -> str:
    if not valid_id(rid):
        raise ValueError("invalid result id")
    return os.path.join(root, rid)


def get(rid: str, root: str = RESULTS_ROOT) -> dict | None:
    p = os.path.join(_dir(rid, root), "result.json")
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


def get_units(rid: str, root: str = RESULTS_ROOT) -> dict | None:
    p = os.path.join(_dir(rid, root), "units.json")
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


MAP_NAME_PATTERN = re.compile(r"[a-z0-9_]{1,64}")


def get_map(rid: str, name: str, root: str = RESULTS_ROOT) -> bytes | None:
    if not MAP_NAME_PATTERN.fullmatch(name or ""):
        raise ValueError("invalid map name")
    p = os.path.join(_dir(rid, root), "maps", f"{name}.png")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as fh:
        return fh.read()


def put(rid: str, result: dict, units: dict, root: str = RESULTS_ROOT,
        maps: dict | None = None) -> None:
    """Write once, atomically: a complete directory appears or nothing does."""
    final = _dir(rid, root)
    if os.path.exists(final):
        raise FileExistsError(f"result {rid} is stored and immutable")
    os.makedirs(root, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=f".{rid}.", dir=root)
    try:
        with open(os.path.join(tmp, "result.json"), "w") as fh:
            json.dump(result, fh)
        with open(os.path.join(tmp, "units.json"), "w") as fh:
            json.dump(units, fh)
        if maps:
            os.makedirs(os.path.join(tmp, "maps"))
            for name, png in maps.items():
                if not MAP_NAME_PATTERN.fullmatch(name):
                    raise ValueError(f"invalid map name {name!r}")
                with open(os.path.join(tmp, "maps", f"{name}.png"), "wb") as fh:
                    fh.write(png)
        os.rename(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def list_results(root: str = RESULTS_ROOT) -> list:
    if not os.path.isdir(root):
        return []
    rows = []
    for rid in sorted(os.listdir(root)):
        if not valid_id(rid):
            continue
        r = get(rid, root)
        if r is None:
            continue
        rows.append({"result_id": rid, "aoi_label": r["request"]["aoi_label"],
                     "bbox": r["request"]["bbox"], "window": r["request"]["window"],
                     "boundary_layer_id": r["request"].get("boundary_layer_id"),
                     "version_id": r["model_version"]["version_id"],
                     "created_utc": r.get("created_utc"),
                     "validation_summary": r.get("validation_summary")})
    return sorted(rows, key=lambda x: x["created_utc"] or "", reverse=True)


def incomplete_stages(result: dict) -> dict:
    return {k: v["status"] for k, v in result.get("stages", {}).items() if v["status"] != "ok"}


def _lock(rid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(rid, threading.Lock())


def analyze(bbox, start, end, *, name: str, boundary_id: str | None = None, producer=None,
            root: str = RESULTS_ROOT, runner=None, commit: dict | None = None,
            run_kwargs: dict | None = None) -> dict:
    """Serve a stored result, or run, store (if complete) and return it.

    Returns {"result_id", "cached", "stored", "result"} plus, when unstored,
    "not_stored_because"."""
    from analysis.fractions import StandInFractions
    from analysis.run import resolve_window, run_analysis, version_for
    producer = producer or StandInFractions()
    runner = runner or run_analysis
    window = resolve_window(start, end)
    mv = version_for(producer, commit)
    rid = result_id(bbox, window, boundary_id, mv["version_id"])
    with _lock(rid):
        hit = get(rid, root)
        if hit is not None:
            return {"result_id": rid, "cached": True, "stored": True, "result": hit}
        result, units = runner(bbox, window, name=name, producer=producer,
                               boundary_id=boundary_id, commit=commit, **(run_kwargs or {}))
        if result["model_version"]["version_id"] != mv["version_id"]:
            raise RuntimeError("the run's model_version differs from the one it was keyed on")
        maps = result.pop("_maps", {})
        result["result_id"] = rid
        gaps = incomplete_stages(result)
        if gaps:
            result["result_id"] = None
            return {"result_id": None, "cached": False, "stored": False, "result": result,
                    "not_stored_because": gaps}
        put(rid, result, units, root, maps=maps)
        return {"result_id": rid, "cached": False, "stored": True, "result": result}
