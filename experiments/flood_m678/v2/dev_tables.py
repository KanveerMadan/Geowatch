"""
M6–M8 v2 steps 3-4 on DEV: terrain, forcing and physics scores per usable DEV label (M8 sustained melt first).

    cd ~/gw-r3pin-r35 && PYTHONPATH=.:$HOME/gw-m678v2/experiments/flood_m678 python -B ~/gw-m678v2/experiments/flood_m678/v2/dev_tables.py

Per usable unit (>= 50 flooded and >= 50 dry cells on the 8 km box):
- terrain on a 12 km routing domain (box + 2 km margin), one exclusive-lock EE request: GLO-30
  elevation, MERIT HAND, MERIT upstream area, GLO-30 slope;
- channel cells: MERIT upa >= 10 km2;
- forcing: the WSC annual maximum discharge at the lead's station for the same water year (a measured
  peak; same gauge as the crest time, so not independent stage validation);
- per channel cell: Q = Q_g (upa / upa_g)^0.8, stage from a HAND rating curve of the cells that drain
  to that channel band (forcing.py), n = 0.05, bed slope = median channel slope (floor 1e-4);
- scores on the box: elev, hand, phys (routing.physics_score), and the ablations
  phys_seasonal (station median annual maximum Q), phys_exchanged (the Q ratio of a matched other
  incident) and phys_noconnect (stage minus HAND: same forcing, connectivity removed).
Written to the DEV store only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import numpy as np

V2 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(V2))


def _load(n):
    spec = importlib.util.spec_from_file_location(f"v2{n}", os.path.join(V2, f"{n}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


S, R, F = _load("storage"), _load("routing"), _load("forcing")
MARGIN_M = 2000.0
UPA_CHANNEL = 10.0
WSC_Q = os.path.expanduser("~/.cache/geowatch/m678v2/sources/wsc/annual_peaks_discharge.json")


def wsc_discharge():
    import urllib.request
    if not os.path.exists(WSC_Q):
        feats, off = [], 0
        while True:
            u = ("https://api.weather.gc.ca/collections/hydrometric-annual-peaks/items?f=json&limit=10000"
                 f"&offset={off}&DATA_TYPE_EN=Discharge&PEAK_CODE_EN=Maximum")
            with urllib.request.urlopen(u, timeout=300) as r:
                d = json.load(r)
            feats += d["features"]
            if len(d["features"]) < 10000:
                break
            off += 10000
        json.dump(feats, open(WSC_Q, "w"))
    by = {}
    for f in json.load(open(WSC_Q)):
        p = f["properties"]
        if p.get("DATE") and p.get("PEAK") is not None:
            by.setdefault(p["STATION_NUMBER"], {})[p["DATE"][:4]] = float(p["PEAK"])
    return by


def geoglows_q(m):
    """(peak Q in [crest - 3 d, crest + 3 d], median annual max 1984-2021, source) at the GEOGloWS reach
    with the largest upstream area inside the 8 km box (v1's geoglows_crests helpers)."""
    import geoglows_crests as G
    ix = {k: v for k, v in np.load(G.REACHES).items()}
    r = G.reach(ix, tuple(m["bbox"]))
    if r is None:
        return None, None, "no GEOGloWS reach"
    t, q = G.series(r["link"])
    c = m["crest_utc"][0][:10]
    from datetime import date, timedelta
    d0 = date.fromisoformat(c)
    win = [(d0 + timedelta(days=k)).isoformat() for k in range(-3, 4)]
    qp = max((float(v) for x, v in zip(t, q) if x in win), default=None)
    years = {}
    for x, v in zip(t, q):
        if "1984" <= x[:4] <= "2021":
            years[x[:4]] = max(years.get(x[:4], 0.0), float(v))
    med = float(np.median(list(years.values()))) if len(years) >= 5 else None
    return qp, med, f"GEOGloWS v2 reach {r['link']} (no WSC discharge)"


def terrain(ee, grid_bbox):
    from experiments.flood_learned import fetch as Fe
    from susceptibility.hydro_rasters import compute_pixels, utm_grid
    t, shape, crs = utm_grid(grid_bbox)
    region = ee.Geometry.Rectangle(list(grid_bbox))
    dem = Fe._mosaic(Fe.GLO30_ASSET, region, "DEM")
    merit = ee.Image("MERIT/Hydro/v1_0_1")
    bands = {"z": dem, "hand": merit.select("hnd"), "upa": merit.select("upa"), "slope": ee.Terrain.slope(dem)}
    out = {}
    for k, im in bands.items():                       # one band per request (40 km domains hit EE's memory limit)
        a = compute_pixels(im.rename(k).toFloat(), t, shape, crs, f"v2 terrain {k}")
        out[k] = np.asarray(a[k], float)
    return t, shape, crs, out


def stages_q(T, qcell):
    """Per-cell stage from a per-cell discharge field (per-reach forcing): one rating per upa band,
    driven by the band's median discharge."""
    from scipy.ndimage import distance_transform_edt
    upa, hand, slope = np.nan_to_num(T["upa"]), T["hand"], np.tan(np.radians(np.nan_to_num(T["slope"])))
    ch = (upa >= UPA_CHANNEL) & np.isfinite(qcell)
    st = np.full(upa.shape, np.nan)
    if not ch.any():
        return ch, st
    _, (ri, ci) = distance_transform_edt(~ch, return_indices=True)
    band = np.floor(np.log2(np.maximum(upa, 1e-3))).astype(int)
    cellband = band[ri, ci]
    s_bed = max(float(np.nanmedian(slope[ch])), 1e-4)
    for b in np.unique(band[ch]):
        mem = ch & (band == b)
        cat = cellband == b
        ys, Q = F.rating(hand[cat], slope[cat], 900.0, mem.sum() * 30.0, s_bed)
        for qv in np.unique(np.round(qcell[mem], 1)):
            sel = mem & (np.round(qcell, 1) == qv)
            st[sel] = F.stage_for(float(qv), ys, Q)
    return ch, st


def stages(T, q_g, upa_g):
    """Per-cell stage (m above local bed) on channel cells; NaN elsewhere."""
    from scipy.ndimage import distance_transform_edt
    upa, hand, slope = np.nan_to_num(T["upa"]), T["hand"], np.tan(np.radians(np.nan_to_num(T["slope"])))
    ch = upa >= UPA_CHANNEL
    st = np.full(upa.shape, np.nan)
    if not ch.any() or not q_g or not upa_g:
        return ch, st
    _, (ri, ci) = distance_transform_edt(~ch, return_indices=True)
    band = np.floor(np.log2(np.maximum(upa, 1e-3))).astype(int)
    cellband = band[ri, ci]
    s_bed = max(float(np.nanmedian(slope[ch])), 1e-4)
    for b in np.unique(band[ch]):
        mem = ch & (band == b)
        cat = cellband == b
        reach_len = mem.sum() * 30.0
        ys, Q = F.rating(hand[cat], slope[cat], 900.0, reach_len, s_bed)
        q = F.scale_discharge(q_g, upa_g, float(np.median(upa[mem])))
        st[mem] = F.stage_for(q, ys, Q)
    return ch, st


def scores(T, ch, st, crop):
    z = T["z"]
    g, lv = R.channel_groups(z, ch, st)
    phys = R.physics_score(z, g, lv) if g else np.full(z.shape, np.nan)
    from scipy.ndimage import distance_transform_edt
    _, (ri, ci) = distance_transform_edt(~ch, return_indices=True) if ch.any() else (None, (None, None))
    noconn = (st[ri, ci] - T["hand"]) if ch.any() else np.full(z.shape, np.nan)
    r0, c0, h, w = crop
    sl = (slice(r0, r0 + h), slice(c0, c0 + w))
    return phys[sl], noconn[sl]


def main():
    import labels_m678 as LM
    from experiments.flood_validation import references as Rf
    from experiments.flood_validation.harness_round4 import window_in
    from susceptibility.hydro_rasters import utm_grid
    S.init()
    qtab = wsc_discharge()
    ee = LM.init_ee()
    ldir = S.dev_path("labels")
    out_dir = S.dev_path("tables")
    os.makedirs(out_dir, exist_ok=True)
    units = []
    for f in sorted(os.listdir(ldir)):
        z = np.load(os.path.join(ldir, f), allow_pickle=False)
        m = json.loads(str(z["meta"]))
        if m.get("dropout") or (m.get("flooded_cells") or 0) < 50 or (m.get("dry_cells") or 0) < 50:
            continue
        units.append((f, m))
    meds = {}
    for f, m in units:
        p = os.path.join(out_dir, f)
        stn = m["lead"].split(":")[1]
        yr = m["date"][:4]
        q_g = qtab.get(stn, {}).get(yr)
        hist = [v for y, v in qtab.get(stn, {}).items() if "1984" <= y <= "2021"]
        meds[f] = (q_g, float(np.median(hist)) if len(hist) >= 5 else None, "WSC annual maximum discharge")
        if q_g is None:                                          # water-level-only station: GEOGloWS (last resort)
            meds[f] = geoglows_q(m)
        if os.path.exists(p):
            continue
        lat, lon = m["centre"]
        dom = Rf.square_bbox(lat, lon, 8000.0 + 2 * MARGIN_M)
        t, shape, crs, T = terrain(ee, dom)
        bt, bshape, _ = utm_grid(tuple(m["bbox"]))
        r0, c0 = window_in(t, shape, bt, bshape)
        crop = (r0, c0, bshape[0], bshape[1])
        ri, ci = shape[0] // 2, shape[1] // 2
        upa_g = float(np.nanmax(T["upa"]))                       # gauge reach: the trunk in the domain
        res = {}
        q_g = meds[f][0]
        for name, q in (("phys", q_g), ("phys_seasonal", meds[f][1])):
            ch, st = stages(T, q, upa_g)
            ps, nc = scores(T, ch, st, crop)
            res[name] = ps
            if name == "phys":
                res["phys_noconnect"] = nc
        sl = (slice(r0, r0 + bshape[0]), slice(c0, c0 + bshape[1]))
        np.savez_compressed(p + ".tmp.npz", y=np.load(os.path.join(ldir, f))["y"], elev=-T["z"][sl], hand=-T["hand"][sl],
                            **{k: v.astype(np.float32) for k, v in res.items()},
                            meta=np.array(json.dumps({**m, "q_peak": q_g, "q_median": meds[f][1], "q_source": meds[f][2], "upa_gauge": upa_g,
                                                      "domain": list(dom)})))
        os.replace(p + ".tmp.npz", p)
        print(f, "Q", q_g, "Qmed", meds[f][1], flush=True)
    json.dump({f: {"q_peak": a, "q_median": b, "source": c} for f, (a, b, c) in meds.items()},
              open(S.dev_path("tables", "forcing_index.json"), "w"), indent=1)
    print("tables", len(units))


if __name__ == "__main__":
    main()
