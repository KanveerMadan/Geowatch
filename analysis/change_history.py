"""Store a dated change record in bounded spatial tiles. All read paths are offline."""
from __future__ import annotations

import io
import json
import math
import sqlite3
import tempfile
import time
import warnings
import zlib
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np

from analysis.change_semantics import LAND_COVER

SCHEMA = "geowatch.change-history/1"
STATES = ("change_detected", "candidate_change", "no_change_detected", "insufficient_observation")
SIGNALS = ("ndvi", "mndwi", "ndbi", "vv_db", "vh_db", "building_presence", *LAND_COVER)
COLUMNS_PER_BLOCK = 32   # one cell read decodes at most 32 columns, independently of AOI size


def _json(obj):
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)


def _pack(obj):
    return zlib.compress(_json(obj).encode(), level=1)


def _unpack(blob):
    return json.loads(zlib.decompress(blob))


def _tile_arrays(records, offset, size):
    """One small group of cell columns at a time, even for long acquisition histories."""
    keys = sorted({k for rec in records for k in rec["values"]})
    arrays = {k: np.full((len(records), size), np.nan, np.float32) for k in [*keys, "coverage"]}
    for i, rec in enumerate(records):
        arrays["coverage"][i] = rec["coverage"][offset:offset + size]
        for k, values in rec["values"].items():
            arrays[k][i] = values[offset:offset + size]
    return arrays


def _observations(catalogue, arrays, pos, support_id):
    rows = []
    for i, meta in enumerate(catalogue):
        values = {k: float(a[i, pos]) for k, a in arrays.items()
                  if k != "coverage" and np.isfinite(a[i, pos])}
        coverage = float(arrays["coverage"][i, pos])
        rows.append({**meta, "coverage": coverage if math.isfinite(coverage) else 0.0,
                     "values": values, "support_id": support_id})
    return rows


def _save_signals(db, tile_id, offset, arrays):
    for key, array in arrays.items():
        buf = io.BytesIO()
        np.save(buf, array, allow_pickle=False)
        db.execute("INSERT INTO signals VALUES (?,?,?,?)", (tile_id, offset, key, zlib.compress(buf.getvalue(), 1)))


def _load_signals(db, tile_id, offset, key=None):
    query = "SELECT signal, samples FROM signals WHERE tile_id=? AND col_offset=?"
    args = (tile_id, offset)
    if key is not None:
        query += " AND signal=?"
        args += (key,)
    return {k: np.load(io.BytesIO(zlib.decompress(blob)), allow_pickle=False)
            for k, blob in db.execute(query, args)}


