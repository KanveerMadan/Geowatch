"""
Round 3, Phase 1: diagnosis on BURNED units only (catalog.py).

    python -m experiments.flood_round3.diagnose     # writes results/diagnosis.json

Offline parts (cached tables, round-2 DEV LRO predictions, round-2 held-out AUCs):
  a  information ceiling: within-unit rank correlation of the learned score with elevation;
     SHAP share of terrain features (LightGBM pred_contrib);
  b  image timing: label-image lag vs AUC and gain;
  c  terrain cutoffs in each label source (HAND, slope, height above local low);
  d  radar-prone cells (steep slopes; built-up cells) among labelled cells;
  f  power: per-unit gain spread -> units needed for 90 % power;
  g  compound: per unit, the learned model vs elevation, and how far its features sit
     from the training compound units;
  h  resolution: flooded-patch sizes vs the 30 m cell.
Parts needing new data (peak timing from drivers, independent-source agreement,
radar geometry) are in diagnose_ee.py.
"""
from __future__ import annotations

import json
import os
import pickle

import numpy as np
from scipy import ndimage
from scipy.stats import norm, spearmanr

from experiments.flood_round2 import features_r2 as R
from experiments.flood_round2 import model_v3 as M3
from experiments.flood_validation.harness import auc

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
TYPES = M3.TYPES
F = R.FEATURES_R2
TERRAIN = {f for f in F if any(f.startswith(p) for p in ("slope_", "curv_", "tpi990_", "relmin2km_", "depr_",
                                                          "handmap_", "elev", "hand_", "valley_floor", "spi",
                                                          "upslope_", "log_acc30", "kirpich"))} | {"hand_merit"}
CHOSEN_R2 = {"fluvial": "resid_lgbm", "pluvial": "elev", "waterlogging": "full_lr", "flash_flood": "resid_lgbm",
             "coastal": "elev", "compound": "full_lgbm"}
LEARNED_FOR = {"fluvial": "resid_lgbm", "pluvial": "resid_lgbm", "waterlogging": "full_lr",
               "flash_flood": "resid_lgbm", "coastal": "coastal_lgbm", "compound": "full_lgbm"}


def catalog():
    return json.load(open(os.path.join(OUT, "burned_catalog.json")))


def table(row):
    z = np.load(os.path.expanduser(row["table"]), allow_pickle=False)
    return {"X": z["X"], "C": z["C"], "y": z["y"], "meta": json.loads(str(z["meta"]))}


def col(t, f):
    return t["X"][:, F.index(f)].astype(np.float64)


def _auc(s, y):
    ok = (y >= 0) & np.isfinite(s)
    yy = y[ok]
    return float(auc(s[ok], (yy == 1).astype(int), (yy == 0).astype(int)))


def per_unit_aucs(cat):
    """{unit: {cand: auc}}: DEV from round-2 LRO predictions, r2_test from heldout_r2.json."""
    r2 = json.load(open(os.path.join(os.path.dirname(HERE), "flood_round2", "results", "heldout_r2.json")))
    runs = M3.load_runs("lro")
    out = {}
    for n, row in cat.items():
        if row["role"] == "r2_test":
            out[n] = {k: v for k, v in r2["units"][n]["auc"].items() if ":" not in k}
            continue
        t = table(row)
        ok = t["y"] >= 0
        for r in runs.values():
            ok &= np.isfinite(r[n])
        y = t["y"][ok]
        out[n] = {k: round(_auc(r[n][ok].astype(np.float64), y), 4) for k, r in runs.items()}
    return out


def best_baseline(a):
    return "elev" if a.get("elev", 0) >= a.get("hand", 0) else "hand"


