"""
flood_round2 DEV references and inputs. DEV units only: reserved units are refused.

    python -m experiments.flood_round2.build_dev refs          # EMS + S1 references for DEV_EMS_R2 / DEV_S1_R2
    python -m experiments.flood_round2.build_dev inputs        # inputs + feature tables for registered round-2 DEV units
    python -m experiments.flood_round2.build_dev --one <unit>  # (internal)

References use round 4's place() + reference(), unchanged (as flood_final).
Inputs and tables use flood_final.build_units.build_one, with this run's reference directory.
Each unit runs in a killable subprocess with up to 3 tries.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

CACHE = os.path.expanduser("~/.cache/geowatch/flood_round2")
DEV_REFS = os.path.join(CACHE, "dev_refs")
REF_DIR = os.path.join(DEV_REFS, "refs")
LOG = os.path.join(CACHE, "build_dev_log.json")
UNIT_KILL_S = 3600
TRIES = 3


def refs():
    from experiments.flood_baselines.build import check_disk
    from experiments.flood_final import heldout_pass as HP
    from experiments.flood_learned.heldout import select as SEL
    from experiments.flood_validation.harness import MIN_DRY_CELLS, MIN_FLOODED_CELLS
    from experiments.flood_round2 import events_round2 as E
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    SEL.REF_DIR = HP.REF_DIR = REF_DIR
    os.makedirs(REF_DIR, exist_ok=True)
    for code, (tags, region, link) in E.DEV_EMS_R2.items():
        out_p = os.path.join(DEV_REFS, f"{code}.json")
        if os.path.exists(out_p):
            continue
        rows, event = SEL.product_rows(code)
        aois = []
        for aoi, mon, typ, aname in rows:
            check_disk()
            try:
                m = SEL.build_ref(code, aoi, mon, typ, event)
            except Exception as e:      # noqa: BLE001 -- recorded
                m = {"unit": f"{code.lower()}_aoi{aoi:02d}", "error": f"{type(e).__name__}: {e}"[:300]}
            m.update(aoi=aoi, monitoring=mon, product_type=typ, aoi_name=aname)
            m["qualifies"] = m.get("flooded_cells", 0) >= MIN_FLOODED_CELLS and m.get("dry_cells", 0) >= MIN_DRY_CELLS
            aois.append({k: m.get(k) for k in ("unit", "aoi", "aoi_name", "monitoring", "product_type", "bbox",
                                               "flooded_cells", "dry_cells", "qualifies", "error")})
            print(f"  {code} AOI{aoi:02d} {aname[:25]}: {m.get('flooded_cells')} / {m.get('dry_cells')} "
                  f"{'Q' if m['qualifies'] else '-'} {str(m.get('error', ''))[:60]}", flush=True)
        json.dump({"code": code, "event": event, "tags": list(tags), "region": region, "aois": aois},
                  open(out_p, "w"), indent=1, default=str)
    for name, (tags, region, pt, date, basis) in E.DEV_S1_R2.items():
        u = {"event_id": name, "date": date, "flood_final": {"reference": ["s1", pt[1], pt[0], date]}}
        try:
            m = HP.build_reference(u)
        except Exception as e:          # noqa: BLE001
            m = {"error": f"{type(e).__name__}: {e}"[:300]}
        print(f"  {name}: {m.get('flooded_cells')} / {m.get('dry_cells')} {str(m.get('error', ''))[:60]}", flush=True)
    return 0


def round2_dev_units(reg=None) -> list:
    from experiments.flood_core.registry import registry as REG
    reg = reg or REG.load()
    return [u for u in reg["units"] if u["role"] == "dev" and u.get("exposure_level", 0) < 6
            and any(x.get("round") == "flood_round2" for x in u.get("uses", []))]


def build_one(name: str) -> dict:
    from experiments.flood_final import build_units as BU
    BU.REF_DIR = REF_DIR
    return BU.build_one(name)


def inputs():
    import numpy as np
    from experiments.flood_baselines.build import check_disk
    from experiments.flood_learned import features as FT
    log = json.load(open(LOG)) if os.path.exists(LOG) else {}
    for u in round2_dev_units():
        n = u["event_id"]
        p = os.path.join(REF_DIR, f"{n}.npz")
        if not os.path.exists(p):
            log[n] = {"done": True, "result": "no reference"}
            continue
        meta = json.loads(str(np.load(p)["meta"]))
        if "error" in meta or meta.get("flooded_cells", 0) < 50 or meta.get("dry_cells", 0) < 50:
            log[n] = {"done": True, "result": {"not_qualifying": [meta.get("flooded_cells"), meta.get("dry_cells")],
                                               "error": meta.get("error")}}
            continue
        rec = log.setdefault(n, {"tries": 0})
        while not os.path.exists(FT.path(n)) and rec["tries"] < TRIES:
            check_disk()
            t0 = time.time()
            try:
                r = subprocess.run([sys.executable, "-m", "experiments.flood_round2.build_dev", "--one", n],
                                   timeout=UNIT_KILL_S, capture_output=True, text=True)
                ok, tail = r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-3:]
            except subprocess.TimeoutExpired:
                ok, tail = False, [f"killed after {UNIT_KILL_S} s"]
            rec["tries"] += 1
            rec.update(ok=ok, tail=tail, s=round(time.time() - t0))
            print(n, json.dumps(rec)[:300], flush=True)
            os.makedirs(CACHE, exist_ok=True)
            json.dump(log, open(LOG, "w"), indent=1)
        rec["done"] = os.path.exists(FT.path(n))
        json.dump(log, open(LOG, "w"), indent=1)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "--one":
        import ee
        from experiments.flood_validation import references as R
        from ingestion.gee_client import initialize_gee
        initialize_gee()
        ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
        print(json.dumps(build_one(a[1]), default=str)[:600], flush=True)
        return 0
    return refs() if a[0] == "refs" else inputs()


if __name__ == "__main__":
    sys.exit(main())
