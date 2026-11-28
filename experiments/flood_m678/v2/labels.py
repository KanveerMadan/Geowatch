"""
M6–M8 v2 step 2: DEV labels with per-cell provenance (ARCHITECTURE_V2 "Event supply and observations").

Run from the pinned round-3 checkout (R35) so round 3's modules are the ones imported:

    cd ~/gw-r3pin-r35 && PYTHONPATH=.:$HOME/gw-m678v2/experiments/flood_m678 python -B ~/gw-m678v2/experiments/flood_m678/v2/labels.py dev [--limit N]

Rules (v1's, imported from labels_m678 unchanged; reproduced exactly on the Midland and Grand Forks
fixtures before any change): five states 1 flooded, 0 dry, -1 unobserved, -2 permanent/normal water,
-3 ambiguous; optical two-signal new-water rule with a pre-event land view; radar R3-S1/R3-O rules;
MODIS snow unobserved; built-up unobserved.

Changes for v2 (design, recorded in decisions.md before any v2 label):
- **No union across flood phases.** Each scene is labelled on its own. A cell takes the state of the
  in-window observation NEAREST the local crest (by |offset|), optical first; radar fills only where
  no optical scene gives FLOODED or DRY. The union of all scenes is kept as a secondary layer.
- **Provenance per cell:** sensor family (1 optical, 2 radar), scene index and offset from the crest
  interval (hours, nearest bound).
- **Box on its own grid** when the flood-centre box extends past the search square (v1's defect).
- DEV only: paths come from v2/storage.py; reserve components are refused.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

V2 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(V2))           # v1 modules (labels_m678, screen_acquisitions)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


S = _load("v2storage", os.path.join(V2, "storage.py"))
SEARCH_M, BOX_M = 20000.0, 8000.0
MAX_PER_COMPONENT = 2


def _utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def offset_h(scene_utc, lo, hi):
    """Hours from the crest interval: 0 inside it, else to the nearest bound (signed)."""
    t = _utc(scene_utc)
    if t < lo:
        return (t - lo).total_seconds() / 3600
    if t > hi:
        return (t - hi).total_seconds() / 3600
    return 0.0


def nearest_merge(stacks, offsets, families):
    """Per cell: the FLOODED/DRY state from the scene with the smallest |offset|, optical (family 1)
    before radar (2). Returns (state, family, scene index, offset). Cells no scene decides keep the
    'most informative' non-scored state: permanent > ambiguous > unobserved."""
    shape = stacks[0].shape
    state = np.full(shape, -1, np.int8)
    fam = np.zeros(shape, np.int8)
    idx = np.full(shape, -1, np.int16)
    off = np.full(shape, np.nan, np.float32)
    order = sorted(range(len(stacks)), key=lambda i: (families[i], abs(offsets[i])))
    decided = np.zeros(shape, bool)
    for i in order:
        y = stacks[i]
        take = ~decided & np.isin(y, (0, 1))
        state[take], fam[take], idx[take], off[take] = y[take], families[i], i, offsets[i]
        decided |= take
    for code in (-3, -2):                                 # ambiguous, then permanent wins over unobserved
        for i in order:
            y = stacks[i]
            take = ~decided & (y == code) & (state != -2)
            state[take] = code
    return state, fam, idx, off


def scenes_for(lead, lat, lon, ses):
    import screen_acquisitions as SA
    lo, hi = _utc(lead["crest_utc_min"]), _utc(lead["crest_utc_max"])
    if lead["type"] == "M7":
        # M7 (Amendments 4 and 5): the same window code as the seal screen, so DEV labels see exactly the
        # sealed window (levee: [breach, breach + 72 h]; breach known to the day: [day end, day start + 72 h];
        # dam: [crest - 24 h, crest + 48 h] floored at any reported breach time).
        SV = _load("v2screen", os.path.join(V2, "screen_v2.py"))
        src = {**lead, "crest_kind": lead.get("src_crest_kind", lead.get("crest_kind", ""))}
        return SV.screen_lead(src, lo, hi, ses)["scenes"], lo, hi
    site = {"type": lead["type"], "subtype": "ice jam" if lead["submode"] == "ice_jam" else lead["submode"],
            "zone": "UTC", "longitude": lon, "latitude": lat}
    ev = {"date": lead["date"], "crest_utc_bracket": [lo.isoformat(), hi.isoformat()]}
    from pathlib import Path
    return SA.screen(ev, site, {}, ses, Path(os.path.expanduser("~/.cache/geowatch/m678v2/stac")))["scenes"], lo, hi


def domain_labels(ee, optical, radar, lo, hi, bb, t, shape, crs):
    """v2 labels on any grid (box, search square or corridor domain), by the rules in the docstring."""
    import labels_m678 as LM
    from experiments.flood_round3 import labels_r3 as L
    obs = L.observability(ee, t, shape, crs)
    stacks, offs, fams, used = [], [], [], []
    for sc in optical:
        o, u = LM.optical_label(ee, [sc], lo, t, shape, crs)
        if o is not None:
            stacks.append(LM.optical_states(o, obs)); offs.append(offset_h(sc["utc"], lo, hi)); fams.append(1)
            used.append({"scene": sc["scene"], "family": "optical", "utc": sc["utc"], "offset_h": offs[-1]})
    for sc in radar:
        try:
            lab = LM.radar_label(ee, bb, [sc], lo, t, shape, crs)
        except LookupError:
            continue
        stacks.append(L.s1_states(lab, obs)); offs.append(offset_h(sc["utc"], lo, hi)); fams.append(2)
        used.append({"scene": sc["scene"], "family": "radar", "utc": sc["utc"], "offset_h": offs[-1]})
    if not stacks:
        return None
    days = [_utc(u["utc"]).date().isoformat() for u in used]
    modis_days = [d for d in days if d >= "2000-02-24"]       # MODIS Terra snow begins 2000-02-24
    snow = LM.snow_mask(ee, modis_days, t, shape, crs) if modis_days else np.zeros(shape, bool)
    if len(modis_days) < len(days):
        used.append({"note": "MODIS snow unavailable before 2000-02-24: the sensors' own snow flags only"})
    for y in stacks:
        y[snow & (y != L.PERMANENT)] = L.UNOBSERVED
    state, fam, idx, off = nearest_merge(stacks, offs, fams)
    union = np.where(np.any([np.isin(y, (1,)) for y in stacks], axis=0), 1,
                     np.where(np.any([y == 0 for y in stacks], axis=0), 0, state)).astype(np.int8)
    return {"state": state, "family": fam, "scene": idx, "offset": off, "union": union, "scenes": used}



def build(lead, comp, ee):
    import labels_m678 as LM
    from experiments.flood_round3 import labels_r3 as L
    from experiments.flood_validation import references as R
    from experiments.flood_validation.harness_round4 import s1_flood_centre, window_in
    from susceptibility.hydro_rasters import utm_grid
    out_p = S.dev_path("labels", f"{lead['lead_id'].replace(':', '__')}.npz")
    if os.path.exists(out_p):
        return json.loads(str(np.load(out_p, allow_pickle=False)["meta"]))
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    lat, lon = float(lead["lat"]), float(lead["lon"])
    import requests
    scenes, lo, hi = scenes_for(lead, lat, lon, requests.Session())
    radar = [dict(s, scene_orbit=LM.s1_relative_orbit(s["scene"])) for s in scenes
             if s["collection"] == "sentinel-1-grd" and s.get("baseline")]
    optical = [s for s in scenes if s["collection"] != "sentinel-1-grd"]

    def labels_on(bb, t, shape, crs):
        return domain_labels(ee, optical, radar, lo, hi, bb, t, shape, crs)

    sq = R.square_bbox(lat, lon, SEARCH_M)
    t, shape, crs = utm_grid(sq)
    a = labels_on(sq, t, shape, crs)
    meta = {"lead": lead["lead_id"], "component": comp, "type": lead["type"], "submode": lead["submode"],
            "date": lead["date"], "crest_utc": [lo.isoformat(), hi.isoformat()], "search_square": list(sq),
            "merge": "nearest-to-crest, optical first, radar fill (v2)"}
    if a is None:
        meta["dropout"] = "no label source built"
        np.savez_compressed(out_p, meta=np.array(json.dumps(meta)))
        return meta
    centre = s1_flood_centre(a["state"] == 1, np.isin(a["state"], (0, 1)), t, crs)
    if centre is None:
        meta.update(dropout="no flooded cell in the search square", scenes=a["scenes"])
        np.savez_compressed(out_p, meta=np.array(json.dumps(meta)))
        return meta
    box = R.square_bbox(*centre, BOX_M)
    bt, bshape, bcrs = utm_grid(box)
    try:
        r0, c0 = window_in(t, shape, bt, bshape)
        b = {k: v[r0:r0 + bshape[0], c0:c0 + bshape[1]] for k, v in a.items() if k != "scenes"}
        b["scenes"] = a["scenes"]
    except ValueError:
        b = labels_on(box, bt, bshape, bcrs)
        meta["box_labelled_on_own_grid"] = True
    y = b["state"]
    meta.update(centre=list(centre), bbox=list(box), grid={"crs": bcrs, "transform": list(bt)[:6], "shape": list(bshape)},
                flooded_cells=int((y == 1).sum()), dry_cells=int((y == 0).sum()), ambiguous_cells=int((y == -3).sum()),
                unobserved_cells=int((y == -1).sum()), permanent_cells=int((y == -2).sum()), scenes=b["scenes"],
                optical_share=float((b["family"][np.isin(y, (0, 1))] == 1).mean()) if np.isin(y, (0, 1)).any() else None,
                union_flooded=int((b["union"] == 1).sum()))
    if lead["type"] == "M7":                     # Amendment 4.1: each label records its lag to the breach
        ref = _breach_ref(lead, lo)
        meta["breach_ref_utc"], meta["breach_ref_kind"] = ref[0].isoformat(), ref[1]
        meta["lag_to_breach_h"] = [round((_utc(sc["utc"]) - ref[0]).total_seconds() / 3600, 2)
                                   for sc in b["scenes"] if "utc" in sc]
    np.savez_compressed(out_p + ".tmp.npz", y=y, family=b["family"], scene=b["scene"], offset=b["offset"],
                        union=b["union"], meta=np.array(json.dumps(meta, default=str)))
    os.replace(out_p + ".tmp.npz", out_p)
    return meta


def _breach_ref(lead, lo):
    """The breach time a label's lag is measured from: the reported breach time (levee), the start of the
    breach day (breach known to the day), else the start of the dam crest window (incident day)."""
    kind = lead.get("src_crest_kind", lead.get("crest_kind", ""))
    if lead["submode"] == "levee_breach" and kind == "breach_day":
        return lo, "breach_day_start"
    if lead.get("not_before_utc"):
        return _utc(lead["not_before_utc"]), "reported_breach_time"
    return lo, "crest_window_start"


def dev_leads(limit=None, seal_version="2.0", only_type=None):
    seal = json.load(open(os.path.join(V2, f"seal_{seal_version}.json")))
    leads = {r["lead_id"]: r for r in csv.DictReader(open(os.path.join(V2, "leads.csv")))}
    order = {"sustained_melt": 0, "ice_jam": 1}
    out = []
    for c in sorted(seal["dev"], key=lambda c: (order.get(c["submode"], 9), c["component"])):
        same = [x for x in c["leads"] if leads[x["lead_id"]]["submode"] == c["submode"]]
        if only_type and c["type"] != only_type:
            continue
        for x in sorted(same, key=lambda x: x["date"])[:MAX_PER_COMPONENT]:
            out.append((c["component"], {**leads[x["lead_id"]], **x, "src_crest_kind": leads[x["lead_id"]]["crest_kind"]}))
    return out[:limit] if limit else out


def provenance_table():
    rows = []
    d = S.dev_path("labels")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = json.loads(str(np.load(os.path.join(d, f), allow_pickle=False)["meta"]))
        offs = [s["offset_h"] for s in m.get("scenes", []) if "offset_h" in s]
        rows.append({"lead": m["lead"], "component": m["component"], "type": m["type"], "submode": m["submode"],
                     "date": m["date"], "flooded": m.get("flooded_cells"), "dry": m.get("dry_cells"),
                     "usable": bool((m.get("flooded_cells") or 0) >= 50 and (m.get("dry_cells") or 0) >= 50),
                     "dropout": m.get("dropout", ""), "optical_share": m.get("optical_share"),
                     "n_scenes": len(offs), "min_abs_offset_h": min((abs(o) for o in offs), default=None),
                     "union_flooded": m.get("union_flooded"), "own_grid": m.get("box_labelled_on_own_grid", False)})
    p = os.path.join(V2, "provenance.csv")
    if rows:
        with open(p, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    return rows


def main(argv):
    import labels_m678 as LM
    if argv[0] != "dev":
        raise SystemExit("v2 labels.py builds DEV only; the reserve is built by score_once after the gates")
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    seal_version = argv[argv.index("--seal") + 1] if "--seal" in argv else "2.0"
    only_type = argv[argv.index("--type") + 1] if "--type" in argv else None
    S.init()
    ee = LM.init_ee()
    for comp, lead in dev_leads(limit, seal_version, only_type):
        try:
            m = build(lead, comp, ee)
            print(lead["lead_id"], json.dumps({k: m.get(k) for k in ("flooded_cells", "dry_cells", "optical_share", "dropout")}),
                  flush=True)
        except Exception as e:      # noqa: BLE001
            print(lead["lead_id"], "ERROR", type(e).__name__, str(e)[:200], flush=True)
    rows = provenance_table()
    print("provenance rows", len(rows), "usable", sum(r["usable"] for r in rows))


if __name__ == "__main__":
    main(sys.argv[1:])