# ── a: information ceiling ─────────────────────────────────────────────
def part_a(cat):
    runs = M3.load_runs("lro")
    res = {}
    for cand in ("full_lr", "resid_lgbm", "full_lgbm"):
        rhos = {}
        for n, row in cat.items():
            if row["role"] != "dev":
                continue
            t = table(row)
            ok = (t["y"] >= 0) & np.isfinite(runs[cand][n]) & np.isfinite(col(t, "elev_glo30"))
            if ok.sum() < 100:
                continue
            rhos[n] = float(spearmanr(runs[cand][n][ok], -col(t, "elev_glo30")[ok]).statistic)
        by = {ty: [rhos[n] for n in rhos if ty in cat[n]["tags"]] for ty in TYPES}
        res[cand] = {"rho_with_minus_elev_median": round(float(np.median(list(rhos.values()))), 3),
                     "by_type_median": {ty: (round(float(np.median(v)), 3) if v else None) for ty, v in by.items()}}
    # SHAP share of terrain features in the final resid_lgbm / full_lgbm (trained on all DEV)
    shap = {}
    for cand in ("resid_lgbm", "full_lgbm"):
        m = pickle.load(open(os.path.join(M3.CACHE, f"final__{cand}.pkl"), "rb"))
        m = m["model"]
        lg = m["lgbm"] if isinstance(m, dict) else m
        feats = M3.FULL
        rng = np.random.default_rng(0)
        share_by = {ty: [] for ty in TYPES}
        for n, row in cat.items():
            t = table(row)
            ok = np.where(t["y"] >= 0)[0]
            idx = rng.choice(ok, min(800, len(ok)), replace=False)
            con = lg.predict(t["X"][idx][:, M3.cols(feats)], pred_contrib=True)[:, :-1]
            a = np.abs(con).sum(axis=0)
            terr = sum(a[i] for i, f in enumerate(feats) if f in TERRAIN)
            for ty in row["tags"]:
                if ty in share_by:
                    share_by[ty].append(float(terr / a.sum()))
        shap[cand] = {ty: (round(float(np.median(v)), 3) if v else None) for ty, v in share_by.items()}
        if cand == "resid_lgbm":
            shap[cand + "_note"] = ("resid_lgbm's base is an elevation-only logistic fit; the SHAP share is of the "
                                    "boosted correction only, so the whole score is even more elevation")
    res["shap_terrain_share_median"] = shap
    return res


def part_a2(cat):
    """Where elevation is wrong (river, waterlogging, coastal, compound units). Take
    elevation's top-k cells (k = flooded count) as its 'wet' call.
    - misses (flooded, not in top-k): share with GLO-30 HAND < 2 m (near the river,
      above the box's low ground because the water surface slopes downstream);
    - false alarms (dry, in top-k): share in a closed depression (depr_glo30 > 0.3 m),
      share > 1 km from mapped water (unconnected low ground or another reach), and
      share with HAND >= 2 m (low in the box but not low relative to its river)."""
    out = {}
    for ty in ("fluvial", "waterlogging", "coastal", "compound", "flash_flood"):
        rows = []
        for n, row in cat.items():
            if ty not in row["tags"]:
                continue
            t = table(row)
            y = t["y"]
            lab = y >= 0
            e = col(t, "elev_glo30")
            ok = lab & np.isfinite(e)
            k = int((y[ok] == 1).sum())
            if k < 50:
                continue
            idx = np.flatnonzero(ok)
            top = np.zeros(len(y), bool)
            top[idx[np.argsort(e[idx])[:k]]] = True
            miss = ok & (y == 1) & ~top
            fa = ok & (y == 0) & top
            hm = col(t, "handmap_glo30")
            dep = col(t, "depr_glo30")
            dw = col(t, "dist_water_m")
            sh = lambda m, c: float(np.mean(c[m])) if m.sum() else np.nan  # noqa: E731
            rows.append({"miss_share": float(miss.sum() / max(1, k)),
                         "miss_near_river_hand_lt2": sh(miss, hm < 2),
                         "fa_in_depression": sh(fa, dep > 0.3),
                         "fa_far_from_water_gt1km": sh(fa, dw > 1000),
                         "fa_hand_ge2": sh(fa, hm >= 2)})
        if rows:
            out[ty] = {"units": len(rows), **{k: round(float(np.nanmedian([r[k] for r in rows])), 3) for k in rows[0]}}
    return out


