"""
Direct measurement of PURE `built` endmember pixels on the real Sentinel-2 grid.

`diagnose_open_buildings_aoi.py` and `sweep_open_buildings_params.py` both
measured a proxy: polygon area surviving an inward buffer. Polygon area is not
pixel purity -- a 10.1 x 10.1 m building interior straddling a pixel boundary
clears any area bar you like while contributing zero pure pixels. This script
drops the buffer/area-bar machinery entirely and measures the thing itself:

  how many 10m Sentinel-2 pixels are FULLY covered by building footprint?

Grid alignment
--------------
The grid is taken from an actual COPERNICUS/S2_SR_HARMONIZED image over each
AOI -- its native UTM CRS and 10m crsTransform -- NOT a 10m grid constructed
from the AOI bounds. Pixel-boundary alignment is the entire question here, so
the grid has to be the one the real composite would use.

Method
------
1. Paint the confidence>=0.7 footprints into a mask.
2. Reproject that mask to a SUB-PIXEL grid derived from the S2 projection via
   `.atScale(SUBPIXEL_M)` -- same CRS, same origin, so sub-cells tile the 10m
   cells exactly.
3. `reduceResolution(mean)` back to the S2 10m grid -> per-pixel covered
   fraction.
4. overlap = fraction > 0 ; pure = fraction >= PURE_FRACTION_MIN (~1.0).

Three honesty notes on the approximation, all pointing the same direction:

  a) Purity is tested at sub-cell centers, so a pixel that is 99.6% covered
     can register as pure. This can only OVER-count pure pixels, never
     under-count them.
  b) Coverage is measured against the UNION of footprints, so a pixel spanning
     two shared-wall structures counts as pure. For a *built* endmember that
     is arguably correct -- such a pixel is spectrally pure built -- and it is
     also the more generous reading.
  c) `overlap` is measured on the same sub-cell basis, so a pixel clipping a
     footprint by less than one sub-cell is missed, which slightly SHRINKS the
     denominator of metric 3 and inflates the reported usable percentage.

All three biases inflate the result. A near-zero pure-pixel count is therefore
robust: it cannot be an artifact of the approximation.

Metric 4 (pixel-level bias_sel)
-------------------------------
Only buildings with area_in_meters >= 100 can possibly contain a full 100 m^2
pixel, so the per-building pass runs over that subset -- exact, not a
shortcut, and it keeps reduceRegions off the ~93k full set. A building
"contributes" if at least one pure pixel centre falls within it.

Reuses AOI resolution and constants from diagnose_open_buildings_aoi.py
(importing it also performs GEE initialization).

Usage:
    python diagnose_pure_pixels.py
    python diagnose_pure_pixels.py --aoi dharavi
"""

import argparse

import diagnose_open_buildings_aoi as diag
import ee

S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# Sub-cell size for the coverage-fraction test. 1m -> 100 sub-cells per 10m
# pixel. Smaller is more exact but costs quadratically; 1m is enough to make
# the over-count in note (a) small.
SUBPIXEL_M = 1

# A 10m pixel counts as pure at this covered fraction. Not exactly 1.0 to
# absorb floating-point noise in the mean reducer.
PURE_FRACTION_MIN = 0.999

# A polygon smaller than one 10m pixel cannot contain one.
MIN_AREA_FOR_PURE_M2 = 100

FORMAL_CT_BBOX = [18.455, -33.985, 18.495, -33.950]


def build_aois(which=None):
    aois = []

    if which in (None, "dharavi"):
        aois.append(("Dharavi", ee.Geometry.Rectangle(diag.DHARAVI_BOUNDS)))

    if which in (None, "khayelitsha", "capetown"):
        ct_bounds, ct_run_dir = diag.aoi_bounds_from_run("capetown")
        print(f"  capetown AOI from {ct_run_dir}")
        aois.append((
            "Khayelitsha (capetown run)",
            ee.Geometry.Rectangle(list(ct_bounds)),
        ))

    if which in (None, "formal"):
        aois.append(("Cape Town formal suburbs",
                     ee.Geometry.Rectangle(FORMAL_CT_BBOX)))

    return aois


def s2_grid_for(aoi):
    """The real Sentinel-2 10m grid over this AOI.

    Taken from an actual S2_SR_HARMONIZED scene's B2 band, so the CRS and
    crsTransform are the ones the real composite is built on -- not a 10m
    grid synthesized from the AOI bounds.
    """
    scene = (ee.ImageCollection(S2_COLLECTION)
             .filterBounds(aoi)
             .first())
    proj = ee.Image(scene).select("B2").projection()
    info = proj.getInfo()
    return proj, info


def pure_pixel_images(fc, proj):
    """(overlap, pure) masks on `proj`'s grid for an arbitrary polygon
    FeatureCollection.

    Coverage fraction is measured by painting the polygons at a sub-pixel
    scale derived from `proj` itself (`.atScale`), so sub-cells tile the 10m
    cells exactly, then averaging back down onto the 10m grid.

    Kept source-agnostic: `built` passes building footprints, `paved` passes
    unroofed OSM polygons, and both are measured identically.
    """
    fine_proj = proj.atScale(SUBPIXEL_M)
    mask = ee.Image(0).byte().paint(fc, 1).reproject(fine_proj)

    subcells = int((10 / SUBPIXEL_M) ** 2)
    covered_fraction = (mask
                        .reduceResolution(ee.Reducer.mean(),
                                          maxPixels=subcells + 16)
                        .reproject(proj))

    return (covered_fraction.gt(0).rename("overlap"),
            covered_fraction.gte(PURE_FRACTION_MIN).rename("pure"),
            subcells)


