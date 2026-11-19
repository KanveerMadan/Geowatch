"""
The public site's data, generated from code: the honesty page and the city
gallery. Nothing on either page is typed by hand.

    python -m product.site_data          write web/src/generated/*.json
    python -m product.site_data --check  exit 1 if the committed files are stale

HONESTY reads analysis/contract.py: FLOOD_TAXONOMY, flood_verdicts() (pinned
round files, hash-checked), VALIDATED_CONFIGS' scope notes and
UNBUILT_FLOOD_TYPES; the ground-cover, observation and vector-track labels
from the constants their producers use; the known limits from the constants
that cause them. The round whose evidence is shown for a module is chosen by
the same rule as flood_verdicts(), and the two are checked against each
other: if they disagree, generation fails.

GALLERY reads product/gallery_cities.json (one entry per city) and the stored
run record each entry names. Values and labels are the ones stored with the
result: a stored result is immutable, so a label that has changed since is
shown as it was, with the date.

tests/test_site_data.py fails when the committed JSON and the code disagree.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from analysis import contract as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join("web", "src", "generated")
GALLERY_CONFIG = os.path.join("product", "gallery_cities.json")


def _rel(path: str) -> str:
    return os.path.relpath(path, ROOT) if os.path.isabs(path) else path


def _load(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


# ── honesty ─────────────────────────────────────────────────────────────

ROUND_FILES = {
    1: (C.FLOOD_VALIDATION_RESULT, C.FLOOD_VALIDATION_SHA256),
    2: (C.FLOOD_VALIDATION_ROUND2_RESULT, C.FLOOD_VALIDATION_ROUND2_SHA256),
    3: (C.FLOOD_VALIDATION_ROUND3_RESULT, C.FLOOD_VALIDATION_ROUND3_SHA256),
    4: (C.FLOOD_VALIDATION_ROUND4_RESULT, C.FLOOD_VALIDATION_ROUND4_SHA256),
}


def _rounds() -> dict:
    out = {}
    for n, (path, sha) in ROUND_FILES.items():
        digest = C.sha256_file(path)
        if digest != sha:
            raise C.ContractError(f"{path}: sha256 {digest} is not the pinned {sha}")
        out[n] = _load(path)
    return out


def _deciding_round(module: str, rounds: dict) -> int | None:
    """The round whose verdict flood_verdicts() reads for `module`."""
    def v(n):
        return ((rounds[n]["modules"].get(module) or {}).get("held_out") or {}).get("verdict")
    if module in C.ROUND4_REPLACED_METHODS:
        return 4 if v(4) and v(4) != "not-run" else None
    if v(3) and v(3) != "not-run":
        return 3
    if v(2) and (v(2) != "not-run" or module in C.ROUND2_REPLACED_METHODS):
        return 2
    return 1 if (rounds[1]["modules"].get(module) or {}).get("verdict") else None


def _evidence(module: str, n: int, rounds: dict) -> dict:
    m = rounds[n]["modules"][module]
    path = ROUND_FILES[n][0]
    if n == 1:
        return {"round": 1, "file": path, "verdict": m.get("verdict"), "auc": m.get("auc"),
                "auc_kind": "round 1 AUC", "events": []}
    ho = m["held_out"]
    per = m.get("held_out_per_event") or {}
    events = [{"event": e, "auc": x.get("auc")} for e, x in per.items() if x.get("qualifies", True)]
    pooled = "n_sites" in ho
    return {"round": n, "file": path, "verdict": ho["verdict"], "auc": ho.get("auc"),
            "auc_kind": ("pooled AUC over held-out sites" if pooled
                         else "mean within-event AUC over held-out events"),
            "qualifying": ho.get("n_sites") if pooled else ho.get("qualifying_events"),
            "events": events}


def _label_for(verdict: str | None, scoped: bool) -> dict:
    """What a module's output is labelled, from its verdict (hazard_label's
    rule): failed stays failed whatever the inputs; validated holds only in
    the validated configuration, and is experimental anywhere else."""
    lab = C.verdict_label(verdict)
    if lab == "failed":
        return {"label": "failed", "outside_scope": None}
    if lab == "validated" and scoped:
        return {"label": "validated", "outside_scope": "experimental"}
    return {"label": "experimental", "outside_scope": None}


def honesty() -> dict:
    from analysis.fractions import StandInFractions
    from analysis.hazards import CONTEXT_SOURCES
    from analysis.observability import CAUSE_LABEL
    from vector import coverage as VC, fractions as VF, roads as VR, units as VU

    rounds = _rounds()
    verdicts = C.flood_verdicts()
    bar = rounds[4]["bar"]
    flood = []
    for fid, t in C.FLOOD_TAXONOMY.items():
        mod = t["module"]
        row = {"id": fid, "module": mod, "name": t["name"], "status_text": t["status"],
               "round": t["round"]}
        if mod in C.UNBUILT_FLOOD_TYPES:
            status, label, reason = C.UNBUILT_FLOOD_TYPES[mod]
            row.update({"built": False, "status": status, "label": label, "reason": reason})
        else:
            n = _deciding_round(mod, rounds)
            ev = _evidence(mod, n, rounds) if n else None
            if (ev or {}).get("verdict") != verdicts.get(mod):
                raise C.ContractError(f"{mod}: the honesty page would show round {n}'s verdict "
                                      f"{(ev or {}).get('verdict')!r}; flood_verdicts() says "
                                      f"{verdicts.get(mod)!r}")
            cfg = C.VALIDATED_CONFIGS.get(mod)
            scope = json.loads(json.dumps(cfg["scope"])) if cfg else None
            row.update({"built": True, "verdict": verdicts.get(mod), "evidence": ev,
                        **_label_for(verdicts.get(mod), scope is not None),
                        "scope": scope,
                        "validated_method": cfg["config"]["method"] if cfg else None})
        flood.append(row)

    producer = StandInFractions()
    labels = producer.labels()
    ground = [{"key": f, "label": labels[f], "measured": f not in producer.NOT_COMPUTED,
               "reason": producer.NOT_COMPUTED.get(f)} for f in labels]

    limits = [
        {"id": "terrain", "title": "Flood scores rest on 30 m terrain",
         "facts": {"evaluation_cell_m": None,
                   "terrain_sources": [CONTEXT_SOURCES[k] for k in ("hand", "fabdem", "slope")]}},
        {"id": "clouds", "title": "Cloud gaps leave cells unmeasured",
         "facts": {"min_clear_observations_per_pixel": VF.MIN_VALID_OBS,
                   "pixel_m": VF.PIXEL_M, "min_unit_coverage": VU.MIN_UNIT_COVERAGE}},
        {"id": "osm", "title": "Street and building maps vary by place",
         "facts": {"regimes": list(VC.REGIMES),
                   "warned_regimes": sorted(VC.LOW_COVERAGE_REGIMES),
                   "topology_suppressed_in": sorted(VC.SUPPRESS_TOPOLOGY_IN)}},
    ]
    # The terrain cell is the evaluation cell every round-4 event used: read
    # it, do not assume it.
    cells = {e.get("evaluation_cell_m") for m in rounds[4]["modules"].values()
             for e in (m.get("held_out_per_event") or {}).values()}
    if len(cells) != 1:
        raise C.ContractError(f"round 4 used several evaluation cells: {cells}")
    limits[0]["facts"]["evaluation_cell_m"] = cells.pop()

    return {
        "generated_from": sorted({"analysis/contract.py", "analysis/fractions.py",
                                  "analysis/observability.py", "analysis/hazards.py",
                                  "vector/coverage.py", "vector/fractions.py", "vector/roads.py",
                                  "vector/units.py", *[p for p, _ in ROUND_FILES.values()]}),
        "pinned_sha256": {p: s for p, s in ROUND_FILES.values()},
        "label_order": list(C.VALIDATION_PRECEDENCE),
        "bar": {"validated_if_auc_at_least": bar["validated_if_auc_at_least"],
                "min_events": bar["min_test_events"], "min_flooded_cells": bar["min_flooded_cells"],
                "min_dry_cells": bar["min_dry_cells"], "metric": bar["metric"]},
        "flood": flood,
        "ground": ground,
        "observation": [{"cause": k, "label": v} for k, v in CAUSE_LABEL.items()],
        "vector_default_label": VR.VALIDATION_DEFAULT,
        "limits": limits,
    }


# ── gallery ─────────────────────────────────────────────────────────────

def gallery(config_path: str = GALLERY_CONFIG) -> dict:
    from analysis.live_runs import CITIES
    from analysis.store import valid_id

    cfg = _load(config_path)
    cards = []
    for entry in cfg["cities"]:
        rec = _load(entry["run_record"])
        run = rec["cities"][entry["run_key"]]
        if not run.get("stored") or not valid_id(run.get("result_id")):
            raise ValueError(f"{entry['run_key']}: the run record has no stored result")
        h = run["headline"]
        city = CITIES[entry["run_key"]]
        cards.append({
            "key": entry["key"], "name": entry["name"], "region": entry["region"],
            "result_id": run["result_id"], "version_id": run["version_id"],
            "run_utc": rec["run_utc"], "window": rec["window"],
            "bbox": list(city["bbox"]), "run_record": entry["run_record"],
            "fractions": [{"key": k, "value": v[0], "status": v[1], "label": v[2]}
                          for k, v in h["fractions"].items()],
            "flood": [{"key": k, "value": v[0], "tier": v[1], "status": v[2], "label": v[3]}
                      for k, v in h["susceptibility"].items()],
            "observed_fraction": h["observed_fraction"],
            "osm_regime": h.get("osm_regime"),
            "label_counts": run["validation_summary"],
        })
    return {"cities": cards}


# ── files ───────────────────────────────────────────────────────────────

def build() -> dict:
    return {"honesty.json": honesty(), "gallery.json": gallery()}


def _dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    stale = []
    for name, obj in build().items():
        path = os.path.join(OUT_DIR, name)
        text = _dump(obj)
        if args.check:
            if not os.path.exists(path) or open(path).read() != text:
                stale.append(path)
        else:
            os.makedirs(OUT_DIR, exist_ok=True)
            with open(path, "w") as fh:
                fh.write(text)
            print(f"wrote {path}")
    if stale:
        print("stale (run python -m product.site_data):", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
