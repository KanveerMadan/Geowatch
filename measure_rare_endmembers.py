"""
Measure real Sentinel-2 endmember spectra for the three rare fractions.

Feeds ceiling_rare_fractions.py. The ceiling there is only as good as these
spectra, so every site is chosen from an independent MAPPED reference, never
from a spectral threshold of our own: selecting pixels by, say, NDSI > 0.4
would hand the ceiling an endmember that is separable by construction.

Fractions and the references that locate them (all verified live, see --verify):

  solar                  OSM `power=plant` + `plant:source=solar` outlines
                         (utility), OSM `generator:source=solar` +
                         `location=roof` polygons (rooftop)
  snow_ice               GLIMS glacier outlines  AND  ESA WorldCover v200
                         class 70 (snow and ice)
  mixed_water_vegetation Global Mangrove Watch v3 2020 AND GLWD v2 class 28 AND
                         WorldCover 95 (mangrove); GLWD v2 non-forested
                         flooded/saturated wetland classes AND WorldCover 90
                         (marsh); Murray global intertidal, tidal flat (mud)

Purity. A pixel is used only if it lies wholly inside the reference:
vector references are eroded by ERODE_M (10 m >= the 7.07 m half-diagonal of a
10 m pixel) and tested at the pixel centre; raster references are eroded by one
pixel. This is the same "pure pixel" idea as diagnose_pure_pixels.py, done by
erosion rather than 1 m sub-pixel coverage because a solar park is tens of km^2.

Composite. Same as ingestion/sentinel2.get_sentinel2_median_composite:
COPERNICUS/S2_SR_HARMONIZED, CLOUDY_PIXEL_PERCENTAGE < CLOUD_PCT, SCL-masked
by mask_s2_clouds (which keeps SCL 11 snow), median. Built here rather than
called, because that function makes un-timed getInfo calls (C56).

Known limits, stated before running:
  * A utility-farm pixel is panels PLUS the ground between rows. That is what a
    10 m pixel over a farm sees, but it is not a pure panel spectrum, and it
    pulls the solar endmember toward bare/vegetation.
  * OSM rooftop polygons may trace the roof, not the panels.
  * Tidal-flat composites mix tide states; Murray is 2014-2016.
  * Sen2Cor can flag bright snow as cloud. n_pixels and n_images are recorded
    so an under-observed snow endmember is visible.
  * Water hyacinth (a Decision 11 sub-type) is NOT measured: no independent
    map of it was found. Logged, not substituted.

Every EE request goes through ee_timeout.call with an explicit timeout, and
ee.data.setDeadline is set as a second guard (C56).

Usage:
    python measure_rare_endmembers.py --verify   # masks only, no spectra
    python measure_rare_endmembers.py            # writes ENDMEMBERS_PATH
"""

import argparse
import datetime as dt
import json
import os
import sys

import ee
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import linemerge, polygonize, unary_union

from ee_timeout import call
from ingestion.overpass import run_query
from ingestion.sentinel2 import S2_BAND_NAMES, mask_s2_clouds

# --- fixed before any spectrum was read ----------------------------------
CLOUD_PCT = 20                 # pipeline default
CLOUD_PCT_FALLBACK = 50        # used only if < MIN_IMAGES at CLOUD_PCT
MIN_IMAGES = 5
MIN_PIXELS = 30                # same floor as test_endmember_sensitivity.py
ERODE_M = 10
SURROUND_INNER_M = 30          # local-surround ring, diagnostic only
SURROUND_OUTER_M = 300
SCALE_M = 10
EE_TIMEOUT_S = 300
EE_DEADLINE_MS = 280_000
OVERPASS_TIMEOUT_S = 180

WC = "ESA/WorldCover/v200"
GLIMS = "GLIMS/current"
GMW = "projects/sat-io/open-datasets/GMW/extent/gmw_v3_2020_vec"
GLWD = "projects/sat-io/open-datasets/GLWD/GLWD_V2_DELTA_MAIN_CLASS"
MURRAY = "UQ/murray/Intertidal/v1_1/global_intertidal"

