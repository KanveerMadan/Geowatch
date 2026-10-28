"""
Item 20 — the stored coverage report: one item 20 block per vector AOI.

This is what the UI reads (GET /api/vector/coverage). The UI renders it and
computes nothing: the regime, the warning, the reasons and every partial-fetch
status are decided here, by vector.coverage, and nowhere else.

The report is built offline because scoring hits Overpass and Earth Engine
(the 2026-10-27 run took most of a day with the primary endpoint timing
out). The API serves the newest stored report, verbatim.

Run from the repo root:  python -m vector.coverage_report
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os

from vector import coverage
from vector.aois import BASELINE_AOIS, MORPHOLOGY_AOIS

REPORT_DIR = os.path.join("experiments", "vector_coverage")
REPORT_PREFIX = "result_"


def report_aois() -> dict:
    """Every vector AOI: the 11 baseline AOIs plus the morphology AOIs. That
    is the same 13 the reference set was measured on."""
    out = {name: {"bbox": tuple(bbox)} for name, bbox in BASELINE_AOIS.items()}
    for name, spec in MORPHOLOGY_AOIS.items():
        out.setdefault(name, {"bbox": tuple(spec["bbox"])})
        out[name]["morphology"] = spec["morphology"]
    return out


def build_report(aois: dict, *, inputs=None, now=None) -> dict:
    """Score every AOI. An AOI whose inputs raise is reported as
    not_measurable with the error as its reason; it is never dropped, and it
    is never given a number."""
    inputs = inputs or coverage.coverage_inputs
    rows = []
    for name, spec in aois.items():
        try:
            layer, n_fp = inputs(name, spec["bbox"])
            block = coverage.score_layer(layer, footprint_count=n_fp)
        except Exception as e:   # items 54/55: name the class
            block = coverage.not_measurable_block(
                f"inputs could not be built: {type(e).__name__}: {e}")
        row = {"aoi": name, "bbox": list(spec["bbox"]), "coverage": block}
        if "morphology" in spec:
            row["morphology"] = spec["morphology"]
        rows.append(row)
    now = now or dt.datetime.now(dt.timezone.utc)
    return {
        "item": 20,
        "measure": "peer_relative_density_rank",
        "validation_status": "experimental",
        "generated_at": now.isoformat(timespec="seconds"),
        "reference_measured_on": coverage.REFERENCE_MEASURED_ON,
        # Provenance only. The UI does not read these: each block's regime,
        # warning and reasons already say what they decided.
        "thresholds": {
            "very_low_narrow_km_per_km2": coverage.VERY_LOW_NARROW_KM_PER_KM2,
            "low_narrow_km_per_km2": coverage.LOW_NARROW_KM_PER_KM2,
            "partial_mapping_arterial_to_pedestrian":
                coverage.PARTIAL_MAPPING_ARTERIAL_TO_PEDESTRIAN,
        },
        "aois": rows,
    }


def write_report(report: dict, report_dir: str = REPORT_DIR) -> str:
    day = report["generated_at"][:10]
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"{REPORT_PREFIX}{day}.json")
    with open(path, "w") as fh:
        # allow_nan=False: the score is never NaN or inf (item 20).
        json.dump(report, fh, indent=2, allow_nan=False)
        fh.write("\n")
    return path


def latest_report(report_dir: str | None = None):
    """(path, report) for the newest stored report, or None if there is none.
    Dated names sort chronologically, so the last one is the newest."""
    report_dir = report_dir or REPORT_DIR
    paths = sorted(glob.glob(os.path.join(report_dir, f"{REPORT_PREFIX}*.json")))
    if not paths:
        return None
    with open(paths[-1]) as fh:
        return paths[-1], json.load(fh)


def main():
    report = build_report(report_aois())
    path = write_report(report)
    for row in report["aois"]:
        c = row["coverage"]
        pct = c.get("osm_density_percentile", "—")
        print(f"{row['aoi']:<20} {c['coverage_regime_flag']:<15} {pct}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
