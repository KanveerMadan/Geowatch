"""
Pure-pixel diagnostic for the `paved` endmember, mirroring diagnose_pure_pixels.py.

`diagnose_pure_pixels.py` measured whether `built` can supply pure 10m
endmember pixels from Open Buildings footprints. This asks the same question
of `paved`, which has a completely different source: per 02_ARCHITECTURE.md
(~L301) and 05_BUILD_MANUAL.md (~L215), `paved` must NOT come from OSM road
centerlines -- a centerline pixel at 10m is ~45% road / 55% roof, which is C29
-- and must instead come from wide, unambiguously unroofed OSM *polygons*.

Source note, stated plainly
---------------------------
This project has no existing paved/impervious polygon generator to reuse.
`generate_osm_road_masks.py` queries `way["highway"]` CENTERLINES and buffers
them by tag-based width; `generate_osm_water_masks.py` queries `waterway` and
`natural=water`. Neither is the unroofed-polygon source Decision 13 specifies.
So this script queries Overpass directly, for the polygon tags the docs name
plus close siblings:

    amenity=parking          parking lots
    aeroway=apron            airport aprons
    highway=pedestrian +area=yes   plazas mapped as areas
    highway=service   +area=yes    service yards / hardstanding
    place=square             civic squares
    amenity=bus_station      bus aprons
    landuse=garages          garage courts

Deliberately EXCLUDED, though 02_ARCHITECTURE.md says "landuse": bare
`landuse=industrial` / `landuse=retail` / `landuse=commercial`. Those polygons
enclose buildings and roofs, so they are not "unambiguously unroofed" -- using
them would measure roof purity and label it paved, laundering exactly the
contamination Decision 13 is trying to escape. That exclusion is a judgement
call and is called out in the results.

Known limitation: only OSM *ways* are queried, not multipolygon *relations*.
Large parking areas mapped as relations are therefore missed, so the paved
area found here is a lower bound.

Grid and purity logic are imported verbatim from diagnose_pure_pixels.py --
same real Sentinel-2 CRS/crsTransform, same sub-cell coverage-fraction test,
same "fully covered" definition. No buffer, no area bar.

Usage:
    python diagnose_pure_pixels_paved.py
"""

import argparse
import json
import os
import time


import diagnose_open_buildings_aoi as diag
import diagnose_pure_pixels as pure_diag
import ee

# Endpoints, per-status-code error handling and backoff come from the shared
# client (C44). This used to import OVERPASS_URLS from generate_osm_road_masks
# and reimplement the retry loop -- which is how the impervious endmember
# extraction inherited a list in which two of three endpoints were dead.
from ingestion.overpass import (
    run_query, OverpassQueryError, OverpassQueryTooHeavy, OverpassError,
)

CACHE_DIR = os.path.join("cache", "paved_polygons")

PAVED_TAG_QUERIES = [
    'way["amenity"="parking"]',
    'way["aeroway"="apron"]',
    'way["highway"="pedestrian"]["area"="yes"]',
    'way["highway"="service"]["area"="yes"]',
    'way["place"="square"]',
    'way["amenity"="bus_station"]',
    'way["landuse"="garages"]',
]

# Below this, reporting a pure-pixel percentage is meaningless -- say so
# instead of dividing by a rounding error.
MIN_MEANINGFUL_PAVED_M2 = 10_000  # 1 hectare, i.e. 100 pixel-equivalents


def _tag_slug(tag_query):
    return "".join(c if c.isalnum() else "_" for c in tag_query).strip("_")


