"""
Phase 2 live runs: the analysis pipeline end to end on three cities.

    python -m analysis.live_runs            # writes experiments/analysis_runs/

Everything below was fixed 2026-10-28 and committed BEFORE the first live
run, so no AOI, window or bar was chosen for how it scored.

AOIs: Dharavi (the project's canonical AOI, with the 24 Mumbai BMC wards as
an extra unit type), and two cities from item 19's morphology set that have
Open Buildings coverage: Lagos (dense informal) and Chandigarh (formal
Asian). One dry-season window for all three.

RUN BARS are engineering acceptance only. They say whether the pipeline ran
and kept its contract. They are NOT validation: every output's label is
decided by analysis/contract.py, and no run here can make anything
`validated`.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

CITIES = {
    "dharavi": {"bbox": (72.836, 19.037, 72.862, 19.060),
                "boundary_layer_id": "datameet_mumbai_bmc_wards"},
    "lagos": {"bbox": (3.37, 6.475, 3.41, 6.51), "boundary_layer_id": None},
    "chandigarh_central": {"bbox": (76.765, 30.725, 76.790, 30.745), "boundary_layer_id": None},
}
WINDOW = ("2026-01-01", "2026-03-31")

RUN_BARS = {
    "every_stage_ok": True,             # no stage timed out or failed
    "contract_violations": 0,           # whole result + every served ward unit
    "consistency": "PASS",              # item 22: unit types reproduce the same totals
    "runtime_budget_s": 1800,           # per city, first (uncached) run
    "cache_hit_on_rerun": True,         # same AOI + dates + version is not recomputed
}
OUT_DIR = os.path.join("experiments", "analysis_runs")


def per_output_labels(result: dict) -> dict:
    from analysis.contract import walk_outputs
    return {path: {"validation_status": o["validation_status"], "status": o["status"]}
            for path, o in walk_outputs(result["outputs"])}


def check_wards(result: dict, units: dict) -> int:
    """Materialise and contract-check every ward unit. Returns the count."""
    from analysis.wards import materialize, ward_context
    ctx = ward_context(result)
    n = 0
    for t, b in units.items():
        for u in b["units"]:
            materialize(u, t, ctx)
            n += 1
    return n


def run_city(name: str, spec: dict) -> dict:
    from analysis import store
    from analysis.contract import ContractError, check_result
    t0 = time.time()
    out = store.analyze(spec["bbox"], *WINDOW, name=name, boundary_id=spec["boundary_layer_id"])
    runtime = round(time.time() - t0, 1)
    r = out["result"]
    row = {"result_id": out["result_id"], "stored": out["stored"], "cached": out["cached"],
           "runtime_s": runtime, "pipeline_runtime_s": r.get("runtime_s"),
           "stages": r["stages"], "not_stored_because": out.get("not_stored_because"),
           "version_id": r["model_version"]["version_id"],
           "code_commit": r["model_version"]["code_commit"],
           "code_dirty": r["model_version"]["code_dirty"],
           "validation_summary": r.get("validation_summary"),
           "labels": per_output_labels(r), "wards": r["wards"]}
    violations = []
    try:
        row["outputs_checked"] = check_result(r)
    except ContractError as e:
        violations.append(f"result: {e}")
    units = store.get_units(out["result_id"]) if out["stored"] else None
    if units is not None:
        try:
            row["ward_units_checked"] = check_wards(r, units)
        except ContractError as e:
            violations.append(f"wards: {e}")
    row["contract_violations"] = violations
    agg = r["outputs"]["aggregation"]
    row["consistency"] = {t: a.get("consistency") for t, a in agg.items()}
    t1 = time.time()
    again = store.analyze(spec["bbox"], *WINDOW, name=name, boundary_id=spec["boundary_layer_id"])
    row["rerun"] = {"cached": again["cached"], "runtime_s": round(time.time() - t1, 1),
                    "same_id": again["result_id"] == out["result_id"]}
    s = r["outputs"]["susceptibility"]
    row["headline"] = {
        "fractions": {f: (v["value"], v["status"], v["validation_status"])
                      for f, v in r["outputs"]["fractions"].items()},
        "observed_fraction": r["outputs"]["observability"]["observed_fraction"]["value"],
        "susceptibility": {h: (v["value"], v.get("tier"), v["status"], v["validation_status"])
                           for h, v in s.items()},
        "osm_regime": r["outputs"]["osm_coverage"]["coverage_regime_flag"],
    }
    row["bars"] = {
        "every_stage_ok": all(v["status"] == "ok" for v in r["stages"].values()),
        "contract_violations": len(violations),
        "consistency": "PASS" if all(c in ("PASS", None) for t, c in row["consistency"].items()
                                     if not t.startswith("ward")) else "FAIL",
        "runtime_s": runtime, "within_runtime_budget": runtime <= RUN_BARS["runtime_budget_s"],
        "cache_hit_on_rerun": bool(again["cached"] and row["rerun"]["same_id"]),
    }
    return row


def main():
    rows = {}
    for name, spec in CITIES.items():
        print(f"\n===== {name} =====", flush=True)
        try:
            rows[name] = run_city(name, spec)
        except Exception as e:                   # noqa: BLE001 -- one city must not stop the rest
            rows[name] = {"error": f"{type(e).__name__}: {e}"}
        print(json.dumps(rows[name].get("bars", rows[name]), indent=1), flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"result_{datetime.now(timezone.utc):%Y-%m-%d}.json")
    with open(path, "w") as fh:
        json.dump({"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "window": WINDOW, "bars": RUN_BARS, "cities": rows}, fh, indent=1, default=str)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
