"""Sun geometry from building shadows (labelling/sun_geometry.py), for
imagery without a published acquisition time (guide v1.2, §5 / §8)."""
import json
import math
import pathlib
import sys
from datetime import date, datetime, timezone

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from labelling import sun_geometry as sg

# Maxar ARD item 42/031333030301/10300100D13F6500 (Karachi), published angles
KARACHI = dict(when=datetime(2022, 3, 29, 6, 26, 37, tzinfo=timezone.utc),
               lat=(25.074531079778954 + 25.084355) / 2, lon=(66.90132225441228 + 66.91951390433394) / 2,
               az=139.1, el=62.6)


def test_solar_position_matches_maxar_published_angles():
    az, el = sg.solar_position(KARACHI["when"], KARACHI["lat"], KARACHI["lon"])
    # observed agreement 2026-09-29: 0.04 deg azimuth, 0.14 deg elevation
    assert az == pytest.approx(KARACHI["az"], abs=0.2) and el == pytest.approx(KARACHI["el"], abs=0.2)


def test_solstice_noon_elevation():
    # max elevation at 40 N on the June solstice = 90 - 40 + 23.44
    best = max(sg.solar_position(datetime(2010, 6, 21, h, m, tzinfo=timezone.utc), 40.0, -105.0)[1]
               for h in range(17, 21) for m in range(0, 60, 2))
    assert best == pytest.approx(73.44, abs=0.1)


def test_inverse_recovers_time_and_elevation():
    sols = sg.elevation_for_azimuth(KARACHI["az"], date(2022, 3, 29), KARACHI["lat"], KARACHI["lon"])
    assert len(sols) == 1
    t, el = sols[0]
    assert abs((t - KARACHI["when"]).total_seconds()) < 60 and el == pytest.approx(KARACHI["el"], abs=0.2)


def test_daylight_check_flags_night_windows():
    lima = (-12.2, -76.9)
    assert sg.is_daylight(datetime(2019, 12, 19, 15, 30, tzinfo=timezone.utc),
                          datetime(2019, 12, 19, 16, 0, tzinfo=timezone.utc), *lima)
    assert not sg.is_daylight(datetime(2019, 12, 19, 5, 0, tzinfo=timezone.utc),
                              datetime(2019, 12, 19, 6, 0, tzinfo=timezone.utc), *lima)


def test_circular_mean_across_north():
    m, sd = sg.circular_mean_deg([350, 10, 0])
    assert min(m, 360 - m) == pytest.approx(0, abs=1e-9) and sd < 10


def _lines_for_sun(az_true, crs, x, y, n=3):
    """Shadow lines pointing away from a sun at true azimuth `az_true`, drawn
    in grid coordinates (the grid convergence removed)."""
    from pyproj import CRS, Proj, Transformer
    from shapely.geometry import LineString
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    conv = Proj(CRS.from_user_input(crs)).get_factors(lon, lat).meridian_convergence
    grid = math.radians((az_true + 180 - conv) % 360)
    return [LineString([(x + 5 * i, y), (x + 5 * i + 4 * math.sin(grid), y + 4 * math.cos(grid))])
            for i in range(n)]


def test_measure_recovers_azimuth_and_elevation_karachi():
    from pyproj import Transformer
    crs = "EPSG:32642"
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(KARACHI["lon"], KARACHI["lat"])
    lines = _lines_for_sun(KARACHI["az"], crs, x, y)
    r = sg.measure(lines, crs, KARACHI["lat"], KARACHI["lon"], [date(2022, 3, 29)], 3)
    assert r["sun_azimuth_deg"] == pytest.approx(KARACHI["az"], abs=0.1)
    assert r["sun_elevation_deg"] == pytest.approx(KARACHI["el"], abs=0.2)
    assert r["sun_geometry_n_buildings"] == 3 and "3 building-shadow bearings" in r["sun_geometry_method"]


def test_measure_over_a_date_range_records_midpoint_and_range():
    from pyproj import Transformer
    crs, lat, lon = "EPSG:32734", -34.04, 18.67                  # Khayelitsha
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
    az = sg.solar_position(datetime(2025, 1, 15, 8, 30, tzinfo=timezone.utc), lat, lon)[0]
    days = [date(2025, 1, d) for d in range(1, 32)]
    r = sg.measure(_lines_for_sun(az, crs, x, y), crs, lat, lon, days, 3)
    lo, hi = r["detail"]["elevation_range_deg"]
    assert lo < hi and r["sun_elevation_deg"] == pytest.approx((lo + hi) / 2, abs=0.05)
    assert "date range" in r["sun_geometry_method"] and len(r["detail"]["per_day"]) == 31


def test_fewer_than_three_buildings_refused():
    from shapely.geometry import LineString
    with pytest.raises(ValueError, match=">= 3 buildings"):
        sg.measure([LineString([(0, 0), (1, 1)])] * 2, "EPSG:32642", 25.0, 67.0, [date(2022, 3, 29)], 3)


def test_setup_and_run_write_the_record_fields(tmp_path):
    import geopandas as gpd
    import pyogrio
    from pyproj import Transformer
    crs = "EPSG:32642"
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(KARACHI["lon"], KARACHI["lat"])
    meta = {"tile_utm": {"crs": crs, "x0": x - 100, "y1": y + 100, "size_m": 200},
            "imagery_acquisition_date": "2022-03-29", "imagery_acquisition_date_end": None}
    (tmp_path / "metadata.json").write_text(json.dumps(meta))
    sg.setup(str(tmp_path), crs)
    with pytest.raises(FileExistsError):
        sg.setup(str(tmp_path), crs)
    g = gpd.GeoDataFrame({"building": [1, 2, 3], "note": ["", "", ""]},
                         geometry=_lines_for_sun(KARACHI["az"], crs, x, y), crs=crs)
    pyogrio.write_dataframe(g, str(tmp_path / "sun.gpkg"), layer=sg.LAYER, append=True)
    from labelling.common import load_config
    sg.run(str(tmp_path), load_config())
    out = json.loads((tmp_path / "metadata.json").read_text())
    for k in ("sun_azimuth_deg", "sun_elevation_deg", "sun_geometry_method", "sun_geometry_n_buildings"):
        assert out[k] is not None
    assert out["sun_azimuth_deg"] == pytest.approx(KARACHI["az"], abs=0.1)


def test_uploader_window_corroboration():
    lat, lon = -12.2, -76.9                                      # Lima, Candelaria window
    w = ["2019-12-19T15:30:00.000Z", "2019-12-19T16:00:00.000Z"]
    az_mid = sg.solar_position(datetime(2019, 12, 19, 15, 45, tzinfo=timezone.utc), lat, lon)[0]
    ok = sg.corroborate(az_mid, w, lat, lon, 5)
    assert ok["status"] == "corroborated" and ok["min_difference_deg"] < 1
    far = sg.corroborate((az_mid + 40) % 360, w, lat, lon, 5)
    assert far["status"] == "not corroborated" and far["min_difference_deg"] > 5
    night = sg.corroborate(az_mid, ["2019-12-19T05:00:00Z", "2019-12-19T06:00:00Z"], lat, lon, 5)
    assert night["status"].startswith("not checkable")


def test_corroboration_threshold_is_the_decided_one():
    from labelling.common import load_config
    assert load_config()["sun_geometry"]["uploader_window_corroboration_max_az_diff_deg"] == 5
