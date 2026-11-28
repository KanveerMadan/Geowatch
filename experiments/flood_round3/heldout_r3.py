"""
Round 3 one-shot held-out test (PREREGISTRATION_R3.md). It runs only after the freeze (tag r3-freeze), on the sealed
reserve (results/reserve_r3.json).

    python -m experiments.flood_round3.heldout_r3 build     # labels + features for every sealed unit (resumable)
    python -m experiments.flood_round3.heldout_r3 score     # frozen models -> results/test_r3.json (once)

Units:
- waterlogging plains (S1v3): build_r3.s1route_ref (v3 Sentinel-1 label, box by round 4's place()), round-2 tables,
  wl_feats.one.
- public EMS (EMS): round 4's place() on the product, labels_r3.apply_states, round-2 tables. Rain units get the fine
  features as NaN, as every non-311 DEV unit did.
- FloodNet storms (rain): FLOODNET_TEST_DESIGN rules 5, 7 and 10. Each storm is one unit on a city-wide NYC UTM 18N
  30 m grid; scores come from the box (nyc lattice) whose centre is nearest each sensor cell.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import pickle
import sys
import time
import urllib.parse

import numpy as np

from experiments.flood_round3 import build_r3 as B
from experiments.flood_round3 import dev_cv_r3 as D
from experiments.flood_round3 import model_r3 as M

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
RESERVE = os.path.join(OUT, "reserve_r3.json")
LOG = os.path.join(D.BIG, "heldout_r3_log.json")
FN = os.path.expanduser("~/.cache/geowatch/flood_round3/floodnet")
FN_EVENTS = "https://data.cityofnewyork.us/resource/aq7i-eu5q.json"
FROZEN = os.path.join(D.BIG, "frozen_r3")
METHOD = {"waterlogging": "anc_elev_lgbm_wl@fluvial", "pluvial": "anc_elev_lgbm_fine@fluvial"}
BASELINE_TYPES = ("fluvial", "coastal", "compound")
WET_IN = 1.0


def _log():
    return json.load(open(LOG)) if os.path.exists(LOG) else {}


def _save_log(lg):
    json.dump(lg, open(LOG + ".tmp", "w"), indent=1)
    os.replace(LOG + ".tmp", LOG)


# ------------------------------------------------------------------ labels and features per unit
def plains_unit(u, ee):
    from experiments.flood_round3 import wl_feats as WF
    row = {c["unit"]: c for c in json.load(open(os.path.join(OUT, "plains_candidates.json")))["candidates"]}[u["unit"]]
    meta = B.s1route_ref(row, ee)
    if meta.get("flooded_cells", 0) < 50 or meta.get("dry_cells", 0) < 50:
        return {"usable": False, "flooded": meta.get("flooded_cells", 0), "dry": meta.get("dry_cells", 0),
                "why": meta.get("why")}
    B._features(u["unit"], os.path.join(B.REFS, f"{u['unit']}.npz"), meta)
    WF.one(u["unit"], ee)
    return {"usable": True, "flooded": meta["flooded_cells"], "dry": meta["dry_cells"]}


def ems_unit(u, ee):
    from experiments.flood_round3 import labels_r3 as L
    from experiments.flood_validation import harness_round4 as H4
    from experiments.flood_validation import references as R
    from susceptibility.hydro_rasters import utm_grid
    n = u["unit"]
    rp = os.path.join(B.REFS, f"{n}.npz")
    if not os.path.exists(rp):
        c = {r["unit"]: r for r in json.load(open(os.path.join(OUT, "r3_ems_candidates.json")))["candidates"]}[n]
        typ, mon = c["product"].split()[0], int(c["product"].split()[-1])
        H4.BOX_SIDE_M = B.SIDE_M
        pl = H4.place({"ref": ("ems", u["code"], u["aoi"], mon, typ), "event": u["peak"]})
        if pl.get("bbox") is None:
            meta = {"unit": n, "flooded_cells": 0, "dry_cells": 0, "why": "no flood centre in the product"}
            y = np.zeros((1, 1), np.int8) + L.UNOBSERVED
        else:
            bbox = pl["bbox"]
            t, shape, crs = utm_grid(bbox)
            obs = L.observability(ee, t, shape, crs)
            ref = R.ems_reference(R.ems_product(u["code"], u["aoi"], mon, typ), bbox, t, shape, crs)
            y = L.apply_states(ref["flooded"], ref["valid"], obs, radar=L.is_radar(u.get("sensors") or []))
            meta = {"unit": n, "event": u["event"], "peak": u["peak"], "bbox": list(bbox), "centre": pl["centre"],
                    "side_m": B.SIDE_M, "grid": {"crs": crs, "transform": list(t)[:6], "shape": list(shape)},
                    "block": 1, "label_v3": {"type": u["type"], "kind": "ems", "source": f"{u['code']} AOI{u['aoi']:02d} {typ} monitoring {mon}",
                                             "images": u.get("images"), "peak": u["peak"]},
                    "flooded_cells": int((y == L.FLOODED).sum()), "dry_cells": int((y == L.DRY).sum())}
        np.savez_compressed(rp + ".tmp.npz", flooded=(y == L.FLOODED), valid=(y == L.FLOODED) | (y == L.DRY),
                            y3=y.astype(np.int8), meta=np.array(json.dumps(meta, default=str)))
        os.replace(rp + ".tmp.npz", rp)
    meta = json.loads(str(np.load(rp, allow_pickle=False)["meta"]))
    if meta["flooded_cells"] < 50 or meta["dry_cells"] < 50:
        return {"usable": False, "flooded": meta["flooded_cells"], "dry": meta["dry_cells"], "why": meta.get("why")}
    B._features(n, rp, meta)
    return {"usable": True, "flooded": meta["flooded_cells"], "dry": meta["dry_cells"]}


# ------------------------------------------------------------------ FloodNet
def _sensors():
    s = json.load(open(os.path.join(FN, "sensors.json")))
    return [x for x in s if x.get("tidally_influenced") == "No" and x.get("date_installed") and x.get("latitude")]


def _city_grid():
    """FLOODNET rule 7: a city-wide NYC UTM 18N 30 m grid, snapped like utm_grid, covering every non-tidal sensor."""
    from pyproj import Transformer
    S = _sensors()
    tr = Transformer.from_crs(4326, 32618, always_xy=True)
    X, Y = tr.transform([float(x["longitude"]) for x in S], [float(x["latitude"]) for x in S])
    x0 = math.floor(min(X) / 30.0) * 30.0 - 300.0
    y1 = math.ceil(max(Y) / 30.0) * 30.0 + 300.0
    W = int(math.ceil((max(X) + 300.0 - x0) / 30.0))
    H = int(math.ceil((y1 - (min(Y) - 300.0)) / 30.0))
    return {"crs": "EPSG:32618", "transform": [30.0, 0.0, x0, 0.0, -30.0, y1], "shape": [H, W]}


def _cell(grid, lon, lat):
    from pyproj import Transformer
    x, y = Transformer.from_crs(4326, grid["crs"], always_xy=True).transform(lon, lat)
    t = grid["transform"]
    return int((t[5] - y) // 30.0), int((x - t[2]) // 30.0)


def fn_box_of(lon, lat):
    """FLOODNET rule 10: among nyc lattice boxes covering the point, the one whose centre is nearest."""
    from experiments.flood_round3 import rain311 as R3
    L = R3.lattice("nyc")
    cov = [(k, b) for k, b in L.items() if b[0] <= lon <= b[2] and b[1] <= lat <= b[3]]
    if not cov:
        return None
    return min(cov, key=lambda kb: (((kb[1][0] + kb[1][2]) / 2 - lon) * math.cos(math.radians(lat))) ** 2
               + ((kb[1][1] + kb[1][3]) / 2 - lat) ** 2)[0]


def fn_box_table(box):
    from experiments.flood_round3 import rain311 as R3
    from susceptibility.hydro_rasters import utm_grid
    tp = os.path.join(B.TABLES, f"{box}.npz")
    if os.path.exists(tp):
        return tp
    rp = os.path.join(B.REFS, f"{box}.npz")
    bbox = R3.lattice("nyc")[box]
    t, shape, crs = utm_grid(bbox)
    meta = {"unit": box, "event": R3.FEATURE_YEAR_EVENT, "bbox": list(bbox),
            "grid": {"crs": crs, "transform": list(t)[:6], "shape": list(shape)}, "block": 1,
            "note": "features only (FloodNet boxes); labels per storm at sensor cells"}
    if not os.path.exists(rp):
        z = np.zeros(shape, bool)
        np.savez_compressed(rp + ".tmp.npz", flooded=z, valid=z, meta=np.array(json.dumps(meta)))
        os.replace(rp + ".tmp.npz", rp)
    return B._features(box, rp, meta)


def fn_unit_feats(storm, box, ee):
    """Per storm x box: fine (311 history before 2022, 3DEP 10 m), drainage and drainage-loss SFINCS, as for 311 DEV
    units. A meta-only file in r311_refs carries the storm window; no label is written there."""
    from experiments.flood_round3 import fine_feats as FF
    from experiments.flood_round3 import rain311 as R3
    from experiments.flood_round3 import sfincs_drain as SD
    n = f"r3fn_{storm['peak_day']}_{box}"
    rp = os.path.join(R3.REFS, f"{n}.npz")
    if not os.path.exists(rp):
        tb = np.load(os.path.join(B.TABLES, f"{box}.npz"), allow_pickle=False)
        g = json.loads(str(tb["meta"]))["grid"]
        meta = {"unit": n, "box": box, "event": storm["peak_day"], "bbox": list(R3.lattice("nyc")[box]), "grid": g,
                "window": [storm["window"][0] + "T00:00:00", storm["window"][1] + "T00:00:00"]}
        np.savez_compressed(rp + ".tmp.npz", y3=np.full(int(np.prod(g["shape"])), -1, np.int8),
                            meta=np.array(json.dumps(meta)))
        os.replace(rp + ".tmp.npz", rp)
    ev = {}
    ev.update(FF.extras_311(n, ee))
    ev.update(FF.drainage_311(n, ee))
    ev.update(SD.run_unit(n, ee))
    return n, ev


def _local_window(storm):
    """The UTC window [peak - 1 d, peak + 2 d) in America/New_York local time (FloodNet timestamps are local)."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/New_York")
    a = dt.datetime.fromisoformat(storm["window"][0]).replace(tzinfo=dt.timezone.utc).astimezone(tz)
    b = dt.datetime.fromisoformat(storm["window"][1]).replace(tzinfo=dt.timezone.utc).astimezone(tz)
    return a.strftime("%Y-%m-%dT%H:%M:%S"), b.strftime("%Y-%m-%dT%H:%M:%S")