# ── b: image timing ────────────────────────────────────────────────────
def part_b(cat, aucs):
    rows = []
    for n, row in cat.items():
        lag = row.get("lag_days_min")
        a = aucs[n]
        for ty in row["tags"]:
            if ty not in TYPES:
                continue
            lc = LEARNED_FOR[ty]
            bb = best_baseline(a)
            rows.append({"unit": n, "type": ty, "lag": lag, "kind": row.get("kind"), "elev": a.get("elev"),
                         "hand": a.get("hand"), "learned": a.get(lc),
                         "gain": None if a.get(lc) is None else a[lc] - a[bb]})
    out = {"bins": {}, "spearman": {}}
    bins = [(-99, 1, "<=1 d"), (2, 3, "2-3 d"), (4, 7, "4-7 d"), (8, 999, ">7 d")]
    for ty in TYPES + ("all",):
        rr = [r for r in rows if (ty == "all" or r["type"] == ty) and r["lag"] is not None]
        out["bins"][ty] = {}
        for lo, hi, lab in bins:
            b = [r for r in rr if lo <= r["lag"] <= hi]
            if not b:
                continue
            out["bins"][ty][lab] = {"n": len(b),
                                    **{k: round(float(np.nanmean([r[k] for r in b if r[k] is not None])), 3)
                                       for k in ("elev", "hand", "learned", "gain")}}
        if len(rr) >= 6:
            out["spearman"][ty] = {k: round(float(spearmanr([r["lag"] for r in rr if r[k] is not None],
                                                            [r[k] for r in rr if r[k] is not None]).statistic), 3)
                                   for k in ("elev", "learned", "gain")}
    out["rows"] = rows
    return out


# ── c: terrain cutoffs per label source ───────────────────────────────
def part_c(cat):
    """For each unit: the 99.5th percentile of HAND / slope among flooded cells,
    and the share of labelled dry cells above it. Pooled per source: P(flooded | HAND bin).
    A mask shows as P = 0 above one threshold in many units of one source, with many
    'dry' cells there."""
    bins = np.array([0, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50, 1e9])
    pooled, units = {}, {}
    for n, row in cat.items():
        t = table(row)
        y = t["y"]
        hand = col(t, "hand_merit")
        slope = col(t, "slope_glo30")
        lab = y >= 0
        fl = y == 1
        if fl.sum() < 20:
            continue
        src = row.get("kind", "?")
        if src == "ems":
            sens = row.get("sensors") or ["?"]
            src = "ems_sar" if any(s in ("Sentinel-1", "COSMO-SkyMed", "RADARSAT-2", "TerraSAR-X", "PAZ", "ICEYE",
                                          "SAOCOM", "RCM", "Capella") or "SAR" in s for s in sens) else "ems_optical"
        h99 = float(np.nanpercentile(hand[fl], 99.5))
        s99 = float(np.nanpercentile(slope[fl], 99.5))
        units[n] = {"source": src, "hand_p995_flooded": round(h99, 2),
                    "dry_share_above": round(float(np.mean(hand[lab & ~fl] > h99)), 3),
                    "slope_p995_flooded": round(s99, 1),
                    "dry_share_steeper": round(float(np.mean(slope[lab & ~fl] > s99)), 3),
                    "unobserved_share": round(float(np.mean(~lab)), 3)}
        k = np.digitize(hand, bins) - 1
        p = pooled.setdefault(src, {"fl": np.zeros(len(bins) - 1), "n": np.zeros(len(bins) - 1)})
        for b in range(len(bins) - 1):
            m = lab & (k == b)
            p["n"][b] += m.sum()
            p["fl"][b] += (m & fl).sum()
    curves = {s: {f"{bins[b]:g}-{bins[b + 1]:g}": {"n": int(v["n"][b]),
                                                  "p_flooded": round(float(v["fl"][b] / max(1, v["n"][b])), 4)}
                  for b in range(len(bins) - 1)} for s, v in pooled.items()}
    # Hard-cutoff test: per source, the spread of hand_p995 across units. A mask gives a tight
    # cluster (e.g. all near 15 m) with a large dry share above it.
    summ = {}
    for s in pooled:
        v = [u for u in units.values() if u["source"] == s]
        hp = np.array([u["hand_p995_flooded"] for u in v])
        summ[s] = {"units": len(v), "hand_p995_median": round(float(np.median(hp)), 2),
                   "hand_p995_iqr": [round(float(np.percentile(hp, 25)), 2), round(float(np.percentile(hp, 75)), 2)],
                   "hand_p995_max": round(float(hp.max()), 2),
                   "median_dry_share_above": round(float(np.median([u["dry_share_above"] for u in v])), 3),
                   "units_with_unobserved_gt_5pct": int(sum(u["unobserved_share"] > 0.05 for u in v))}
    return {"per_source": summ, "p_flooded_by_hand": curves, "units": units}


