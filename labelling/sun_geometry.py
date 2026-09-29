"""
Sun azimuth and elevation from building shadows, for tiles whose imagery has
no published acquisition time (LABELLING_GUIDE.md §5 / §8, v1.2: "sun azimuth
and elevation measured from the shadows of at least 3 buildings in the tile,
and the method used").

The labeller draws one LINE per building in the tile's sun.gpkg (layer
`sun_shadows`), from a roof corner to the matching corner of its shadow on
the ground. At least `sun_geometry.min_buildings` (3) buildings.

  azimuth    the shadow points away from the sun: sun azimuth = the lines'
             circular-mean bearing + 180 deg. Bearings are converted from UTM
             grid north to true north with the grid (meridian) convergence.
  elevation  is not measurable from an orthophoto shadow without a building
             height. It is DERIVED from the measured azimuth: for the
             acquisition date (or each day of a date range) and the tile
             location, the time of day at which the sun has that azimuth is
             solved, and the elevation at that time taken. For a date range,
             the value recorded is the midpoint of the elevations over the
             range, and the range itself is recorded beside it.

Solar position: the NOAA Solar Calculator spreadsheet algorithm (NOAA
Global Monitoring Laboratory; after Meeus, "Astronomical Algorithms"),
geometric -- no refraction correction. Checked against Maxar's
published sun angles for the Karachi scene (tests).

    python -m labelling.sun_geometry --setup <tile dir>   # add sun.gpkg
    python -m labelling.sun_geometry <tile dir>           # measure -> metadata.json
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone

import numpy as np

LAYER = "sun_shadows"
METHOD = ("azimuth: circular mean of {n} building-shadow bearings (roof corner -> shadow corner) + 180, "
          "grid->true north by meridian convergence; elevation: solved from that azimuth for {dates} at the "
          "tile centre with the NOAA Solar Calculator algorithm (geometric){range}")


# ── solar position (NOAA general solar position calculations) ────────────────

def solar_position(when: datetime, lat: float, lon: float) -> tuple:
    """(azimuth deg clockwise from true north, elevation deg) at UTC `when`.
    The NOAA Solar Calculator spreadsheet algorithm (after Meeus, Astronomical
    Algorithms), geometric elevation (no refraction)."""
    when = when.astimezone(timezone.utc)
    jd = (when - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400 + 2451545.0
    T = (jd - 2451545.0) / 36525                                          # Julian century
    L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360          # geom. mean longitude
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)                   # geom. mean anomaly
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)              # orbit eccentricity
    Mr = math.radians(M)
    C = (math.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T))
         + math.sin(2 * Mr) * (0.019993 - 0.000101 * T) + math.sin(3 * Mr) * 0.000289)
    true_long = L0 + C
    omega = 125.04 - 1934.136 * T
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(app_long)))
    y = math.tan(math.radians(eps / 2)) ** 2
    L0r = math.radians(L0)
    eqtime = 4 * math.degrees(y * math.sin(2 * L0r) - 2 * e * math.sin(Mr) + 4 * e * y * math.sin(Mr)
                              * math.cos(2 * L0r) - 0.5 * y * y * math.sin(4 * L0r)
                              - 1.25 * e * e * math.sin(2 * Mr))          # minutes
    minutes = when.hour * 60 + when.minute + when.second / 60 + when.microsecond / 6e7
    tst = (minutes + eqtime + 4 * lon) % 1440                             # true solar time
    ha = tst / 4 - 180 if tst / 4 >= 0 else tst / 4 + 180                 # hour angle, deg
    la = math.radians(lat)
    cos_zen = (math.sin(la) * math.sin(decl)
               + math.cos(la) * math.cos(decl) * math.cos(math.radians(ha)))
    zen = math.acos(max(-1.0, min(1.0, cos_zen)))
    denom = math.cos(la) * math.sin(zen)
    if abs(denom) < 1e-12:
        az = 180.0 if lat > 0 else 0.0
    else:
        a = math.degrees(math.acos(max(-1.0, min(1.0, (math.sin(la) * math.cos(zen) - math.sin(decl)) / denom))))
        az = (a + 180) % 360 if ha > 0 else (540 - a) % 360
    return az, 90 - math.degrees(zen)


def is_daylight(start: datetime, end: datetime, lat: float, lon: float) -> bool:
    """True if the sun is above the horizon at both ends of a published window."""
    return solar_position(start, lat, lon)[1] > 0 and solar_position(end, lat, lon)[1] > 0


def _angdiff(a, b):
    return (a - b + 180) % 360 - 180


def elevation_for_azimuth(azimuth: float, day: date, lat: float, lon: float) -> list:
    """Every (UTC time, elevation) on `day` with the sun up at `azimuth`.
    Minute scan of the UTC day plus the neighbouring half-days (local days
    straddle UTC midnight), root by linear interpolation."""
    t0 = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(hours=12)
    times = [t0 + timedelta(minutes=m) for m in range(0, 48 * 60 + 1)]
    pos = [solar_position(t, lat, lon) for t in times]
    out = []
    for i in range(len(times) - 1):
        (a0, e0), (a1, e1) = pos[i], pos[i + 1]
        if e0 <= 0 or e1 <= 0:
            continue
        d0, d1 = _angdiff(a0, azimuth), _angdiff(a1, azimuth)
        if d0 == 0 or (d0 < 0 < d1) or (d1 < 0 < d0):
            if abs(d0 - d1) > 180:                      # wrap, not a crossing
                continue
            f = 0.0 if d0 == d1 else d0 / (d0 - d1)
            t = times[i] + (times[i + 1] - times[i]) * f
            if t.date() == day or abs((t - datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc))
                                      .total_seconds()) <= 12 * 3600:
                out.append((t, solar_position(t, lat, lon)[1]))
    return out


# ── shadows ──────────────────────────────────────────────────────────────────

def circular_mean_deg(angles) -> tuple:
    """(mean, circular standard deviation) in degrees."""
    r = np.radians(np.asarray(angles, float))
    c, s = np.cos(r).mean(), np.sin(r).mean()
    R = math.hypot(c, s)
    return math.degrees(math.atan2(s, c)) % 360, math.degrees(math.sqrt(-2 * math.log(max(R, 1e-12))))


def shadow_bearings(lines, crs: str) -> list:
    """True-north bearings (deg) of roof-corner -> shadow-corner lines drawn in
    UTM `crs`: grid bearing + meridian convergence at the line's start."""
    from pyproj import CRS, Proj, Transformer
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    proj = Proj(CRS.from_user_input(crs))
    out = []
    for ln in lines:
        (x0, y0), (x1, y1) = ln.coords[0], ln.coords[-1]
        grid = math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360
        lon, lat = to_ll.transform(x0, y0)
        conv = proj.get_factors(lon, lat).meridian_convergence
        out.append((grid + conv) % 360)
    return out