def fn_labels(storm):
    """FLOODNET rule 5 and 7 -> {(row, col): state}, per-sensor table. Read only after the freeze."""
    import urllib.request
    p = os.path.join(FN, f"events_{storm['peak_day']}.json")
    if not os.path.exists(p):
        a, b = _local_window(storm)
        q = urllib.parse.urlencode({"$where": f"flood_start_time >= '{a}' AND flood_start_time < '{b}'", "$limit": 50000})
        open(p, "wb").write(urllib.request.urlopen(f"{FN_EVENTS}?{q}", timeout=120).read())
    ev = json.load(open(p))
    w0 = dt.date.fromisoformat(storm["window"][0])
    active = [s for s in _sensors() if s["date_installed"][:10] <= (w0 - dt.timedelta(days=1)).isoformat()]
    mx = {}
    for e in ev:
        try:
            mx[e["sensor_id"]] = max(mx.get(e["sensor_id"], -1.0), float(e.get("max_depth_inches") or 0.0))
        except (KeyError, ValueError):
            continue
    grid = _city_grid()
    cells = {}
    for s in active:
        sid = s["sensor_id"]
        st = "wet" if mx.get(sid, -1.0) >= WET_IN else ("dry" if sid not in mx else "excluded")
        if st == "excluded":
            continue
        cells.setdefault(_cell(grid, float(s["longitude"]), float(s["latitude"])), []).append((st, s))
    out = {}
    for k, v in cells.items():
        sts = {x[0] for x in v}
        if len(sts) == 1:
            out[k] = (sts.pop(), v[0][1])
    return out, {"active_nontidal": len(active), "sensors_with_events": len(mx)}