def run_history(layer, epochs, *, open_provider=None, detector=None, archive_root=None,
                cache_dir=None, sources=None, timeout_s=None, policy=None, surveys=None,
                interpreter=None):
    """Analyze tiles serially. The returned TemporaryDirectory owns the finished database."""
    from vector.change_detection import DetectionConfig, MODEL_VERSION, detect_cell
    from vector.change_observations import SOURCES, open_history
    from analysis.stages import STAGE_TIMEOUT_S
    from analysis.change_surveys import configured_surveys
    from analysis.change_semantics import attach_interpretations, configured_interpreter, configured_sources

    (history_start, _), (start, end) = epochs["s2"]
    deadline = time.monotonic() + (STAGE_TIMEOUT_S["change"] if timeout_s is None else timeout_s)
    def cancelled():
        return time.monotonic() >= deadline

    surveys = configured_surveys() if surveys is None else surveys
    interpreter = configured_interpreter() if interpreter is None else interpreter
    policy = policy or DetectionConfig()
    sources = configured_sources() if sources is None else tuple(sources)
    provider = (open_provider or open_history)(layer, history_start, end, cache_dir=cache_dir,
                                               sources=sources, cancelled=cancelled)
    archive = tempfile.TemporaryDirectory(prefix="gw-change-", dir=archive_root)
    geometry_rows = []
    counts = Counter(dict.fromkeys(STATES, 0))
    areas = Counter()
    sources_seen = defaultdict(list)
    signals = set()
    event_count = 0
    survey_totals = {}
    try:
        with closing(sqlite3.connect(Path(archive.name) / "history.sqlite")) as db:
            db.executescript("""
                CREATE TABLE tiles (tile_id INTEGER PRIMARY KEY, catalogue BLOB NOT NULL);
                CREATE TABLE signals (tile_id INTEGER, col_offset INTEGER, signal TEXT, samples BLOB NOT NULL,
                                      PRIMARY KEY(tile_id,col_offset,signal));
                CREATE TABLE cells (unit_index INTEGER PRIMARY KEY, cell_id TEXT UNIQUE NOT NULL,
                                    support_id TEXT NOT NULL, tile_id INTEGER, position INTEGER, detail BLOB NOT NULL);
                CREATE INDEX cell_by_tile ON cells(tile_id, position);
                CREATE TABLE run (detector TEXT NOT NULL, policy BLOB NOT NULL, interpreter BLOB);
                CREATE TABLE surveys (name TEXT PRIMARY KEY, joint BLOB, gain BLOB, loss BLOB);
            """)
            db.execute("INSERT INTO run VALUES (?,?,?)", (MODEL_VERSION, _pack(asdict(policy)),
                       _pack(interpreter.artifact) if interpreter else None))
            if surveys:
                from shapely.geometry import box
                for _, _, name, shapes in surveys.projected_pairs(box(*layer.bbox), layer.crs, start, end):
                    clipped = [g.intersection(layer.aoi) for g in shapes]
                    if clipped[0].area > 0:
                        db.execute("INSERT INTO surveys VALUES (?,?,?,?)", (name, *(g.wkb for g in clipped)))
            db.commit()
            for tile_id, tile in enumerate(provider.tiles()):
                for row in tile["diagnostics"]:
                    sources_seen[row["source"]].append(row)
                catalogue = [{k: v for k, v in rec.items() if k not in ("values", "coverage")}
                             for rec in tile["observations"]]
                db.execute("INSERT INTO tiles VALUES (?,?)", (tile_id, _pack(catalogue)))
                for pos, cell in enumerate(tile["cells"]):
                    if cancelled():
                        raise TimeoutError("change history deadline reached; cached source batches can be reused")
                    local = pos % COLUMNS_PER_BLOCK
                    if local == 0:
                        size = min(COLUMNS_PER_BLOCK, len(tile["cells"]) - pos)
                        arrays = _tile_arrays(tile["observations"], pos, size)
                        signals.update(set(arrays) - {"coverage"})
                        _save_signals(db, tile_id, pos, arrays)
                    rows = _observations(catalogue, arrays, local, cell["support_id"])
                    detail = (detector or detect_cell)(cell["cell_id"], rows, start=start, end=end, config=policy)
                    attach_interpretations(detail["events"], interpreter, observations=rows, monitoring_start=start)
                    survey = surveys.measure(cell["geometry"], layer.crs, start, end) if surveys else {}
                    for name, stats in survey.items():
                        total = survey_totals.setdefault(name, Counter())
                        total.update({k: stats[k] for k in ("gain_m2", "loss_m2", "net_m2", "joint_area_m2")})
                    cell_row = {**cell, "state": detail["state"], "event_count": len(detail["events"])}
                    if survey:
                        cell_row["survey_measurements"] = survey
                        detail["survey_measurements"] = survey
                    geometry_rows.append(cell_row)
                    counts[detail["state"]] += 1
                    areas[detail["state"]] += cell["area_m2"]
                    event_count += len(detail["events"])
                    db.execute("INSERT INTO cells VALUES (?,?,?,?,?,?)",
                               (cell["unit_index"], cell["cell_id"], cell["support_id"], tile_id, pos, _pack(detail)))
                db.commit()
    except BaseException:
        archive.cleanup()
        raise
    source_status = []
    for source, tiles in sorted(sources_seen.items()):
        statuses = Counter(t["status"] for t in tiles)
        errors = sorted({e for t in tiles for e in t.get("errors", [])})
        status = ("failed" if statuses["failed"] == len(tiles) else "partial"
                  if errors or statuses["partial"] or statuses["failed"] else "available"
                  if statuses["available"] else "no_acquisitions")
        source_status.append({"source": source, "status": status, "errors": errors, "tiles": len(tiles),
                              "acquisition_tile_pairs": sum(t.get("acquisitions", 0) for t in tiles),
                              "usable_acquisition_tile_pairs": sum(t.get("usable_acquisitions", 0) for t in tiles),
                              "tile_status_counts": dict(statuses)})
    summary = {"schema": SCHEMA, "period": [start, end], "training_period": [history_start, start],
               "end_exclusive": True, "mode": "prospective", "grid_cell_m": 100, "counts": dict(counts),
               "event_count": event_count, "support_area_m2": dict(areas), "signals": sorted(signals),
               "source_status": source_status, "sources": {k: SOURCES[k] for k in sources},
               "alerts_enabled": False,
               "detector": MODEL_VERSION, "operating_parameters": asdict(policy),
               "survey_measurements": {k: dict(v) for k, v in survey_totals.items()},
               "survey_sources": surveys.provenance if surveys else [],
               "semantic_model": interpreter.provenance if interpreter else None}
    return {"schema": SCHEMA, "summary": summary, "archive": archive,
            "block": {"schema": SCHEMA, "status": "available" if geometry_rows else "unavailable",
                      "crs": layer.crs.to_string(), "grid_cell_m": 100, "cells": geometry_rows}}


