"""Train a transition interpreter or score independent, dated review cases from stored cell details.

A case is one independently reviewed cell-period-target, with a complete observation of the
target in that interval. Each case points to an exported /change/cells/{index} JSON file.
See README.md for the manifest, sampling frame and admissible claims.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np

from analysis.change_semantics import FEATURES, MODEL_SCHEMA, Interpreter, feature_vector


def _date(s):
    return date.fromisoformat(s)


def read_cases(path, split=None):
    path = Path(path)
    cases = []
    ids, cases_seen, cells = set(), set(), {}
    register = defaultdict(list)
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        for key in ("id", "region", "block", "split", "cell_id", "period", "detail"):
            if not c.get(key):
                raise ValueError(f"missing case field {key}")
        if c["id"] in ids or c["split"] not in ("development", "heldout"):
            raise ValueError("duplicate ID or unrecognised split")
        ids.add(c["id"])
        if cells.setdefault(c["cell_id"], c["split"]) != c["split"]:
            raise ValueError("cell appears in both splits")
        if len(c["period"]) != 2 or _date(c["period"][0]) >= _date(c["period"][1]):
            raise ValueError("invalid reference period")
        register[c["split"]].append(c)
        if split and c["split"] != split:
            continue  # only registry metadata is needed from the other split
        if not all(c.get(k) for k in ("reference", "license", "target")):
            raise ValueError("reference provenance and target are required")
        key = (c["cell_id"], *c["period"], c["target"])
        if key in cases_seen:
            raise ValueError("duplicate reference cell, period and target")
        cases_seen.add(key)
        if c["state"] not in ("changed", "stable", "unobserved") or type(c.get("independent")) is not bool:
            raise ValueError("record reference observability and independence explicitly")
        detail = json.loads((path.parent / c["detail"]).read_text())
        if c["cell_id"] != detail["cell_id"] or c["period"] != detail["period"]:
            raise ValueError("cell detail does not match registered geography and time")
        if detail.get("mode") != "prospective" or detail["as_of"] >= detail["period"][1]:
            raise ValueError("alert evaluation needs prospective evidence inside the reviewed window")
        lo, hi = map(_date, detail["period"])
        if c["state"] == "changed":
            a, b = map(_date, c["onset"])
            if not lo <= a <= b < hi:
                raise ValueError("reference onset must lie in the reviewed window")
        cases.append((c, detail))
    dev, test = register["development"], register["heldout"]
    for key in ("region", "block"):
        if {c[key] for c in dev} & {c[key] for c in test}:
            raise ValueError(f"{key} appears in both splits")
    if dev and test and max(c["period"][1] for c in dev) > min(c["period"][0] for c in test):
        raise ValueError("held-out cases must follow the development periods")
    return cases


def _dump_tree(tree):
    t = tree.tree_
    return {"left": t.children_left.tolist(), "right": t.children_right.tolist(),
            "feature": t.feature.tolist(), "threshold": t.threshold.tolist(),
            "value": t.value[:, 0, 0].tolist()}


def fit(cases):
    from sklearn.ensemble import GradientBoostingClassifier
    from threadpoolctl import threadpool_limits
    x, labels, training, seen = [], [], [], set()
    regions, blocks, used_cells, ends = set(), set(), set(), []
    for c, d in cases:
        if c["split"] != "development" or not c["independent"] or c["state"] == "unobserved":
            continue
        # An interpreter reviews the specific candidate (including false candidates).
        # Merely sharing a date with a reference polygon cannot assign its cause.
        for event in d["events"]:
            label = c.get("event_labels", {}).get(event["event_id"])
            if label:
                if event["event_id"] in seen:
                    raise ValueError("candidate labelled more than once")
                seen.add(event["event_id"])
                regions.add(c["region"])
                blocks.add(c["block"])
                used_cells.add(d["cell_id"])
                ends.append(d["period"][1])
                x.append(feature_vector(event))
                labels.append(label)
                training.append([c["id"], c["reference"], event["event_id"], label, x[-1]])
    if len(set(labels)) < 2 or not {"other", "stable"}.intersection(labels):
        raise ValueError("training needs at least two reviewed labels including other or stable hard negatives")
    x, labels = np.asarray(x), np.asarray(labels)
    models = []
    # Shallow trees allow two-feature interactions. All settings are development defaults.
    with threadpool_limits(limits=1):
        for label in sorted(set(labels)):
            y = labels == label
            model = GradientBoostingClassifier(max_depth=2, random_state=0).fit(x, y)
            offset = float(np.log(y.mean() / (1 - y.mean())))
            models.append({"label": str(label), "offset": offset, "rate": model.learning_rate,
                           "trees": [_dump_tree(t[0]) for t in model.estimators_]})
    return {"schema": MODEL_SCHEMA, "features": FEATURES, "models": models,
            "training_hash": hashlib.sha256(json.dumps(training, sort_keys=True).encode()).hexdigest(),
            "ranges": np.column_stack([x.min(axis=0), x.max(axis=0)]).tolist(),
            "development": {"regions": sorted(regions), "blocks": sorted(blocks),
                            "cells": sorted(used_cells), "end": max(ends)},
            "n_training_candidates": len(x), "class_counts": dict(Counter(map(str, labels)))}


def _metrics(rows):
    counts = sum((r[0] for r in rows), Counter())
    def ratio(a, b):
        return a / b if b else None
    timings = [d for _, d in rows if d is not None]
    return {"cases": len(rows), "counts": dict(counts),
            "precision": ratio(counts["tp"], counts["tp"] + counts["fp"]),
            "recall_including_abstention": ratio(counts["tp"], counts["changed"]),
            "stable_false_positive_rate": ratio(counts["false_positive_cell"], counts["stable"]),
            "stable_false_positive_rate_among_judged": ratio(counts["false_positive_cell"], counts["judged_stable"]),
            "judged_share": ratio(counts["judged"], counts["changed"] + counts["stable"]),
            "median_confirmation_days_after_latest_reference_onset": float(np.median(timings)) if timings else None}


def evaluate(cases, interpreter=None):
    from vector.change_detection import SIGNALS
    groups = defaultdict(list)
    per_region = defaultdict(list)
    per_target = defaultdict(list)
    skipped = Counter()
    for c, d in cases:
        if c["split"] != "heldout":
            continue
        if interpreter:
            dev = interpreter.artifact["development"]
            if (c["region"] in dev["regions"] or c["block"] in dev["blocks"]
                    or d["cell_id"] in dev["cells"] or d["period"][0] < dev["end"]):
                raise ValueError("held-out case overlaps model development geography or time")
        if not c["independent"] or c["state"] == "unobserved":
            skipped["dependent_reference" if not c["independent"] else "unobserved_reference"] += 1
            continue
        counts = Counter({c["state"]: 1})
        selected = []
        for e in d["events"]:
            if not e.get("confirmed_on"):
                continue
            labels = {e["transition"]}
            detection_date = e["confirmed_on"]
            if interpreter:
                meaning = interpreter.predict(e)["label"]
                labels.add(meaning)
                if c["target"] == meaning:
                    detection_date = max(detection_date, e["last_evidence_on"])
            if c["target"] == "any" or c["target"] in labels:
                selected.append((e, detection_date))
        monitored = {s["signal"] for s in d["series"] if s["status"] == "observed"}
        required = set(c.get("signals", [])) or {k for k, (name, _) in SIGNALS.items()
                    if c["target"] in (name + "_gain", name + "_loss")}
        if c["target"] != "any" and not required:
            raise ValueError("declare the required signals for this semantic target")
        judged = bool(selected) or (required.issubset(monitored) if required else bool(monitored))
        counts["judged"] = int(judged)
        lag, hits = None, []
        if c["state"] == "changed":
            a, b = c["onset"]
            for e, ready in selected:
                # Detector onset is (after, by]; the reference bracket is inclusive.
                if (e["onset"]["after"] is None or e["onset"]["after"] < b) and e["onset"]["by"] >= a:
                    hits.append(ready)
            if hits:
                counts["tp"] = 1
                lag = (_date(min(hits)) - _date(b)).days
        else:
            counts["false_positive_cell"] = int(bool(selected))
            counts["judged_stable"] = int(judged)
        counts["fp"] = len(selected) - int(bool(hits))  # includes duplicate alarms in a one-event case
        group = (c["region"], c["block"])
        groups[group].append((counts, lag))
        per_region[c["region"]].append((counts, lag))
        per_target[c["target"]].append((counts, lag))
    rows = [r for g in groups.values() for r in g]
    result = {"overall": _metrics(rows), "by_region": {k: _metrics(v) for k, v in per_region.items()},
              "by_target": {k: _metrics(v) for k, v in per_target.items()},
              "excluded": dict(skipped), "independent_regions": len(per_region), "intervals": {}}
    if len(per_region) >= 2:
        # Entire held-out regions are resampled, preserving dependence among their cells/events.
        rng = np.random.default_rng(0)
        regions = sorted(per_region)
        replicates = [_metrics([r for k in rng.choice(regions, len(regions)) for r in per_region[k]])
                      for _ in range(1000)]
        for key in ("precision", "recall_including_abstention", "stable_false_positive_rate", "judged_share"):
            values = [v[key] for v in replicates if v[key] is not None]
            if values:
                result["intervals"][key] = dict(percentiles_2_5_and_97_5=np.percentile(values, [2.5, 97.5]).tolist(),
                                                 defined_replicates=len(values))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["fit", "evaluate"])
    ap.add_argument("manifest")
    ap.add_argument("--model", help="new artifact path for fit or existing artifact for evaluate")
    args = ap.parse_args()
    cases = read_cases(args.manifest, "development" if args.command == "fit" else "heldout")
    if args.command == "fit":
        if not args.model:
            ap.error("fit requires --model")
        artifact = fit(cases)
        with Path(args.model).open("x") as fh:
            json.dump(artifact, fh, allow_nan=False)
    else:
        interpreter = Interpreter(json.loads(Path(args.model).read_text())) if args.model else None
        print(json.dumps(evaluate(cases, interpreter), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
