"""
Audit GHS-BUILT-S against the Phase 0 VHR impervious labels.

A MEASUREMENT, not a model. No training, no regression against reflectance, no
new labelling. The question item 21 never asked: does an EXISTING global
built-surface product reach usable accuracy in informal fabric? We have
something rare -- an independent VHR-derived label on two sites -- which is
exactly the instrument for checking one.

WHY THE DISTINCTION MATTERS. GHS-BUILT-S is itself Sentinel-2-derived, so this
is NOT an independent check of Sentinel-2's capability. It IS a check of
whether a different METHOD succeeds on the same input where ours did not: JRC
built GHS-BUILT-S with Symbolic Machine Learning on PanTex-style texture and
morphological decomposition, not spectral unmixing. Item 21 established that
spectral built/paved decomposition is unrecoverable at 10 m. If a texture /
morphology method on the same imagery lands accurately, that is a statement
about METHOD, not about the imagery.

LIVE VERIFICATION FINDINGS -- three of them contradict assumptions made
upstream of this script, and are handled here rather than papered over:

  1. The asset RESOLVES. `JRC/GHSL/P2023A/GHS_BUILT_S/2020` exists with bands
     `built_surface` and `built_surface_nres`. The "UNVERIFIED -- confirm live"
     comment at `configs/exposure_constants.py:58` is stale.

  2. IT IS 100 m, NOT 10 m, and the grid is World MOLLWEIDE, not UTM/WGS84.
     Verified: nominalScale 100, crs_transform [100,0,-18041000,0,-100,9000000].
     So a cell is 10,000 m^2 and the built FRACTION is `built_surface / 10000`.
     Dividing by 100 -- which a 10 m cell would call for -- inflates every
     fraction 100x and saturates the product at 1.0 everywhere.
     `configs/exposure_constants.py:59` already says GHSL_RESOLUTION_M = 100,
     which agrees with the live check.

  3. TWELVE EPOCHS EXIST, not just the hardcoded 2020: 1975..2030 in 5-year
     steps. That changes the temporal-matching story (below).

TEMPORAL MATCHING, stated per site rather than buried
------------------------------------------------------
  Nairobi Maxar 2019-05-14 -> GHS 2020 : ~7.5 months. Close.
  Accra   UAV   2024-08-26 -> GHS 2025 : ~4 months  BUT see the caveat
                            -> GHS 2020 : ~4.4 years in a settlement that
                               changes fast.
The Accra asymmetry is real and unavoidable, so BOTH Accra epochs are reported.
CAVEAT ON 2025: GHSL R2023A's post-2020 epochs are extrapolated, not observed,
and the GEE asset carries NO property distinguishing observed from projected
(checked: only system:time_start/time_end, which merely bracket the nominal
5-year interval). 2025 is therefore treated as a PROJECTION and is not
preferred over 2020 on the strength of its nominal date alone.

WHAT IS COMPARED, AND ON WHOSE GRID
-----------------------------------
The comparison unit is the GHS 100 m Mollweide cell. The VHR label is
aggregated up to it; GHS is never resampled to the VHR grid. Each 10 m S2 cell
is assigned its containing GHS cell via `ee.Image.pixelCoordinates` evaluated
in GHS's OWN projection, so the cell assignment is done by Earth Engine in
Mollweide and no local re-projection maths is involved.

TWO COMPARISONS, TWO DIFFERENT CLAIMS -- reported separately and never merged:

  (a) GHS `built_surface` vs the VHR ROOF-ONLY fraction. Like-for-like: both
      are roofed structure. THIS is "is GHS accurate at what it measures".
      Phase 0 stored `roof` and `hard_unroofed` separately precisely so this
      is possible.

  (b) GHS `built_surface` vs the VHR IMPERVIOUS fraction (roof +
      hard_unroofed). This is "is GHS usable as a substitute for what the
      flood model needs". GHS does NOT claim to measure unroofed hard
      surface, so a shortfall here is EXPECTED and is not GHS being wrong.

THIRD SOURCE, same cells: Open Buildings footprint coverage against the same
VHR roof label. That gives a three-way read -- VHR truth, GHS (Sentinel-2 +
texture/morphology), Open Buildings (VHR-derived vectors) -- and it directly
tests the item 21 re-scope's central assumption that footprint-derived `built`
is reliable. That assumption is currently ASSERTED, not measured.

CAVEATS THAT CAP EVERY NUMBER BELOW
-----------------------------------
  * The VHR label is itself MODEL-GENERATED, at 0.711 (Accra) and 0.844
    (Nairobi) binary accuracy. It caps what any agreement number can show, and
    a low agreement CANNOT distinguish "GHS is wrong" from "our label is
    wrong" without further work.
  * Two sites, both African and informal-inclusive. A.13 applies: this does
    not generalise to formal fabric elsewhere.
  * Accra's label is the weaker one AND its temporal gap is the larger one, so
    Accra is secondary throughout.

NO BAR IS PRE-REGISTERED -- this is a measurement, not a hypothesis test. But
so the result is read against something rather than rationalised afterwards,
here is what I would consider USABLE AS A FLOOD-SUSCEPTIBILITY INPUT, written
before running:
    MAE          <= 0.15 in fraction units
    |mean bias|  <= 0.05  (systematic bias propagates into every ward)
    Spearman     >= 0.70  (susceptibility is consumed ordinally/binned)
These are a judgement, not a gate, and are reported alongside the numbers.

Usage:
    python audit_ghsl_vs_vhr.py
"""