WC_SNOW, WC_WETLAND, WC_MANGROVE = 70, 90, 95
GLWD_MANGROVE = 28
# GLWD v2 non-forested wetlands that flood or saturate: lacustrine (9),
# riverine regularly/seasonally flooded or saturated (11, 13, 15), palustrine
# regularly flooded / seasonally saturated (17, 19), ephemeral (21), and
# non-forested peatland (23, 25, 27).
# DEVIATION, recorded: the list first omitted 23/25/27, and --verify found 0
# pure pixels at the Everglades because GLWD v2 maps that sawgrass marsh as
# 27 (tropical peatland, non-forested) while WorldCover calls 98% of the box
# herbaceous wetland (90). Added from class histograms only, before any
# spectrum was read.
GLWD_MARSH = [9, 11, 13, 15, 17, 19, 21, 23, 25, 27]
MURRAY_TIDAL_FLAT = 1

ENDMEMBERS_PATH = "experiments/rare_fraction_ceilings/endmembers.json"


def box(lat, lon, half):
    return [lon - half, lat - half, lon + half, lat + half]


# Each site: fraction, subtype, reference, AOI (w, s, e, n) and window.
SITES = [
    dict(name="bhadla", fraction="solar", subtype="utility",
         ref=("osm_element", "relation", 11250846),
         aoi=[71.89, 27.44, 72.05, 27.55], window=("2025-01-01", "2025-03-31")),
    dict(name="benban", fraction="solar", subtype="utility",
         ref=("osm_element", "way", 694477324),
         aoi=[32.68, 24.39, 32.76, 24.46], window=("2025-01-01", "2025-03-31")),
    dict(name="witznitz", fraction="solar", subtype="utility",
         ref=("osm_element", "relation", 15093634),
         aoi=[12.39, 51.14, 12.45, 51.19], window=("2025-06-01", "2025-08-31")),
    dict(name="rooftop_venlo", fraction="solar", subtype="rooftop",
         ref=("osm_rooftop", None, None),
         aoi=[6.08, 51.33, 6.25, 51.43], window=("2025-06-01", "2025-08-31")),

    dict(name="aletsch", fraction="snow_ice", subtype="glacier",
         ref=("glims_wc", None, None),
         aoi=box(46.50, 8.03, 0.05), window=("2025-08-01", "2025-09-30")),
    dict(name="quelccaya", fraction="snow_ice", subtype="ice_cap",
         ref=("glims_wc", None, None),
         aoi=box(-13.93, -70.82, 0.04), window=("2025-06-01", "2025-09-30")),

    dict(name="sundarbans", fraction="mixed_water_vegetation",
         subtype="mangrove", ref=("mangrove", None, None),
         aoi=box(21.95, 89.45, 0.05), window=("2025-01-01", "2025-03-31")),
    dict(name="everglades", fraction="mixed_water_vegetation",
         subtype="marsh", ref=("marsh", None, None),
         aoi=box(25.70, -80.75, 0.05), window=("2025-08-01", "2025-10-31")),
    dict(name="sudd", fraction="mixed_water_vegetation",
         subtype="marsh", ref=("marsh", None, None),
         aoi=box(7.60, 30.60, 0.05), window=("2025-10-01", "2025-12-31")),
    dict(name="wadden_neuwerk", fraction="mixed_water_vegetation",
         subtype="tidal_flat", ref=("tidal_flat", None, None),
         aoi=box(53.90, 8.45, 0.05), window=("2025-05-01", "2025-08-31")),
]

NOT_MEASURED = {
    "mixed_water_vegetation/water_hyacinth":
        "no independent map of water hyacinth found; not substituted",
}
# -------------------------------------------------------------------------


def _ee_init():
    ee.Initialize(project=os.environ["GEE_PROJECT_ID"])
    ee.data.setDeadline(EE_DEADLINE_MS)


def _get(obj, label, timeout=EE_TIMEOUT_S):
    return call(lambda: obj.getInfo(), timeout=timeout, label=label)


# ------------------------------------------------------------- OSM geometry

def _way_polygon(geom):
    pts = [(p["lon"], p["lat"]) for p in geom]
    return Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] else None


def osm_polygons(elements):
    """Shapely polygons from Overpass `out geom` ways and multipolygons."""
    polys = []
    for el in elements:
        if el["type"] == "way" and "geometry" in el:
            p = _way_polygon(el["geometry"])
            if p is not None and p.is_valid:
                polys.append(p)
        elif el["type"] == "relation":
            outer = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                     for m in el.get("members", [])
                     if m.get("role") == "outer" and m.get("geometry")]
            inner = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                     for m in el.get("members", [])
                     if m.get("role") == "inner" and m.get("geometry")]
            o = unary_union(list(polygonize(linemerge(outer)))) if outer else None
            if o is None or o.is_empty:
                continue
            if inner:
                o = o.difference(unary_union(list(polygonize(linemerge(inner)))))
            polys.append(o)
    return polys