def database(path):
    # mode=ro also prevents accidentally creating a blank archive on an old result.
    return closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro&immutable=1", uri=True))


def cell_detail(path, index, *, replay=None):
    with database(path) as db:
        record = db.execute("""SELECT c.cell_id, c.support_id, c.tile_id, c.position, c.detail, t.catalogue
                               FROM cells c JOIN tiles t USING (tile_id) WHERE c.unit_index=?""",
                            (index,)).fetchone()
        if not record:
            return None
        cell_id, support_id, tile, pos, blob, meta = record
        local = pos % COLUMNS_PER_BLOCK
        observations = _observations(_unpack(meta), _load_signals(db, tile, pos-local), local, support_id)
        detail = _unpack(blob)
        if replay:
            from vector.change_detection import DetectionConfig, MODEL_VERSION, detect_cell
            from analysis.change_semantics import Interpreter, attach_interpretations
            version, policy, model = db.execute("SELECT detector,policy,interpreter FROM run").fetchone()
            if version != MODEL_VERSION:
                raise ValueError("the archived detector version is unavailable for replay")
            observations = [r for r in observations if r["date"] <= replay["as_of"]]
            detail = detect_cell(cell_id, observations, config=DetectionConfig(**_unpack(policy)), **replay)
            attach_interpretations(detail["events"], Interpreter(_unpack(model)) if model else None,
                                   observations=observations, monitoring_start=replay["start"])
        return {**detail, "unit_index": index, "cell_id": cell_id, "observations": observations}


def replay_options(summary, start, end, mode, as_of):
    if not any((start, end, mode, as_of)):
        return None
    if not start or not end:
        raise ValueError("replay requires start and end")
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    lower, upper = date.fromisoformat(summary["training_period"][0]), date.fromisoformat(summary["period"][1])
    mode = mode or "prospective"
    if mode not in ("prospective", "retrospective") or not lower <= a < b <= upper:
        raise ValueError("choose a monitoring interval inside the stored history and a valid replay mode")
    from datetime import timedelta
    cutoff = date.fromisoformat(as_of) if as_of else b - timedelta(days=1)
    if not a <= cutoff < (upper if mode == "retrospective" else b):
        raise ValueError("the evidence cutoff is outside the requested replay bounds")
    return {"start": a.isoformat(), "end": b.isoformat(), "as_of": cutoff.isoformat(), "mode": mode}