def measure(lines, crs: str, lat: float, lon: float, days: list, min_buildings: int) -> dict:
    """Sun geometry from >= min_buildings shadow lines over the date(s) `days`."""
    if len(lines) < min_buildings:
        raise ValueError(f"{len(lines)} shadow line(s); the guide needs >= {min_buildings} buildings")
    bearings = shadow_bearings(lines, crs)
    shadow_mean, spread = circular_mean_deg(bearings)
    azimuth = (shadow_mean + 180) % 360
    per_day = {}
    for d in days:
        sols = elevation_for_azimuth(azimuth, d, lat, lon)
        if len(sols) != 1:
            raise ValueError(f"{d}: the sun reaches azimuth {azimuth:.1f} deg {len(sols)} times while up "
                             f"-- elevation is not determined")
        per_day[d.isoformat()] = {"utc": sols[0][0].isoformat(timespec="minutes"),
                                  "elevation_deg": round(sols[0][1], 2)}
    els = [v["elevation_deg"] for v in per_day.values()]
    lo, hi = min(els), max(els)
    rng = "" if len(days) == 1 else f"; date range: midpoint of the elevations {lo:.1f}-{hi:.1f} deg recorded"
    dates = days[0].isoformat() if len(days) == 1 else f"{days[0].isoformat()}..{days[-1].isoformat()}"
    return {"sun_azimuth_deg": round(azimuth, 1), "sun_elevation_deg": round((lo + hi) / 2, 1),
            "sun_geometry_method": METHOD.format(n=len(lines), dates=dates, range=rng),
            "sun_geometry_n_buildings": len(lines),
            "detail": {"shadow_bearings_true_deg": [round(b, 1) for b in bearings],
                       "bearing_circular_sd_deg": round(spread, 1),
                       "elevation_range_deg": [lo, hi], "per_day": per_day}}


