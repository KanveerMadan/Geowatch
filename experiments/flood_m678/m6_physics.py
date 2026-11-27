"""
M6 physics-only method (owner instruction, DECISIONS 2026-11-27): lake volume -> routed inundation.

LAHARZ-style (Iverson, Schilling & Vallance 1998, GSA Bulletin 110): a flow of volume V floods a
valley cross-section of area A = c * V^(2/3) everywhere along its path. Here c = 0.05, LAHARZ's
coefficient for water-rich lahars, the nearest published class to a glacier-lake flood.

On a box grid (30 m cells):
1. Trunk channel: MERIT upstream area >= 25 % of the box maximum (as dev_cv_m678.main_channel).
2. Every cell belongs to the cross-section of its nearest trunk cell (Euclidean nearest), and has
   a height h_i above that trunk cell.
3. A section's flooded cross-section area at level h is sum_i max(0, h - h_i) * w, w = 30 m,
   counted per trunk cell, so per 30 m of channel. The section fills to the level h* that reaches
   A, found by bisection.
4. Score per cell = h*(its section) - h_i. Positive cells are inundated; the score ranks every
   cell, so it is scored by within-event AUC like any other method. No fitting, no labels.

Volume V (m^3), resolved from metadata only (resolve_volumes, written before any reserve label):
  a. GLOF v4.2 Mean_Flood_Volume_V0 (10^6 m^3) of the same lake within +/- 15 days of the incident;
  b. else Huggel et al. (2002) area-volume scaling, V = 0.104 * A^1.42, from Lake_area_before (m^2)
     of that record;
  c. else the lake's median V0 over its GLOF v4.2 records from 2013 onward;
  d. else a published volume cited in event_evidence.json;
  e. else the median V0 of all ice-dammed GLOF v4.2 records from 2013 onward (recorded as a default).
"""
from __future__ import annotations

import json
import os
import re
import zipfile
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
C_WATER = 0.05
CELL_M = 30.0
GLOF_ODS = os.path.expanduser("~/.cache/geowatch/flood_m678/archives/glof.ods")
VOLUMES = os.path.join(HERE, "lake_volumes_m678.json")
LAKE_OF_SITE = {"mendenhall": r"^Suicide", "taku": r"^Lake No Lake", "kenai-snow": r"^(Snow|Moose)$",
                "salmon-hyder": r"^Summit Lake", "kennicott": r"^Hidden Creek", "sveinstindur": r"Skaft",
                "grimsvotn-gigjukvisl": r"r[ií]msv"}
PUBLISHED = {  # (d): published release volumes cited in event_evidence.json
    "grimsvotn-gigjukvisl-2021-12-04": (0.92e9, "EGU22-8240: about 0.92 km3 released 14 Nov - 10 Dec 2021"),
}


def laharz_score(elev, upa, volume_m3, trunk_share=0.25, c=C_WATER, cell=CELL_M):
    from scipy.ndimage import distance_transform_edt
    u = np.nan_to_num(upa, nan=0.0)
    if not np.isfinite(elev).any() or u.max() <= 0:
        return None
    trunk = u >= trunk_share * u.max()
    _, (ri, ci) = distance_transform_edt(~trunk, return_indices=True)
    h = elev - elev[ri, ci]
    sec = (ri * elev.shape[1] + ci).ravel()
    hv = h.ravel()
    ok = np.isfinite(hv)
    target = c * volume_m3 ** (2.0 / 3.0)
    hstar = np.full(hv.shape, np.nan)
    order = np.argsort(sec[ok], kind="stable")
    s_sorted, h_sorted = sec[ok][order], hv[ok][order]
    idx_sorted = np.flatnonzero(ok)[order]
    bounds = np.flatnonzero(np.diff(s_sorted)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(s_sorted)]):
        hs = h_sorted[a:b]
        lo, hi = float(np.min(hs)), float(np.min(hs)) + 1.0
        while np.sum(np.clip(hi - hs, 0, None)) * cell < target and hi - lo < 1e4:
            hi = lo + 2 * (hi - lo)
        for _ in range(40):
            mid = (lo + hi) / 2
            if np.sum(np.clip(mid - hs, 0, None)) * cell < target:
                lo = mid
            else:
                hi = mid
        hstar[idx_sorted[a:b]] = hi
    return (hstar - hv).reshape(elev.shape).astype(np.float32)