def _comparison(catalogue, samples, windows, size):
    """Choose one common source/track per cell, preferring more distinct dates in the weaker window."""
    results = [{"state": "insufficient_observation", "delta": None, "track": None,
                "n_before": 0, "n_after": 0} for _ in range(size)]
    if samples is None:
        return results
    groups = defaultdict(lambda: defaultdict(list))
    for i, rec in enumerate(catalogue):
        versions = ()
        if rec["source"] == "dynamic_world":
            versions = tuple(sorted({(str(s.get("dynamicworld_algorithm_version", "")),
                                      str(s.get("qa_algorithm_version", ""))) for s in rec.get("scenes", [])}))
        groups[(rec["source"], rec["track"], versions)][rec["date"]].append(i)
    best = [(-1, -1)] * size
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
        for (source, track, versions), days in sorted(groups.items()):
            medians, counts = [], []
            for start, end in windows:
                # Same-day overlaps/reprocessings get one vote.
                daily = [np.nanmedian(samples[idx], axis=0) for day, idx in days.items() if start <= day < end]
                if not daily:
                    counts.append(np.zeros(size, dtype=int))
                    medians.append(np.full(size, np.nan))
                    continue
                values = np.stack(daily)
                counts.append(np.isfinite(values).sum(axis=0))
                medians.append(np.nanmedian(values, axis=0))
            for pos in np.flatnonzero((counts[0] > 0) | (counts[1] > 0)):
                na, nb = int(counts[0][pos]), int(counts[1][pos])
                rank = (min(na, nb), na + nb)
                if rank <= best[pos]:
                    continue
                best[pos] = rank
                before, after = (float(v[pos]) for v in medians)
                common = {"track": track, "source": source, "n_before": na, "n_after": nb,
                          "median_before": before if na else None, "median_after": after if nb else None}
                if versions:
                    common["model_qa_versions"] = versions
                if not (na and nb):
                    results[pos] = {**common, "state": "insufficient_observation", "delta": None}
                    continue
                delta = after - before
                results[pos] = {**common, "state": "increase" if delta > 0 else "decrease" if delta < 0 else "unchanged",
                                "delta": delta}
    return results


def compare(path, block, summary, before, after, signal):
    if signal not in SIGNALS:
        raise ValueError("unknown measurement")
    a, b, c, d = [date.fromisoformat(x) for x in (*before, *after)]
    lower, upper = summary["training_period"][0], summary["period"][1]
    if not (date.fromisoformat(lower) <= a < b <= c < d <= date.fromisoformat(upper)):
        raise ValueError("select two ordered, non-overlapping windows within the stored history")
    before, after = (a.isoformat(), b.isoformat()), (c.isoformat(), d.isoformat())
    by_id = {row["unit_index"]: row for row in block["cells"]}
    features = []
    with database(path) as db:
        for tile, meta in db.execute("SELECT tile_id,catalogue FROM tiles ORDER BY tile_id"):
            indices = [r[0] for r in db.execute(
                "SELECT unit_index FROM cells WHERE tile_id=? ORDER BY position", (tile,))]
            catalogue = _unpack(meta)
            records = []
            for offset in range(0, len(indices), COLUMNS_PER_BLOCK):
                size = min(COLUMNS_PER_BLOCK, len(indices) - offset)
                samples = _load_signals(db, tile, offset, signal).get(signal)
                records.extend(_comparison(catalogue, samples, (before, after), size))
            for i, row in zip(indices, records):
                cell = by_id[i]
                features.append({"type": "Feature", "id": i, "geometry": cell["geometry"],
                                 "properties": {"unit_index": i, "cell_id": cell["cell_id"],
                                                "signal": signal, **row}})
    return {"type": "FeatureCollection", "features": features, "before": before, "after": after,
            "signal": signal, "method": "signed difference of same-track daily medians", "end_exclusive": True}


def zone_summary(block, geometry, path=None, survey_sources=()):
    import pyproj
    from shapely import from_wkb
    from analysis.change_surveys import measure_geometry
    from shapely.geometry import shape
    from shapely.ops import transform
    project = pyproj.Transformer.from_crs("EPSG:4326", block["crs"], always_xy=True).transform
    zone_ll = shape(geometry)
    zone = transform(project, zone_ll)
    totals = Counter(dict.fromkeys(STATES, 0.0))
    for cell in block["cells"]:
        geometry_ll = shape(cell["geometry"])
        if zone_ll.intersects(geometry_ll):
            overlap = zone.intersection(transform(project, geometry_ll))
            totals[cell["state"]] += overlap.area
    monitored = sum(totals.values())
    surveys = {}
    if path and survey_sources:
        with database(path) as db:
            for name, joint, gain, loss in db.execute("SELECT name,joint,gain,loss FROM surveys"):
                stats = measure_geometry(zone, [from_wkb(v) for v in (joint, gain, loss)])
                if stats:
                    surveys[name] = stats
    return {"support_area_m2": dict(totals), "zone_area_m2": zone.area,
            "survey_measurements": surveys, "survey_sources": [s for s in survey_sources if s["name"] in surveys],
            "monitored_area_m2": monitored, "outside_record_m2": max(0.0, zone.area - monitored),
            "basis": "intersection with monitored cell footprints, grouped by detection state"}