# ── files ────────────────────────────────────────────────────────────────────

def sun_qml() -> str:
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<!-- Sun-geometry shadow lines (labelling/sun_geometry.py). Generated; do not hand-edit.
     One line per building: roof corner -> the same corner's shadow on the ground. -->
<qgis version="3.28" styleCategories="Symbology|Fields|Forms">
  <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <symbols>
      <symbol type="line" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleLine" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option name="line_color" type="QString" value="255,140,0,255"/>
            <Option name="line_width" type="QString" value="0.6"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
  <defaults>
    <default field="building" expression="coalesce(maximum(&quot;building&quot;), 0) + 1" applyOnUpdate="0"/>
  </defaults>
</qgis>
'''


def setup(tile_dir: str, crs: str) -> str:
    import geopandas as gpd
    import pandas as pd
    from labelling.gpkg_style import write_gpkg
    path = os.path.join(tile_dir, "sun.gpkg")
    if os.path.exists(path):
        raise FileExistsError(path)
    gdf = gpd.GeoDataFrame({"building": pd.Series([], dtype="int32"), "note": pd.Series([], dtype="object")},
                           geometry=gpd.GeoSeries([], crs=crs), crs=crs)
    return write_gpkg(path, gdf, LAYER, sun_qml(), geometry_type="LineString")


def run(tile_dir: str, cfg: dict) -> dict:
    import pyogrio
    from pyproj import Transformer
    with open(os.path.join(tile_dir, "metadata.json")) as fh:
        meta = json.load(fh)
    crs = meta["tile_utm"]["crs"]
    gdf = pyogrio.read_dataframe(os.path.join(tile_dir, "sun.gpkg"), layer=LAYER)
    lines = [g for g in gdf.geometry if g is not None and not g.is_empty]
    cx = meta["tile_utm"]["x0"] + meta["tile_utm"]["size_m"] / 2
    cy = meta["tile_utm"]["y1"] - meta["tile_utm"]["size_m"] / 2
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(cx, cy)
    d0 = date.fromisoformat(meta["imagery_acquisition_date"])
    d1 = date.fromisoformat(meta.get("imagery_acquisition_date_end") or meta["imagery_acquisition_date"])
    days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    res = measure(lines, crs, lat, lon, days, cfg["sun_geometry"]["min_buildings"])
    for k in ("sun_azimuth_deg", "sun_elevation_deg", "sun_geometry_method", "sun_geometry_n_buildings"):
        meta[k] = res[k]
    meta["sun_geometry_detail"] = res["detail"]
    with open(os.path.join(tile_dir, "metadata.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    return res


def main(argv=None):
    import argparse
    from labelling.common import load_config
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tile_dir")
    ap.add_argument("--setup", action="store_true", help="add the empty sun.gpkg")
    a = ap.parse_args(argv)
    if a.setup:
        with open(os.path.join(a.tile_dir, "metadata.json")) as fh:
            crs = json.load(fh)["tile_utm"]["crs"]
        print(setup(a.tile_dir, crs))
        return
    r = run(a.tile_dir, load_config())
    print(json.dumps({k: r[k] for k in ("sun_azimuth_deg", "sun_elevation_deg", "sun_geometry_n_buildings")}),
          "| bearing spread (circular sd):", r["detail"]["bearing_circular_sd_deg"], "deg")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