def _to_ee(polys):
    geoms = []
    for p in polys:
        parts = getattr(p, "geoms", [p])
        geoms.extend(ee.Geometry(mapping(g), geodesic=False) for g in parts)
    return ee.FeatureCollection([ee.Feature(g) for g in geoms])


def osm_reference(site):
    kind, otype, oid = site["ref"]
    w, s, e, n = site["aoi"]
    if kind == "osm_element":
        q = f"[out:json][timeout:120];{otype}({oid});out geom;"
    else:
        q = (f'[out:json][timeout:120];way["generator:source"="solar"]'
             f'["location"="roof"]({s},{w},{n},{e});out geom;')
    els = run_query(q, timeout=OVERPASS_TIMEOUT_S)
    polys = osm_polygons(els)
    record = {"overpass_elements": len(els), "polygons": len(polys)}
    if kind == "osm_element" and els:
        t = els[0].get("tags", {})
        record.update(osm=f"{otype}/{oid}", name=t.get("name"),
                      output=t.get("plant:output:electricity"),
                      plant_source=t.get("plant:source"))
    return _to_ee(polys), record


# ------------------------------------------------------------- masks

def _erode_fc(fc):
    return fc.map(lambda f: f.buffer(-ERODE_M, 1))


def _paint(fc):
    return ee.Image(0).byte().paint(fc, 1).selfMask()


def _erode_raster(mask):
    m = mask.unmask(0).focalMin(radius=1, kernelType="square", units="pixels")
    return m.selfMask()


def reference_mask(site, aoi):
    """(pure-pixel mask, reference record) for one site."""
    kind = site["ref"][0]
    wc = ee.ImageCollection(WC).first().select("Map")
    glwd = ee.Image(GLWD).select("b1")

    if kind in ("osm_element", "osm_rooftop"):
        fc, rec = osm_reference(site)
        return _paint(_erode_fc(fc)), rec

    if kind == "glims_wc":
        g = ee.FeatureCollection(GLIMS).filterBounds(aoi)
        names = _get(g.aggregate_array("glac_name").distinct(), "glims names")
        n = _get(g.size(), "glims count")
        m = _paint(_erode_fc(g)).And(_erode_raster(wc.eq(WC_SNOW)))
        return m.selfMask(), {"glims_polygons": n,
                              "glims_names": [x for x in names if x][:10],
                              "worldcover_class": WC_SNOW}

    if kind == "mangrove":
        g = ee.FeatureCollection(GMW).filterBounds(aoi)
        n = _get(g.size(), "gmw count")
        m = (_paint(_erode_fc(g))
             .And(_erode_raster(glwd.eq(GLWD_MANGROVE)))
             .And(_erode_raster(wc.eq(WC_MANGROVE))))
        return m.selfMask(), {"gmw_polygons": n, "glwd_class": GLWD_MANGROVE,
                              "worldcover_class": WC_MANGROVE}

    if kind == "marsh":
        marsh = glwd.remap(GLWD_MARSH, [1] * len(GLWD_MARSH), 0)
        m = (_erode_raster(marsh.eq(1))
             .And(_erode_raster(wc.eq(WC_WETLAND))))
        return m.selfMask(), {"glwd_classes": GLWD_MARSH,
                              "worldcover_class": WC_WETLAND}

    if kind == "tidal_flat":
        mur = ee.ImageCollection(MURRAY).sort("system:time_start", False).first()
        period = _get(mur.get("system:index"), "murray period")
        m = _erode_raster(mur.select("classification").eq(MURRAY_TIDAL_FLAT))
        return m, {"murray_image": period, "class": MURRAY_TIDAL_FLAT}

    raise ValueError(kind)


def surround_mask(mask):
    """Ring SURROUND_INNER_M..SURROUND_OUTER_M outside the reference."""
    m = mask.unmask(0)
    outer = m.focalMax(SURROUND_OUTER_M, "circle", "meters")
    inner = m.focalMax(SURROUND_INNER_M, "circle", "meters")
    return outer.And(inner.Not()).selfMask()


# ------------------------------------------------------------- composite