import json
import os

import numpy as np
from scipy.stats import pearsonr, spearmanr

import ee
import vhr_sites
from ee_timeout import call as ee_call

# --- fixed before results existed ----------------------------------------
GHS_TEMPLATE = "JRC/GHSL/P2023A/GHS_BUILT_S/{year}"
GHS_CELL_M = 100                  # VERIFIED LIVE, not assumed
GHS_CELL_AREA_M2 = float(GHS_CELL_M * GHS_CELL_M)   # -> divide by 10000
EPOCHS = {"kibera": [2020], "oldfadama": [2020, 2025]}
PROJECTED_EPOCHS = {2025, 2030}   # extrapolated in GHSL R2023A
BUILTUP_THRESHOLDS = [0.5, 0.3, 0.2]   # 0.5 primary = dominant-cover semantics
MIN_10M_CELLS_PER_GHS = 80        # of ~100; else the GHS cell is edge/partial
INFORMAL_MEDIAN_FOOTPRINT_MAX_M2 = 80.0   # informal vs formal fabric split
MIN_BUILDINGS_FOR_STRATUM = 5
OB_CONFIDENCE = 0.7               # matches diagnose_open_buildings_aoi.py
SUBPIXEL_M = 1                    # matches diagnose_pure_pixels.py
USABLE_MAE, USABLE_BIAS, USABLE_SPEARMAN = 0.15, 0.05, 0.70
# -------------------------------------------------------------------------


def metrics(truth, pred):
    """GHS/OB used AS A PREDICTOR -- no fitting, no rescaling."""
    d = pred - truth
    ss_res = float(np.sum(d ** 2))
    ss_tot = float(np.sum((truth - truth.mean()) ** 2))
    return {
        "n": int(len(truth)),
        "truth_mean": float(truth.mean()), "truth_sd": float(truth.std()),
        "pred_mean": float(pred.mean()), "pred_sd": float(pred.std()),
        "pearson": float(pearsonr(truth, pred)[0]),
        "spearman": float(spearmanr(truth, pred)[0]),
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "mae": float(np.abs(d).mean()),
        "bias": float(d.mean()),
    }


def show(tag, m):
    print(f"    {tag:<26} n={m['n']:>5}  r={m['pearson']:>6.3f} "
          f"rho={m['spearman']:>6.3f}  R2={m['r2']:>7.3f}  "
          f"MAE={m['mae']:.4f}  bias={m['bias']:+.4f}")


def confusion(truth, pred, t):
    tp = int(((truth >= t) & (pred >= t)).sum())
    fp = int(((truth < t) & (pred >= t)).sum())
    fn = int(((truth >= t) & (pred < t)).sum())
    tn = int(((truth < t) & (pred < t)).sum())
    ua = tp / (tp + fp) if tp + fp else float("nan")   # user's / precision
    pa = tp / (tp + fn) if tp + fn else float("nan")   # producer's / recall
    return {"threshold": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "users_accuracy": ua, "producers_accuracy": pa,
            "overall": (tp + tn) / max(1, tp + fp + fn + tn)}