# ── d: radar-prone cells ──────────────────────────────────────────────
def part_d(cat):
    out = {}
    for ty in TYPES:
        st = []
        for n, row in cat.items():
            if ty not in row["tags"]:
                continue
            t = table(row)
            lab = t["y"] >= 0
            slope = col(t, "slope_glo30")
            built = np.fmax(np.nan_to_num(col(t, "wc_built")), np.nan_to_num(col(t, "ghsl_built_frac")))
            st.append({"unit": n, "kind": row.get("kind"),
                       "steep20_share_labelled": float(np.mean(slope[lab] > 20)),
                       "steep20_share_flooded": float(np.mean(slope[t["y"] == 1] > 20)) if (t["y"] == 1).any() else None,
                       "built50_share_labelled": float(np.mean(built[lab] >= 0.5)),
                       "built50_share_flooded": float(np.mean(built[t["y"] == 1] >= 0.5)) if (t["y"] == 1).any() else None,
                       "built50_flood_rate": float(np.mean(t["y"][lab & (built >= 0.5)] == 1)) if (lab & (built >= 0.5)).sum() > 50 else None,
                       "open_flood_rate": float(np.mean(t["y"][lab & (built < 0.5)] == 1)) if (lab & (built < 0.5)).sum() > 50 else None})
        if not st:
            continue
        med = lambda k: round(float(np.nanmedian([s[k] for s in st if s[k] is not None])), 3) if any(s[k] is not None for s in st) else None  # noqa: E731
        out[ty] = {"units": len(st), **{k: med(k) for k in ("steep20_share_labelled", "steep20_share_flooded",
                                                             "built50_share_labelled", "built50_share_flooded",
                                                             "built50_flood_rate", "open_flood_rate")},
                   "s1_units_built_rate_lt_half_open": sum(1 for s in st if s["kind"] == "s1_vvdrop" and s["built50_flood_rate"] is not None
                                                           and s["open_flood_rate"] and s["built50_flood_rate"] < 0.5 * s["open_flood_rate"]),
                   "s1_units": sum(1 for s in st if s["kind"] == "s1_vvdrop")}
    return out