# ------------------------------------------------------------------ build
def _active_boxes(storm):
    """Boxes (rule 10) holding at least one non-tidal sensor active at the storm's window start (criteria §12)."""
    w0 = dt.date.fromisoformat(storm["window"][0])
    act = [x for x in _sensors() if x["date_installed"][:10] <= (w0 - dt.timedelta(days=1)).isoformat()]
    return sorted({b for x in act for b in [fn_box_of(float(x["longitude"]), float(x["latitude"]))] if b})


def _run(lg, key, fn):
    rec = lg.setdefault(key, {"tries": 0})
    if rec.get("done") or rec["tries"] >= 3:
        return
    rec["tries"] += 1
    try:
        r = fn()
        rec.update(done=True, **(r or {}))
    except Exception as e:          # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    print(key, json.dumps(rec)[:240], flush=True)


def build(stage="all", shard=0, shards=1):
    """stage units: plains + EMS units; boxes: NYC box tables; fn: FloodNet storm x box features (shardable)."""
    from experiments.flood_round3.diagnose_ee import _init
    res = json.load(open(RESERVE))
    ee = _init()
    logp = LOG if shards == 1 else LOG.replace(".json", f"_{shard}of{shards}.json")
    lg = json.load(open(logp)) if os.path.exists(logp) else {}
    if stage in ("all", "units"):
        for u in res["units"]:
            _run(lg, u["unit"], lambda u=u: plains_unit(u, ee) if u["label_family"] == "S1v3" else ems_unit(u, ee))
            json.dump(lg, open(logp, "w"), indent=1)
    boxes = sorted({b for s in res["floodnet_storms"] for b in _active_boxes(s)})
    if stage in ("all", "boxes"):
        for i, box in enumerate(boxes):
            if i % shards == shard:
                _run(lg, f"box:{box}", lambda box=box: (fn_box_table(box), None)[1])
                json.dump(lg, open(logp, "w"), indent=1)
    if stage in ("all", "fn"):
        jobs = [(s, b) for s in res["floodnet_storms"] for b in _active_boxes(s)]
        for s, box in jobs:                 # shard by box, so one box's caches (DEM, rail bridges) have one writer
            if boxes.index(box) % shards != shard or not os.path.exists(os.path.join(B.TABLES, f"{box}.npz")):
                continue
            _run(lg, f"fn:{s['peak_day']}:{box}", lambda s=s, box=box: (fn_unit_feats(s, box, ee), None)[1])
            json.dump(lg, open(logp, "w"), indent=1)
    return 0