def fetch_on_s2_grid(image, crs, tr, r_lo, c_lo, nR, nC, bands, label):
    req = {"expression": image.select(bands), "fileFormat": "NUMPY_NDARRAY",
           "grid": {"dimensions": {"width": int(nC), "height": int(nR)},
                    "affineTransform": {
                        "scaleX": tr[0], "shearX": tr[1],
                        "translateX": tr[2] + c_lo * tr[0],
                        "shearY": tr[3], "scaleY": tr[4],
                        "translateY": tr[5] + r_lo * tr[4]},
                    "crsCode": crs}}
    arr = ee_call(lambda: ee.data.computePixels(req), label=label)
    return {b: np.asarray(arr[b]) for b in bands}


def load_site(key):
    """Cached VHR label raster + the S2 grid it sits on. Nothing re-classified."""
    os.environ["GW_SITE"] = key
    import importlib
    import build_vhr_impervious_label as B
    importlib.reload(vhr_sites)
    importlib.reload(B)
    import diagnose_pure_pixels as pure_diag

    site = vhr_sites.site(key)
    aoi = ee.Geometry.Rectangle(site["bbox"])
    _, info = ee_call(lambda: pure_diag.s2_grid_for(aoi), label=f"{key} grid")
    lab = np.load(os.path.join(B.SCRATCH, f"vhr_label_fractions_{key}.npz"))
    counts, valid, total = lab["counts"], lab["valid"], lab["total"]
    r_lo, c_lo = int(lab["r_lo"][0]), int(lab["c_lo"][0])
    nR, nC = valid.shape
    roof = counts[B.CLASSES.index("roof")].astype(np.float64)
    hard = counts[B.CLASSES.index("hard_unroofed")].astype(np.float64)
    return dict(key=key, site=site, aoi=aoi, crs=info["crs"],
                tr=info["transform"], r_lo=r_lo, c_lo=c_lo, nR=nR, nC=nC,
                roof=roof, hard=hard, valid=valid.astype(np.float64),
                total=total.astype(np.float64), scratch=B.SCRATCH)


def ghs_bands(year):
    """GHS built-surface bands, fetched on the 10 m S2 grid.

    This is a nearest-neighbour LOOKUP -- each 10 m cell receives the value of
    the GHS cell that contains it -- and everything is then aggregated back up
    to GHS cells. GHS is never interpolated to a finer grid.
    """
    return (ee.Image(GHS_TEMPLATE.format(year=year))
            .select(["built_surface", "built_surface_nres"]).toFloat())


# GEE reports GHS's CRS as World_Mollweide with PROJECTION Mollweide and
# semi_minor == semi_major == 6378137, i.e. a SPHERE of that radius. `+R=`
# pins PROJ to the same sphere; ESRI:54009 is not used because its ellipsoid
# handling need not match. The transform is the one GEE reports for the band.
MOLLWEIDE_PROJ = "+proj=moll +lon_0=0 +x_0=0 +y_0=0 +R=6378137 +units=m +no_defs"
GHS_TRANSFORM = [100, 0, -18041000, 0, -100, 9000000]


def ghs_cell_indices(crs, tr, r_lo, c_lo, nR, nC):
    """(cx, cy) GHS Mollweide cell index for every 10 m S2 cell.

    Computed locally rather than in Earth Engine: `ee.Image.pixelCoordinates`
    evaluated in GHS's projection returned a single constant across the whole
    extent, so it does not do what the cell assignment needs.

    This is SELF-VALIDATING and must not be trusted on its own: if the
    assignment were wrong, `built_surface` would vary within a GHS group.
    `aggregate_to_ghs` measures that spread and it is reported every run --
    0.0 is the proof that this local transform reproduces GEE's grid exactly.
    """
    from pyproj import Transformer
    xs = tr[2] + (np.arange(nC) + c_lo + 0.5) * tr[0]
    ys = tr[5] + (np.arange(nR) + r_lo + 0.5) * tr[4]
    X, Y = np.meshgrid(xs, ys)
    mx, my = Transformer.from_crs(crs, MOLLWEIDE_PROJ,
                                  always_xy=True).transform(X, Y)
    cx = np.floor((mx - GHS_TRANSFORM[2]) / GHS_TRANSFORM[0]).astype(np.int64)
    cy = np.floor((GHS_TRANSFORM[5] - my) / GHS_TRANSFORM[0]).astype(np.int64)
    return cx, cy


