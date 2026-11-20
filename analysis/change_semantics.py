"""Experimental transition interpretation, loaded from a local JSON artifact (no executable pickle)."""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median

SIGNALS = ("ndvi", "mndwi", "ndbi", "vv_db", "vh_db", "building_presence")
LAND_COVER = tuple("dw_" + k for k in ("water", "trees", "grass", "flooded_vegetation", "crops",
                                       "shrub_and_scrub", "built", "bare", "snow_and_ice"))
FEATURES = [f"{s}_{f}" for s in SIGNALS for f in ("seen", "baseline", "delta")] + [
    "radar_seen", "optical_seen", "evidence_days", "detections"] + [
    f"{s}_{f}" for s in LAND_COVER for f in ("seen", "score", "seasonal_difference")]
MODEL_SCHEMA = "geowatch.transition-gbdt/1"


def _cover_context(observations, monitoring_start):
    """Comparable historical class scores by viewing track, model generation and calendar month."""
    baseline = defaultdict(list)
    monitoring = []
    for row in observations:
        if row["source"] != "dynamic_world" or not row["values"]:
            continue
        versions = tuple(sorted({(str(s.get("dynamicworld_algorithm_version", "")),
                                  str(s.get("qa_algorithm_version", ""))) for s in row.get("scenes", [])}))
        key = (row["track"], versions, row["date"][5:7])
        if row["date"] < monitoring_start:
            for k, v in row["values"].items():
                if k in LAND_COVER:
                    baseline[key, k].append(v)
        else:
            monitoring.append((key, row))
    return {k: median(v) for k, v in baseline.items()}, monitoring


def attach_interpretations(events, interpreter, *, observations=(), monitoring_start=None):
    """Co-occurring signals add context, without counting them as confirmations.

    Use only overlapping abnormal observations available by this episode's last
    evidence date. Later follow-up can produce a different interpretation.
    """
    history, coverage = _cover_context(observations, monitoring_start) if events and monitoring_start else ({}, [])
    for event in events:
        start, cutoff = event["detected_on"], event["last_evidence_on"]
        own = {row["signal"] for row in event["signals"]}
        event["context_signals"] = [dict(signal) for other in events
            if other is not event and other["detected_on"] <= cutoff and other["last_evidence_on"] >= start
            for signal in other["signals"] if signal["signal"] not in own
            and start <= signal["observed_on"] <= cutoff]
        scores = defaultdict(list)
        for group, row in coverage:
            if start <= row["date"] <= cutoff:
                for key, value in row["values"].items():
                    if (group, key) in history:
                        scores[key].append((value, value - history[group, key], row["date"]))
        if scores:
            event["land_cover_context"] = {
                k: {"median_score": median(x[0] for x in values),
                    "seasonal_difference": median(x[1] for x in values),
                    "dates": sorted({x[2] for x in values})}
                for k, values in scores.items()}
        if interpreter:
            event["interpretation"] = {**interpreter.predict(event), "as_of": cutoff}


def feature_vector(event):
    """One strongest standardized departure per signal among the event's actual supporting tracks."""
    by_signal = {}
    for row in [*event["signals"], *event.get("context_signals", [])]:
        name = row["signal"]
        threshold, delta, baseline = row.get("threshold"), row.get("delta"), row.get("baseline")
        if name not in SIGNALS or any(v is None or not math.isfinite(v) for v in (threshold, delta, baseline)):
            continue
        strength = abs(delta) / max(abs(threshold), 1e-12)
        if name not in by_signal or by_signal[name][0] < strength:
            by_signal[name] = strength, float(baseline), float(delta)
    vector = []
    for name in SIGNALS:
        vector.extend([1.0, *by_signal[name][1:]] if name in by_signal else [0.0, 0.0, 0.0])
    duration = (date.fromisoformat(event["last_evidence_on"]) - date.fromisoformat(event["detected_on"])).days
    vector.extend([float(any(k.endswith("_db") for k in by_signal)),
                   float(bool(set(by_signal).intersection(("ndvi", "mndwi", "ndbi")))),
                   duration, event["detections"]])
    for name in LAND_COVER:
        score = event.get("land_cover_context", {}).get(name)
        vector.extend([1., score["median_score"], score["seasonal_difference"]] if score else [0., 0., 0.])
    return vector


def _tree(tree, x):
    node = 0
    while tree["left"][node] != -1:
        node = (tree["left"][node] if x[tree["feature"][node]] <= tree["threshold"][node]
                else tree["right"][node])
    return tree["value"][node]


class Interpreter:
    def __init__(self, artifact):
        if artifact["schema"] != MODEL_SCHEMA or artifact["features"] != FEATURES:
            raise ValueError("incompatible transition interpreter artifact")
        self.artifact = artifact
        self.provenance = {"schema": MODEL_SCHEMA, "training_hash": artifact["training_hash"],
                           "validation_status": "experimental",
                           "sha256": hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest()}

    def predict(self, event):
        x = feature_vector(event)
        supported = any(x[:len(SIGNALS)*3:3])
        if not supported or any(v < lo or v > hi for v, (lo, hi) in zip(x, self.artifact["ranges"])):
            return {"label": "unknown", "reason": "outside training feature range"}
        scores = [m["offset"] + m["rate"] * sum(_tree(t, x) for t in m["trees"])
                  for m in self.artifact["models"]]
        k = max(range(len(scores)), key=scores.__getitem__)
        return {"label": self.artifact["models"][k]["label"], "score": scores[k],
                "score_unit": "one-vs-rest boosting margin", "validation_status": "experimental"}


def configured_interpreter():
    path = os.environ.get("GEOWATCH_CHANGE_INTERPRETER")
    return Interpreter(json.loads(Path(path).read_text())) if path else None


def configured_sources():
    """Explicit source routing for an installation. The standalone command also accepts --sources."""
    from vector.change_observations import DEFAULT_SOURCES, SOURCES
    setting = os.environ.get("GEOWATCH_CHANGE_SOURCES")
    if setting is None:
        return DEFAULT_SOURCES
    selected = tuple(dict.fromkeys(k.strip() for k in setting.split(",") if k.strip()))
    if not selected or set(selected).difference(SOURCES):
        raise ValueError("GEOWATCH_CHANGE_SOURCES must list registered source names")
    return selected


def external_versions():
    """Each configured reference and model participates in the immutable result key."""
    from analysis.change_surveys import configured_surveys
    surveys, model = configured_surveys(), configured_interpreter()
    return {"schema": "geowatch.change-history/1", "sources": list(configured_sources()),
            "surveys": surveys.provenance if surveys else [],
            "interpreter": model.provenance if model else None}