def _merged_log():
    lg = {}
    for f in sorted(os.listdir(D.BIG)):
        if f.startswith("heldout_r3_log") and f.endswith(".json"):
            for k, v in json.load(open(os.path.join(D.BIG, f))).items():
                if v.get("done") or k not in lg:
                    lg[k] = v
    return lg


# ------------------------------------------------------------------ score
def _table(n, extra=None):
    z = np.load(os.path.join(B.TABLES, f"{n}.npz"), allow_pickle=False)
    m = json.loads(str(z["meta"]))
    ev = {k: np.full(len(z["y"]), np.nan, np.float32) for k in D.EV_FEATS + tuple(D._fine()) + tuple(D._mrms()) + tuple(D._wl())}
    ev.update(extra or {})
    return {"X": z["X"], "C": z["C"], "y": z["y"], "F": list(m["features"]), "shape": tuple(m["shape"]), "ev": ev,
            "grid": m["grid"]}


def _model(ty):
    return pickle.load(open(os.path.join(FROZEN, METHOD[ty].replace("@", "__") + ".pkl"), "rb"))


def _flat(t):
    e = t["X"][:, t["F"].index("elev_glo30")]
    return bool(np.nanstd(e) < 4.0)


def _bar(tables, members, cluster, runs, method):
    if len(members) < 1:
        return None
    out = {c: M.gain_lower_bound(tables, members, cluster, runs, c) for c in ("elev", "hand", method) if c in runs}
    m = out[method]
    passed = method not in ("elev", "hand") and m["ci"][0] > 0 and m["mean_auc"] >= 0.70 and len(members) >= 5
    return {"units": len(members), "clusters": len({cluster[n] for n in members}), "candidates": out,
            "method": method, "passes_bar": bool(passed)}


def score():
    from experiments.flood_round3 import wl_feats as WF
    res = json.load(open(RESERVE))
    lg = _merged_log()
    units = {u["unit"]: u for u in res["units"]}
    ok = [n for n, u in units.items() if lg.get(n, {}).get("usable")]
    tables, runs = {}, {"elev": {}, "hand": {}, "method": {}}
    models = {ty: _model(ty) for ty in METHOD}
    from experiments.flood_round3 import freeze_r3 as FZ
    for n in ok:
        u = units[n]
        extra = {}
        if u["type"] == "waterlogging":
            extra = WF.one(n, None) if os.path.exists(os.path.join(WF.OUTD, f"{n}.npz")) else {}
        t = _table(n, extra)
        tables[n] = t
        runs["elev"][n] = M.anchor_score(t, "elev")
        runs["hand"][n] = M.anchor_score(t, "hand")
        if u["type"] in METHOD:
            runs["method"][n] = FZ.predict(models[u["type"]], t).astype(np.float64)
    cluster = {n: units[n]["event_id"] for n in ok}
    report = {"sealed_sha256_file": os.path.basename(RESERVE), "by_type": {}, "dropouts": {n: lg.get(n) for n in units if n not in ok}}
    for ty in ("waterlogging", "fluvial", "pluvial", "coastal", "compound", "flash_flood"):
        mem = [n for n in ok if units[n]["type"] == ty]
        meth = "method" if ty in METHOD else "elev"
        r = {"all": _bar(tables, mem, cluster, runs, meth) if mem else None}
        if mem:
            for lab, sub in (("new_places", [n for n in mem if not units[n]["near_dev_unit_20km"]]),
                             ("flat", [n for n in mem if _flat(tables[n])]), ("hilly", [n for n in mem if not _flat(tables[n])])):
                r[lab] = _bar(tables, sub, cluster, runs, meth) if sub else None
            fams = sorted({units[n]["label_family"] for n in mem})
            r["by_label_family"] = {f: _bar(tables, [n for n in mem if units[n]["label_family"] == f], cluster, runs, meth)
                                    for f in fams}
        r["role"] = {"waterlogging": "verdict", "pluvial": "secondary (public EMS rain AOIs); the rain verdict is FloodNet",
                     "flash_flood": "not testable (no login-free reserve unit with an accepted label)"}.get(
            ty, "informational: the DEV rule chose elevation (R35), so no method can pass")
        report["by_type"][ty] = r
    report["floodnet"] = score_floodnet(res, models["pluvial"])
    json.dump(report, open(os.path.join(OUT, "test_r3.json"), "w"), indent=1, default=str)
    print(json.dumps({ty: (v["all"] or {}).get("passes_bar") for ty, v in report["by_type"].items()}), flush=True)
    return 0