def composite(aoi, window):
    def coll(pct):
        return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(aoi).filterDate(*window)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", pct)))
    pct = CLOUD_PCT
    c = coll(pct)
    n = _get(c.size(), "s2 count")
    if n < MIN_IMAGES:
        pct = CLOUD_PCT_FALLBACK
        c = coll(pct)
        n = _get(c.size(), "s2 count fallback")
    proj = c.first().select("B4").projection()
    crs = _get(proj.crs(), "s2 crs")
    return c.map(mask_s2_clouds).median(), crs, n, pct


def spectrum(img, mask, aoi, crs, label):
    red = (ee.Reducer.mean()
           .combine(ee.Reducer.stdDev(), sharedInputs=True)
           .combine(ee.Reducer.count(), sharedInputs=True))
    st = _get(img.updateMask(mask).reduceRegion(
        reducer=red, geometry=aoi, crs=crs, scale=SCALE_M,
        maxPixels=1e10, tileScale=4), label)
    n = st.get(f"{S2_BAND_NAMES[0]}_count") or 0
    mean = [st.get(f"{b}_mean") for b in S2_BAND_NAMES]
    sd = [st.get(f"{b}_stdDev") for b in S2_BAND_NAMES]
    if n == 0 or any(v is None for v in mean):
        return None, None, 0
    return ([round(v, 5) for v in mean], [round(v, 5) for v in sd], int(n))


def mask_count(mask, aoi, crs, label):
    st = _get(mask.reduceRegion(reducer=ee.Reducer.count(), geometry=aoi,
                                crs=crs, scale=SCALE_M, maxPixels=1e10,
                                tileScale=4), label)
    return int(next(iter(st.values())) or 0)


# ------------------------------------------------------------- main

def measure_site(site, verify_only):
    aoi = ee.Geometry.Rectangle(site["aoi"], None, False)
    mask, rec = reference_mask(site, aoi)
    img, crs, n_img, pct = composite(aoi, site["window"])
    out = dict(name=site["name"], fraction=site["fraction"],
               subtype=site["subtype"], aoi_wsen=site["aoi"],
               window=list(site["window"]), reference=rec,
               s2_crs=crs, n_images=n_img, cloud_pct_used=pct)
    if verify_only:
        out["n_pure_pixels"] = mask_count(mask, aoi, crs, f"{site['name']} mask")
        out["status"] = "ok" if out["n_pure_pixels"] >= MIN_PIXELS else "failed"
        return out
    mean, sd, n = spectrum(img, mask, aoi, crs, f"{site['name']} spectrum")
    smean, _, sn = spectrum(img, surround_mask(mask), aoi, crs,
                            f"{site['name']} surround")
    out.update(mean=mean, sd=sd, n_pixels=n, surround_mean=smean,
               surround_n=sn,
               status="ok" if n >= MIN_PIXELS and n_img >= MIN_IMAGES
               else "failed")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--verify", action="store_true",
                    help="reference masks and image counts only; no spectra")
    ap.add_argument("--only", nargs="*", help="site names")
    args = ap.parse_args()
    _ee_init()

    rows = []
    for site in SITES:
        if args.only and site["name"] not in args.only:
            continue
        print(f"--- {site['name']} ({site['fraction']}/{site['subtype']})",
              flush=True)
        try:
            r = measure_site(site, args.verify)
        except Exception as e:                       # noqa: BLE001
            r = dict(name=site["name"], fraction=site["fraction"],
                     subtype=site["subtype"], status="error",
                     error=f"{type(e).__name__}: {str(e)[:300]}")
        print(json.dumps(r), flush=True)
        rows.append(r)

    if args.verify:
        return
    out = dict(
        validation_status="experimental",
        measured_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        bands=S2_BAND_NAMES, units="surface reflectance (0-1)",
        method=dict(collection="COPERNICUS/S2_SR_HARMONIZED",
                    composite="median, SCL-masked (mask_s2_clouds)",
                    cloud_pct=CLOUD_PCT, cloud_pct_fallback=CLOUD_PCT_FALLBACK,
                    erode_m=ERODE_M, scale_m=SCALE_M,
                    min_pixels=MIN_PIXELS, min_images=MIN_IMAGES),
        sites=rows, not_measured=NOT_MEASURED)
    os.makedirs(os.path.dirname(ENDMEMBERS_PATH), exist_ok=True)
    with open(ENDMEMBERS_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {ENDMEMBERS_PATH}")
    if any(r["status"] != "ok" for r in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
