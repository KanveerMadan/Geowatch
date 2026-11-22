"""
Reproduce, independently, the GEDTM30 v1.2 scale-factor finding (flood-core
prototype). Nothing is corrected: raw values, the header's declared scale
and offset, and what a scale-honouring reader would return are all printed
side by side, against published benchmark elevations that do not come from
any DEM. Run with the prototype environment (gw-floodproto-env).
"""
import json
import sys

import numpy as np
import rasterio
from rasterio.windows import Window

URL = ("/vsicurl/https://s3.opengeohub.org/global/dtm/v1.2/"
       "gedtm_rf_{}_30m_s_20060101_20151231_go_epsg.4326.3855_v1.2.tif")
# (lon, lat, published elevation m, source of the published figure)
BENCH = {
    "denver_capitol_mile_step": (-104.98493, 39.73927, 1609.3, "Colorado State Capitol 'one mile above sea level' step"),
    "el_alto_airport": (-68.19226, -16.51333, 4061.5, "El Alto International Airport (LPB) aerodrome elevation"),
    "dead_sea_shore_ein_bokek": (35.3640, 31.2010, -430.0, "Dead Sea shoreline, approx. -430 m (falling)"),
}


def main(out):
    res = {"gdal": rasterio.__gdal_version__, "rasterio": rasterio.__version__, "layers": {}, "points": {}}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="60"):
        for lay in ("m", "std"):
            with rasterio.open(URL.format(lay)) as ds:
                res["layers"][lay] = {"dtype": ds.dtypes[0], "nodata": ds.nodata, "scales": list(ds.scales),
                                      "offsets": list(ds.offsets), "units": list(ds.units),
                                      "tags": ds.tags(), "band_tags": ds.tags(1), "crs": str(ds.crs)}
                for name, (lon, lat, pub, src) in BENCH.items():
                    r, c = ds.index(lon, lat)
                    a = ds.read(1, window=Window(c - 1, r - 1, 3, 3)).astype("float64")
                    a[a == ds.nodata] = np.nan
                    raw = float(np.nanmedian(a))
                    p = res["points"].setdefault(name, {"lon": lon, "lat": lat, "published_m": pub, "published_src": src})
                    p[f"{lay}_raw"] = round(raw, 2)
                    p[f"{lay}_raw_x_header_scale"] = round(raw * ds.scales[0] + ds.offsets[0], 3)
    json.dump(res, open(out, "w"), indent=1)
    for k, v in res["layers"].items():
        print(k, {kk: v[kk] for kk in ("dtype", "scales", "offsets", "units", "band_tags")})
    for k, v in res["points"].items():
        print(k, v)


if __name__ == "__main__":
    main(sys.argv[1])