def _glof_records():
    import xml.etree.ElementTree as ET
    import discover as D
    rows = []
    with zipfile.ZipFile(GLOF_ODS) as z, z.open("content.xml") as s:
        for _, row in ET.iterparse(s, events=("end",)):
            if row.tag == D.TABLE + "table":
                break
            if row.tag != D.TABLE + "table-row":
                continue
            vals = []
            for cell in row:
                v = cell.get(D.OFFICE + "value") or cell.get(D.OFFICE + "date-value") or "".join(cell.itertext())
                vals.extend([v.strip()] * min(int(cell.get(D.TABLE + "number-columns-repeated", "1")), 80 - len(vals)))
                if len(vals) >= 80:
                    break
            row.clear()
            rows.append(vals)
    cols = rows[0]
    return [dict(zip(cols, r)) for r in rows[3:] if any(r)]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def resolve_volumes(incidents):
    """{incident: {"volume_m3", "rule", "detail"}} by rules a-e, metadata only."""
    recs = _glof_records()
    dated = []
    for r in recs:
        d = (r.get("Date") or r.get("Date_Min") or "")[:10]
        if re.match(r"\d{4}-\d{2}-\d{2}", d):
            dated.append((date.fromisoformat(d), r))
    ice = [_f(r["Mean_Flood_Volume_V0"]) for d, r in dated if d.year >= 2013 and r.get("Lake_type") == "ice"
           and _f(r.get("Mean_Flood_Volume_V0"))]
    default = float(np.median(ice)) * 1e6
    out = {}
    for inc in incidents:
        site, day = inc.rsplit("-", 3)[0], date.fromisoformat(inc[-10:])
        pat = LAKE_OF_SITE.get(site)
        mine = [(d, r) for d, r in dated if pat and re.search(pat, r.get("Lake") or "", re.I)]
        near = sorted((abs((d - day).days), d, r) for d, r in mine if abs((d - day).days) <= 15)
        v = None
        if near:
            _, d, r = near[0]
            if _f(r.get("Mean_Flood_Volume_V0")):
                v = (_f(r["Mean_Flood_Volume_V0"]) * 1e6, "a: GLOF v4.2 V0", f"{r['Lake']} {d}")
            elif _f(r.get("Lake_area_before")):
                a = _f(r["Lake_area_before"])
                v = (0.104 * a ** 1.42, "b: Huggel 2002 from lake area", f"{r['Lake']} {d}, A = {a:.0f} m2")
        if v is None:
            lake_v = [_f(r["Mean_Flood_Volume_V0"]) for d, r in mine if d.year >= 2013 and _f(r.get("Mean_Flood_Volume_V0"))]
            if lake_v:
                v = (float(np.median(lake_v)) * 1e6, "c: lake median V0", f"{len(lake_v)} records")
        if v is None and inc in PUBLISHED:
            v = (PUBLISHED[inc][0], "d: published", PUBLISHED[inc][1])
        if v is None:
            v = (default, "e: default (median ice-dammed V0 since 2013)", f"{len(ice)} records")
        out[inc] = {"volume_m3": round(v[0], 0), "rule": v[1], "detail": v[2]}
    return out


def main():
    import labels_m678 as LM
    incs = [r["incident"] for s in ("dev", "reserve") for r in LM.records(s) if r["type"] == "M6"]
    res = resolve_volumes(incs)
    json.dump({"method": "m6_physics.resolve_volumes (rules a-e)", "volumes": res}, open(VOLUMES, "w"), indent=1, sort_keys=True)
    for k, v in sorted(res.items()):
        print(k, v)


if __name__ == "__main__":
    main()