def _overpass_one(tag_query, bbox, retries=5):
    """One tag clause, one request.

    A single union of all seven clauses reliably 504s on overpass-api.de --
    clauses like highway=service scan a large way set before the area=yes
    filter applies. Split per tag, each finishes in about a second.
    """
    query = f"""
    [out:json][timeout:60];
    {tag_query}{bbox};
    out geom;
    """
    headers = {
        "User-Agent": "GeoWatchCopilot/1.0 (research project, contact: local dev)",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        return run_query(query)
    except (OverpassQueryError, OverpassQueryTooHeavy) as e:
        # The query is at fault, not the network. Retrying or rotating would
        # reissue the same broken query and report the same failure later --
        # and for the endmember extraction, a malformed tag clause silently
        # yielding "no paved polygons here" is exactly the failure that must
        # never be mistaken for a real zero.
        print(f"    {tag_query}: QUERY REJECTED -- {e}")
        raise
    except OverpassError as e:
        # Every endpoint exhausted. Report unavailable rather than zero: one
        # flaky tag must not discard the other six, and "not retrieved" and
        # "none exist" are different claims of which only one is honest.
        print(f"    {tag_query}: UNAVAILABLE -- {e}")
        return None


def overpass_paved(min_lon, min_lat, max_lon, max_lat, cache_key):
    """Closed OSM ways carrying unroofed hard-surface tags. Cached to disk so
    reruns don't re-hit Overpass."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_path):
        with open(cache_path) as fh:
            elements = json.load(fh)
        print(f"  (cached) {len(elements)} paved ways")
        return elements, []

    bbox = f"({min_lat},{min_lon},{max_lat},{max_lon})"
    seen = {}
    unavailable = []
    for i, tag_query in enumerate(PAVED_TAG_QUERIES):
        # Per-tag cache: a throttled run resumes instead of restarting.
        tag_cache = os.path.join(CACHE_DIR, f"{cache_key}__{_tag_slug(tag_query)}.json")
        if os.path.exists(tag_cache):
            with open(tag_cache) as fh:
                els = json.load(fh)
            print(f"    {tag_query}: {len(els)} ways (cached)", flush=True)
        else:
            if i:
                time.sleep(3)  # be polite to a shared public endpoint
            els = _overpass_one(tag_query, bbox)
            if els is None:
                unavailable.append(tag_query)
                continue  # not cached -- a later run can still retrieve it
            with open(tag_cache, "w") as fh:
                json.dump(els, fh)
            print(f"    {tag_query}: {len(els)} ways", flush=True)

        for el in els:
            seen[el.get("id")] = el  # dedupe across overlapping tag clauses

    elements = list(seen.values())
    if unavailable:
        print(f"  WARNING: {len(unavailable)} tag(s) not retrieved: "
              f"{unavailable} -- counts below are a lower bound")
    else:
        with open(cache_path, "w") as fh:
            json.dump(elements, fh)
    print(f"  {len(elements)} paved ways total (deduped)")
    return elements, unavailable


def to_feature_collection(elements):
    """Closed ways -> ee.FeatureCollection of polygons, tagged with the OSM
    tag that matched, so the per-polygon pass can report composition."""
    feats = []
    for el in elements:
        geom = el.get("geometry")
        if not geom or len(geom) < 4:
            continue
        ring = [[pt["lon"], pt["lat"]] for pt in geom]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        if len(ring) < 4:
            continue

        tags = el.get("tags", {})
        if tags.get("amenity") == "parking":
            kind = "parking"
        elif tags.get("aeroway") == "apron":
            kind = "apron"
        elif tags.get("highway") == "pedestrian":
            kind = "plaza"
        elif tags.get("highway") == "service":
            kind = "service_area"
        elif tags.get("place") == "square":
            kind = "square"
        elif tags.get("amenity") == "bus_station":
            kind = "bus_station"
        else:
            kind = "other"

        try:
            poly = ee.Geometry.Polygon([ring], proj="EPSG:4326", geodesic=False)
        except Exception:
            continue
        feats.append(ee.Feature(poly, {"osm_id": el.get("id", 0), "kind": kind}))

    return ee.FeatureCollection(feats), len(feats)


def measure_paved(label, aoi, cache_key):
    print(f"\n{'=' * 78}")
    print(f"[{label}] -- paved")
    print(f"{'=' * 78}")

    area_km2 = aoi.area(1).getInfo() / 1e6
    proj, proj_info = pure_diag.s2_grid_for(aoi)
    print(f"  S2 grid: CRS={proj_info.get('crs')} "
          f"transform={proj_info.get('transform')}")
    print(f"  AOI area: {area_km2:.2f} km^2")

    bounds = aoi.bounds().coordinates().getInfo()[0]
    lons = [c[0] for c in bounds]
    lats = [c[1] for c in bounds]
    elements, unavailable = overpass_paved(min(lons), min(lats),
                                           max(lons), max(lats), cache_key)

    fc, n_polys = to_feature_collection(elements)
    if n_polys == 0:
        print("  1. paved polygon area: 0 m^2 -- NO paved polygons at all")
        print("     Nothing to measure. Pure-pixel percentage is undefined,")
        print("     not zero-with-a-denominator.")
        return {"label": label, "area_km2": area_km2, "n_polys": 0,
                "paved_m2": 0.0, "overlap_px": 0, "pure_px": 0,
                "pure_pct": None, "contributors": 0, "bias_sel_px": None,
                "unavailable": unavailable, "meaningful": False}

    # Dissolve so overlapping/duplicate mappings aren't double counted
    paved_m2 = fc.geometry().dissolve(1).area(1).getInfo()
    pct_of_aoi = 100.0 * paved_m2 / (area_km2 * 1e6)
    print(f"  1. paved polygons: {n_polys} | dissolved area "
          f"{paved_m2:,.0f} m^2 ({pct_of_aoi:.2f}% of AOI)")

    kinds = fc.aggregate_histogram("kind").getInfo()
    print(f"     composition by tag: {kinds}")

    if paved_m2 < MIN_MEANINGFUL_PAVED_M2:
        print(f"     *** below {MIN_MEANINGFUL_PAVED_M2:,} m^2 -- too little "
              f"paved polygon area for a pure-pixel percentage to mean "
              f"anything. Reporting counts, flagging the ratio as unreliable.")

    overlap_px, pure_px, pure = pure_diag.count_overlap_and_pure(
        fc, aoi, proj, proj_info
    )
    pure_pct = (100.0 * pure_px / overlap_px) if overlap_px else None

    print(f"  2. pixels overlapping any paved polygon : {overlap_px}")
    print(f"  3. PURE pixels (fully covered)          : {pure_px}")
    if pure_pct is None:
        print(f"     pure as % of overlap                 : undefined "
              f"(no overlap pixels)")
    else:
        print(f"     pure as % of overlap                 : {pure_pct:.2f}%")
    print(f"     pure pixels per km^2                 : {pure_px/area_km2:.1f}")

    # --- metric 4 --------------------------------------------------------
    # Per-polygon area, and which polygons yield >=1 pure pixel. Whether this
    # constitutes "bias" in the same sense as buildings is discussed in the
    # write-up, not asserted here -- the numbers are reported either way.
    with_area = fc.map(lambda f: f.set({"poly_area_m2": f.geometry().area(1)}))
    pop_mean_area = with_area.aggregate_mean("poly_area_m2").getInfo()

    contributors = None
    contrib_mean = None
    bias_sel_px = None
    if pure_px > 0:
        scored = pure.rename("pure").reduceRegions(
            collection=with_area,
            reducer=ee.Reducer.sum(),
            crs=proj_info["crs"],
            crsTransform=proj_info["transform"],
        )
        contrib_fc = scored.filter(ee.Filter.gte("sum", 1))
        stats = ee.Dictionary({
            "n": contrib_fc.size(),
            "mean_area": contrib_fc.aggregate_mean("poly_area_m2"),
        }).getInfo()
        contributors = stats["n"]
        if contributors:
            contrib_mean = stats["mean_area"]
            bias_sel_px = contrib_mean / pop_mean_area

    print(f"  4. mean paved polygon area (all)        : {pop_mean_area:,.0f} m^2")
    if bias_sel_px is None:
        print(f"     no pure pixels -- size ratio undefined")
    else:
        print(f"     polygons contributing >=1 pure pixel : {contributors} "
              f"/ {n_polys} ({100.0*contributors/n_polys:.1f}%)")
        print(f"     their mean area                      : {contrib_mean:,.0f} m^2")
        print(f"     size ratio (paved analog of bias_sel): {bias_sel_px:.2f}x")

    return {"label": label, "area_km2": area_km2, "n_polys": n_polys,
            "paved_m2": paved_m2, "pct_of_aoi": pct_of_aoi,
            "overlap_px": overlap_px, "pure_px": pure_px, "pure_pct": pure_pct,
            "contributors": contributors, "bias_sel_px": bias_sel_px,
            "unavailable": unavailable,
            "meaningful": paved_m2 >= MIN_MEANINGFUL_PAVED_M2}


def print_summary(rows):
    print("\n" + "=" * 108)
    print("PURE-PIXEL DIAGNOSTIC -- `paved` from unroofed OSM polygons, "
          "real S2 10m grid, no buffer, no area bar")
    print("=" * 108)
    print(f"{'AOI':<28} {'polys':>6} {'paved m2':>12} {'%AOI':>6} "
          f"{'overlap':>8} {'pure':>7} {'pure %':>8} {'contribs':>9} {'ratio':>7}")
    print("-" * 108)
    for r in rows:
        pure_pct = f"{r['pure_pct']:.2f}%" if r["pure_pct"] is not None else "n/a"
        ratio = f"{r['bias_sel_px']:.2f}x" if r["bias_sel_px"] else "n/a"
        contribs = r["contributors"] if r["contributors"] is not None else 0
        flag = "" if r["meaningful"] else "  <- too little paved area"
        print(f"{r['label']:<28} {r['n_polys']:>6} {r['paved_m2']:>12,.0f} "
              f"{r.get('pct_of_aoi', 0):>5.2f}% {r['overlap_px']:>8} "
              f"{r['pure_px']:>7} {pure_pct:>8} {contribs:>9} {ratio:>7}{flag}")
    print("=" * 108)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", choices=["dharavi", "khayelitsha", "formal"])
    args = parser.parse_args()

    cache_keys = {
        "Dharavi": "dharavi",
        "Khayelitsha (capetown run)": "khayelitsha",
        "Cape Town formal suburbs": "ct_formal",
    }

    rows = []
    for label, aoi in pure_diag.build_aois(args.aoi):
        rows.append(measure_paved(label, aoi, cache_keys[label]))

    if len(rows) > 1:
        print_summary(rows)


if __name__ == "__main__":
    main()