def count_overlap_and_pure(fc, aoi, proj, proj_info):
    """(overlap_px, pure_px, pure_image) over `aoi` on the real S2 grid."""
    overlap, pure, subcells = pure_pixel_images(fc, proj)

    print(f"  counting pixels ({subcells} sub-cells per 10m pixel)...",
          flush=True)
    counts = ee.Image.cat(overlap, pure).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        crs=proj_info["crs"],
        crsTransform=proj_info["transform"],
        maxPixels=1e10,
    ).getInfo()

    return int(counts["overlap"]), int(counts["pure"]), pure


def measure_aoi(label, aoi):
    print(f"\n{'=' * 78}")
    print(f"[{label}]")
    print(f"{'=' * 78}")

    area_km2 = aoi.area(1).getInfo() / 1e6

    proj, proj_info = s2_grid_for(aoi)
    print(f"  S2 grid: CRS={proj_info.get('crs')} "
          f"transform={proj_info.get('transform')}")
    print(f"  AOI area: {area_km2:.2f} km^2")

    buildings = ee.FeatureCollection(diag.BUILDINGS_ASSET).filterBounds(aoi)
    confident = buildings.filter(
        ee.Filter.gte("confidence", diag.CONFIDENCE_THRESHOLD)
    )

    baseline = ee.Dictionary({
        "raw": buildings.size(),
        "confident": confident.size(),
        "pop_mean_area": confident.aggregate_mean("area_in_meters"),
    }).getInfo()
    print(f"  raw {baseline['raw']} | confident {baseline['confident']} | "
          f"pop mean area {baseline['pop_mean_area']:.1f} m^2")

    overlap_px, pure_px, pure = count_overlap_and_pure(
        confident, aoi, proj, proj_info
    )
    pure_pct = (100.0 * pure_px / overlap_px) if overlap_px else 0.0

    print(f"  1. pixels overlapping any footprint : {overlap_px}")
    print(f"  2. PURE pixels (fully covered)      : {pure_px}")
    print(f"  3. pure as % of overlap             : {pure_pct:.2f}%")
    print(f"     pure pixels per km^2             : {pure_px / area_km2:.1f}")

    # --- metric 4: pixel-level bias_sel -----------------------------------
    # Only buildings >= one pixel of area can contain a full pixel.
    candidates = confident.filter(
        ee.Filter.gte("area_in_meters", MIN_AREA_FOR_PURE_M2)
    )
    cand_count = candidates.size().getInfo()
    print(f"  4. per-building pass over {cand_count} candidates "
          f"(area >= {MIN_AREA_FOR_PURE_M2} m^2)...", flush=True)

    if pure_px == 0 or cand_count == 0:
        print("     no pure pixels -- bias_sel undefined")
        return {
            "label": label, "area_km2": area_km2,
            "raw": baseline["raw"], "confident": baseline["confident"],
            "pop_mean_area": baseline["pop_mean_area"],
            "overlap_px": overlap_px, "pure_px": pure_px,
            "pure_pct": pure_pct,
            "contributors": 0, "contrib_mean_area": None, "bias_sel_px": None,
        }

    scored = pure.rename("pure").reduceRegions(
        collection=candidates,
        reducer=ee.Reducer.sum(),
        crs=proj_info["crs"],
        crsTransform=proj_info["transform"],
    )
    contributors = scored.filter(ee.Filter.gte("sum", 1))

    contrib = ee.Dictionary({
        "n": contributors.size(),
        "mean_area": contributors.aggregate_mean("area_in_meters"),
    }).getInfo()

    n_contrib = contrib["n"]
    if not n_contrib:
        print("     no contributing buildings -- bias_sel undefined")
        bias_sel_px = None
        contrib_mean = None
    else:
        contrib_mean = contrib["mean_area"]
        bias_sel_px = contrib_mean / baseline["pop_mean_area"]
        print(f"     buildings contributing >=1 pure pixel : {n_contrib} "
              f"({100.0*n_contrib/baseline['confident']:.2f}% of confident set)")
        print(f"     their mean original area              : {contrib_mean:.1f} m^2")
        print(f"     population mean original area         : "
              f"{baseline['pop_mean_area']:.1f} m^2")
        print(f"     bias_sel (pixel-level)                : {bias_sel_px:.2f}x")

    return {
        "label": label, "area_km2": area_km2,
        "raw": baseline["raw"], "confident": baseline["confident"],
        "pop_mean_area": baseline["pop_mean_area"],
        "overlap_px": overlap_px, "pure_px": pure_px, "pure_pct": pure_pct,
        "contributors": n_contrib, "contrib_mean_area": contrib_mean,
        "bias_sel_px": bias_sel_px,
    }


def print_summary(rows):
    print("\n" + "=" * 100)
    print("PURE-PIXEL DIAGNOSTIC -- Sentinel-2 10m grid, confidence >= 0.7, "
          "no buffer, no area bar")
    print("=" * 100)
    print(f"{'AOI':<28} {'overlap px':>11} {'pure px':>9} {'pure %':>8} "
          f"{'pure/km2':>9} {'contribs':>9} {'bias_sel':>9}")
    print("-" * 100)
    for r in rows:
        bias = f"{r['bias_sel_px']:.2f}x" if r["bias_sel_px"] else "n/a"
        print(f"{r['label']:<28} {r['overlap_px']:>11} {r['pure_px']:>9} "
              f"{r['pure_pct']:>7.2f}% {r['pure_px']/r['area_km2']:>9.1f} "
              f"{r['contributors']:>9} {bias:>9}")
    print("=" * 100)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", choices=["dharavi", "khayelitsha", "formal"],
                        help="run a single AOI (default: all three)")
    args = parser.parse_args()

    rows = [measure_aoi(label, aoi) for label, aoi in build_aois(args.aoi)]
    if len(rows) > 1:
        print_summary(rows)


if __name__ == "__main__":
    main()