def ob_coverage(aoi, crs, tr):
    """Open Buildings coverage fraction per 10 m cell.

    Same construction as `diagnose_pure_pixels.pure_pixel_images`: paint at
    SUBPIXEL_M in the S2 grid's own projection so sub-cells tile the 10 m cells
    exactly, then average down. Continuous fraction, not the thresholded masks.
    """
    import diagnose_open_buildings_aoi as diag
    fc = (ee.FeatureCollection(diag.BUILDINGS_ASSET).filterBounds(aoi)
          .filter(ee.Filter.gte("confidence", OB_CONFIDENCE)))
    proj = ee.Projection(crs, list(tr))
    fine = proj.atScale(SUBPIXEL_M)
    painted = ee.Image(0).byte().paint(fc, 1).reproject(fine)
    sub = int((10 / SUBPIXEL_M) ** 2)
    return (painted.reduceResolution(ee.Reducer.mean(), maxPixels=sub + 16)
            .reproject(proj).rename("ob_cover"))


def building_stats_per_ghs(aoi, gcx, gcy, crs, tr, r_lo, c_lo):
    """Exact median footprint area per GHS cell, from downloaded polygons.

    Only ~12k-19k buildings per extent, so the true median is affordable and
    an area-weighted raster approximation is not needed.
    """
    import diagnose_open_buildings_aoi as diag
    fc = (ee.FeatureCollection(diag.BUILDINGS_ASSET).filterBounds(aoi)
          .filter(ee.Filter.gte("confidence", OB_CONFIDENCE)))

    def add_xy(f):
        c = f.geometry().centroid(1).coordinates()
        return ee.Feature(None, {"a": f.get("area_in_meters"),
                                 "lon": c.get(0), "lat": c.get(1)})

    rows = ee_call(
        lambda: ee.data.computeFeatures(
            {"expression": fc.map(add_xy),
             "fileFormat": "PANDAS_DATAFRAME"}
        ).to_dict("records"), label="open buildings download")
    if not rows:
        return {}
    lon = np.array([r["lon"] for r in rows], float)
    lat = np.array([r["lat"] for r in rows], float)
    area = np.array([r["a"] for r in rows], float)

    # buildings -> their 10 m S2 cell -> that cell's GHS cell
    from pyproj import Transformer
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x, y = tf.transform(lon, lat)
    cc = np.floor((x - tr[2]) / tr[0]).astype(int) - c_lo
    rr = np.floor((y - tr[5]) / tr[4]).astype(int) - r_lo
    ok = (rr >= 0) & (rr < gcx.shape[0]) & (cc >= 0) & (cc < gcx.shape[1])
    rr, cc, area = rr[ok], cc[ok], area[ok]
    keys = list(zip(gcx[rr, cc].tolist(), gcy[rr, cc].tolist()))
    out = {}
    for k, a in zip(keys, area):
        out.setdefault(k, []).append(a)
    return {k: (float(np.median(v)), len(v)) for k, v in out.items()}