# ── f: power ──────────────────────────────────────────────────────────
def part_f(cat, aucs):
    out = {}
    z = norm.ppf(0.975) + norm.ppf(0.90)
    for ty in TYPES:
        g = {}
        for n, row in cat.items():
            if ty not in row["tags"]:
                continue
            a = aucs[n]
            lc = LEARNED_FOR[ty]
            if a.get(lc) is None:
                continue
            g[n] = (a[lc] - a[best_baseline(a)], row["role"])
        if len(g) < 4:
            continue
        v = np.array([x for x, _ in g.values()])
        sd = float(v.std(ddof=1))
        need = {}
        for d in (0.01, 0.02, 0.03, 0.05):
            n = int(np.ceil((z * sd / d) ** 2))
            need[f"delta_{d}"] = {"n": n, "n_plus_30pct": int(np.ceil(n * 1.3))}
        out[ty] = {"units": len(v), "mean_gain": round(float(v.mean()), 4), "sd_gain": round(sd, 4),
                   "dev_mean_gain": round(float(np.mean([x for x, r in g.values() if r == "dev"])), 4),
                   "r2_mean_gain": round(float(np.mean([x for x, r in g.values() if r == "r2_test"] or [np.nan])), 4),
                   "units_needed_90pct_power": need,
                   "note": "normal approximation on unit means; the cluster x block bootstrap is wider, so these are lower bounds"}
    return out


# ── g: compound ───────────────────────────────────────────────────────
def part_g(cat, aucs):
    dev_c = [n for n, r in cat.items() if r["role"] == "dev" and "compound" in r["tags"]]
    test_c = [n for n, r in cat.items() if r["role"] == "r2_test" and "compound" in r["tags"]]
    keyf = ("elev_glo30", "dist_coast_m", "rain_p999_mm_h", "hand_merit", "wc_built", "sea_spill_m", "jrc_occurrence")
    ref = {f: np.concatenate([col(table(cat[n]), f) for n in dev_c]) for f in keyf}
    units = {}
    for n in test_c:
        t = table(cat[n])
        a = aucs[n]
        units[n] = {"elev": a.get("elev"), "hand": a.get("hand"), "full_lgbm": a.get("full_lgbm"),
                    "coastal_lgbm": a.get("coastal_lgbm"), "resid_lgbm": a.get("resid_lgbm"),
                    "lag_days": cat[n].get("lag_days_min"), "kind": cat[n].get("kind"),
                    "flooded": cat[n]["flooded"], "dry": cat[n]["dry"],
                    "feature_median_pct_in_dev_compound": {f: round(float(np.mean(ref[f][np.isfinite(ref[f])] <= np.nanmedian(col(t, f)))), 3)
                                                           for f in keyf}}
    return {"dev_compound_units": dev_c, "test_units": units}


# ── h: resolution ─────────────────────────────────────────────────────
def part_h(cat):
    out = {}
    for ty in ("pluvial", "waterlogging", "fluvial"):
        sizes, small = [], []
        for n, row in cat.items():
            if ty not in row["tags"]:
                continue
            t = table(row)
            sh = tuple(t["meta"]["shape"])
            fl = (t["y"] == 1).reshape(sh)
            lab, k = ndimage.label(fl)
            if k == 0:
                continue
            s = np.bincount(lab.ravel())[1:]
            sizes.append(float(np.median(s)))
            small.append(float((s[s <= 2]).sum() / s.sum()))
        if sizes:
            out[ty] = {"units": len(sizes), "median_patch_cells": round(float(np.median(sizes)), 1),
                       "median_share_of_flooded_in_1_2_cell_patches": round(float(np.median(small)), 3)}
    return out


def main():
    cat = catalog()
    aucs = per_unit_aucs(cat)
    res = {"units": len(cat), "per_unit_auc": aucs}
    for k, f in (("a", lambda: part_a(cat)), ("a2", lambda: part_a2(cat)), ("b", lambda: part_b(cat, aucs)), ("c", lambda: part_c(cat)),
                 ("d", lambda: part_d(cat)), ("f", lambda: part_f(cat, aucs)), ("g", lambda: part_g(cat, aucs)),
                 ("h", lambda: part_h(cat))):
        res[k] = f()
        print(f"── part {k}", json.dumps({kk: vv for kk, vv in res[k].items() if kk not in ("rows", "units")}, default=str)[:1500], flush=True)
    json.dump(res, open(os.path.join(OUT, "diagnosis.json"), "w"), indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