def score_floodnet(res, model):
    from experiments.flood_round3 import freeze_r3 as FZ
    grid = _city_grid()
    H, W = grid["shape"]
    tables, runs, cluster, per = {}, {"elev": {}, "hand": {}, "method": {}}, {}, {}
    flat_box, cell_box = {}, {}
    for s in res["floodnet_storms"]:
        lab, info = fn_labels(s)
        y = np.full(H * W, -1, np.int8)
        sc = {k: np.full(H * W, np.nan) for k in runs}
        boxcache = {}
        for (r, c), (st, sensor) in lab.items():
            box = fn_box_of(float(sensor["longitude"]), float(sensor["latitude"]))
            if box is None:
                continue
            if box not in boxcache:
                try:
                    n, ev = fn_unit_feats(s, box, None)
                except Exception:          # noqa: BLE001  (box features missing -> its cells are unscored, reported)
                    boxcache[box] = None
                    continue
                t = _table(box, ev)
                boxcache[box] = (t, FZ.predict(model, t), M.anchor_score(t, "elev"), M.anchor_score(t, "hand"))
                flat_box[box] = _flat(t)
            if boxcache[box] is None:
                continue
            t, pm, pe, ph = boxcache[box]
            br, bc = _cell(t["grid"], float(sensor["longitude"]), float(sensor["latitude"]))
            k = br * t["shape"][1] + bc
            if not (0 <= br < t["shape"][0] and 0 <= bc < t["shape"][1]):
                continue
            i = r * W + c
            cell_box[(s["peak_day"], i)] = box
            y[i] = 1 if st == "wet" else 0
            sc["method"][i], sc["elev"][i], sc["hand"][i] = pm[k], pe[k], ph[k]
        u = f"r3fn_{s['peak_day']}"
        nw, nd = int((y == 1).sum()), int((y == 0).sum())
        per[u] = {"wet_cells": nw, "dry_cells": nd, **info, "usable": nw >= 50 and nd >= 50}
        if per[u]["usable"]:
            tables[u] = {"y": y, "shape": (H, W)}
            for k in runs:
                runs[k][u] = sc[k]
            cluster[u] = u
    mem = sorted(tables)
    out = {"units": per, "verdict_rule": "rain verdict on usable FloodNet storms; >= 5 needed, else not testable"}
    out["all"] = _bar(tables, mem, cluster, runs, "method") if mem else None
    out["testable"] = len(mem) >= 5
    for lab, want in (("flat", True), ("hilly", False)):      # criteria §9 / FLOODNET rule 11, reporting only
        sub_t = {}
        for u in mem:
            y = tables[u]["y"].copy()
            pk = u[len("r3fn_"):]
            for i in np.flatnonzero(y >= 0):
                if flat_box.get(cell_box.get((pk, int(i)))) is not want:
                    y[i] = -1
            sub_t[u] = {"y": y, "shape": tables[u]["shape"]}
        sm = [u for u in mem if (sub_t[u]["y"] == 1).sum() >= 1 and (sub_t[u]["y"] == 0).sum() >= 1]
        out[lab] = _bar(sub_t, sm, cluster, runs, "method") if sm else None
    return out


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "build":
        return build(a[1] if len(a) > 1 else "all", int(a[2]) if len(a) > 2 else 0, int(a[3]) if len(a) > 3 else 1)
    return {"score": score}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