def aggregate_to_ghs(d, gh, ob, cx, cy):
    """Group 10 m cells by their GHS cell; VHR goes up, GHS never comes down."""
    bs = np.asarray(gh["built_surface"], dtype=np.float64)

    usable = (d["valid"] > 0) & ((d["valid"] / np.maximum(d["total"], 1)) >= 0.60)
    usable &= np.isfinite(bs) & np.isfinite(ob)

    key = cy * 10 ** 7 + cx
    flat = key[usable]
    uniq, inv = np.unique(flat, return_inverse=True)
    n = np.bincount(inv)

    roof_n = np.bincount(inv, weights=d["roof"][usable])
    hard_n = np.bincount(inv, weights=d["hard"][usable])
    val_n = np.bincount(inv, weights=d["valid"][usable])
    ob_s = np.bincount(inv, weights=ob[usable])
    bs_s = np.bincount(inv, weights=bs[usable])
    bs_mx = np.zeros_like(bs_s)
    np.maximum.at(bs_mx, inv, bs[usable])
    bs_mn = np.full_like(bs_s, np.inf)
    np.minimum.at(bs_mn, inv, bs[usable])

    keep = n >= MIN_10M_CELLS_PER_GHS
    spread = float(np.nanmax((bs_mx - bs_mn)[keep])) if keep.any() else 0.0

    ux = (uniq % 10 ** 7).astype(int)
    uy = (uniq // 10 ** 7).astype(int)
    return dict(
        cx=ux[keep], cy=uy[keep], n10=n[keep],
        vhr_roof=roof_n[keep] / val_n[keep],
        vhr_imperv=(roof_n[keep] + hard_n[keep]) / val_n[keep],
        ob=ob_s[keep] / n[keep],
        ghs=(bs_s[keep] / n[keep]) / GHS_CELL_AREA_M2,
        ghs_spread=spread)


def report_pair(name, truth, pred, strata, out, thresholds=BUILTUP_THRESHOLDS):
    m = metrics(truth, pred)
    show("all cells", m)
    rec = {"all": m, "confusion": [], "strata": {}}
    for t in thresholds:
        c = confusion(truth, pred, t)
        star = "  <- primary" if t == thresholds[0] else ""
        print(f"      thr {t:<4} UA(user's)={c['users_accuracy']:.3f} "
              f"PA(producer's)={c['producers_accuracy']:.3f} "
              f"overall={c['overall']:.3f}  "
              f"[TP {c['tp']} FP {c['fp']} FN {c['fn']} TN {c['tn']}]{star}")
        rec["confusion"].append(c)
    for sname, sm in strata.items():
        if sm.sum() >= 20:
            s = metrics(truth[sm], pred[sm])
            show(f"  {sname}", s)
            rec["strata"][sname] = s
        else:
            print(f"    {'  ' + sname:<26} n={int(sm.sum())} -- too few")
    out[name] = rec
    return m


def main():
    print("=" * 78)
    print("GHS-BUILT-S AUDITED AGAINST THE PHASE 0 VHR LABELS")
    print("=" * 78)
    print(f"GHS cell {GHS_CELL_M} m Mollweide (VERIFIED LIVE) -> fraction = "
          f"built_surface / {GHS_CELL_AREA_M2:.0f}")
    print(f"Usable-for-flood judgement (NOT a pre-registered bar): "
          f"MAE<={USABLE_MAE}, |bias|<={USABLE_BIAS}, rho>={USABLE_SPEARMAN}")
    results = {}

    for key in ("kibera", "oldfadama"):
        d = load_site(key)
        site = d["site"]
        print("\n" + "=" * 78)
        print(f"{site['label']}   VHR {site['sensor']}  acquired {site['acquired']}")
        print("=" * 78)

        ob_img = ob_coverage(d["aoi"], d["crs"], d["tr"])
        ob = fetch_on_s2_grid(ob_img, d["crs"], d["tr"], d["r_lo"], d["c_lo"],
                              d["nR"], d["nC"], ["ob_cover"],
                              f"{key} open buildings")["ob_cover"]

        for year in EPOCHS[key]:
            gh = fetch_on_s2_grid(ghs_bands(year), d["crs"], d["tr"],
                                  d["r_lo"], d["c_lo"], d["nR"], d["nC"],
                                  ["built_surface", "built_surface_nres"],
                                  f"{key} GHS {year}")
            cx, cy = ghs_cell_indices(d["crs"], d["tr"], d["r_lo"], d["c_lo"],
                                      d["nR"], d["nC"])
            a = aggregate_to_ghs(d, gh, ob, cx, cy)

            acq = int(site["acquired"][:4]) + int(site["acquired"][5:7]) / 12
            gap = abs(year - acq)
            proj = "  [PROJECTED epoch, not observed]" if year in PROJECTED_EPOCHS else ""
            print(f"\n--- GHS epoch {year}{proj} | temporal gap "
                  f"{gap:.1f} yr from {site['acquired']} ---")
            print(f"  GHS cells with >={MIN_10M_CELLS_PER_GHS} usable 10 m "
                  f"cells: {len(a['cx'])}")
            print(f"  self-check, within-GHS-cell spread of built_surface: "
                  f"{a['ghs_spread']:.6f} m^2 (0 => cell assignment exact)")
            if len(a["cx"]) < 20:
                print("  too few cells -- skipping")
                continue

            bstats = building_stats_per_ghs(
                d["aoi"], cx, cy,
                d["crs"], d["tr"], d["r_lo"], d["c_lo"])
            med = np.array([bstats.get((x, y), (np.nan, 0))[0]
                            for x, y in zip(a["cx"], a["cy"])])
            cnt = np.array([bstats.get((x, y), (np.nan, 0))[1]
                            for x, y in zip(a["cx"], a["cy"])])
            enough = cnt >= MIN_BUILDINGS_FOR_STRATUM
            informal = enough & (med < INFORMAL_MEDIAN_FOOTPRINT_MAX_M2)
            formal = enough & (med >= INFORMAL_MEDIAN_FOOTPRINT_MAX_M2)
            print(f"  fabric split (median OB footprint, cut "
                  f"{INFORMAL_MEDIAN_FOOTPRINT_MAX_M2:.0f} m2): "
                  f"informal {int(informal.sum())}, formal {int(formal.sum())}, "
                  f"unclassified {int((~enough).sum())}")
            if enough.any():
                print(f"    median footprint over classified cells: "
                      f"informal {np.nanmedian(med[informal]) if informal.any() else float('nan'):.1f} m2, "
                      f"formal {np.nanmedian(med[formal]) if formal.any() else float('nan'):.1f} m2")

            for q, arr in (("VHR roof", a["vhr_roof"]),
                           ("VHR impervious", a["vhr_imperv"]),
                           ("GHS fraction", a["ghs"]),
                           ("OB coverage", a["ob"])):
                p = np.percentile(arr, [5, 25, 50, 75, 95])
                print(f"  {q:<16} mean={arr.mean():.3f} sd={arr.std():.3f} "
                      f"p5/25/50/75/95 = " +
                      " ".join(f"{v:.3f}" for v in p))

            strata = {"informal fabric": informal, "formal fabric": formal}
            rec = {}
            print("\n  (a) GHS vs VHR ROOF-ONLY  -- 'is GHS accurate at what "
                  "it measures'")
            report_pair("a_ghs_vs_roof", a["vhr_roof"], a["ghs"], strata, rec)
            print("\n  (b) GHS vs VHR IMPERVIOUS -- 'is GHS usable as a "
                  "substitute'.")
            print("      GHS does not claim unroofed hard surface; a shortfall "
                  "here is EXPECTED,")
            print("      not GHS being wrong.")
            report_pair("b_ghs_vs_imperv", a["vhr_imperv"], a["ghs"], strata, rec)
            print("\n  (c) OPEN BUILDINGS vs VHR ROOF-ONLY -- tests the item 21 "
                  "re-scope's")
            print("      assumption that footprint-derived `built` is reliable.")
            report_pair("c_ob_vs_roof", a["vhr_roof"], a["ob"], strata, rec)

            m = rec["a_ghs_vs_roof"]["all"]
            verdict = (m["mae"] <= USABLE_MAE and abs(m["bias"]) <= USABLE_BIAS
                       and m["spearman"] >= USABLE_SPEARMAN)
            print(f"\n  against the stated usability judgement (comparison a): "
                  f"{'MEETS' if verdict else 'DOES NOT MEET'} "
                  f"(MAE {m['mae']:.3f}/{USABLE_MAE}, "
                  f"bias {m['bias']:+.3f}/±{USABLE_BIAS}, "
                  f"rho {m['spearman']:.3f}/{USABLE_SPEARMAN})")
            results[f"{key}_{year}"] = rec

    sc = vhr_sites.site("kibera")["scratch"]
    with open(os.path.join(sc, "ghsl_audit.json"), "w") as fh:
        json.dump(results, fh, indent=2, default=float)
    print(f"\nwrote {os.path.join(sc, 'ghsl_audit.json')}")


if __name__ == "__main__":
    main()
