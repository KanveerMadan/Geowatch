"""
C2 / build item 52 — a GEE export is checked against what was requested, and
the API's AOI cap agrees with what the tiler can actually export.

04_FINDINGS_LEDGER.md C2 [R]: `export_image_local` trusted
`geemap.ee_export_image` with no check on dimensions, band count or CRS. A file
of the wrong shape would flow on into tiling, segmentation and the frontend
projection without an error anywhere.

The request is fully determined before the download starts: width and height
come from `_compute_export_grid` (measured to reproduce 137 of 137 real
`raw.tif` files exactly), band count from `image.bandNames()`, and the CRS is
EPSG:4326, the lattice the grid is computed on. The checks are therefore exact
equality, with no tolerance.

geemap and Earth Engine are replaced with stubs that write a GeoTIFF of a
chosen shape. Nothing here touches the network.

Run from the repo root:  pytest tests/test_export_validation.py
"""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ingestion import tiler

# The canonical Dharavi AOI. Its grid is 291 x 257, matching every Dharavi
# raw.tif on disk.
DHARAVI = (72.836, 19.037, 72.862, 19.060)


def _write_tif(path, width, height, count, crs="EPSG:4326"):
    data = np.zeros((count, height, width), dtype=np.float32)
    with rasterio.open(
        path, "w", driver="GTiff", width=width, height=height, count=count,
        dtype="float32", crs=crs,
        transform=from_origin(72.8, 19.06, tiler.DEGREES_PER_PIXEL_AT_SCALE_10,
                              tiler.DEGREES_PER_PIXEL_AT_SCALE_10),
    ) as dst:
        dst.write(data)


class _Info:
    def __init__(self, value):
        self._value = value

    def getInfo(self):
        return self._value


class FakeImage:
    def __init__(self, n_bands=6):
        self._bands = list(tiler.BAND_NAMES)[:n_bands]

    def bandNames(self):
        return _Info(self._bands)


class FakeAOI:
    def __init__(self, west, south, east, north):
        self._ring = [[west, south], [east, south], [east, north],
                      [west, north], [west, south]]

    def bounds(self):
        return _Info({"coordinates": [self._ring]})


@pytest.fixture
def fake_geemap(monkeypatch):
    """Stub geemap.ee_export_image to write a file of a configurable shape."""
    import geemap
    shape = {"width": None, "height": None, "count": 6, "crs": "EPSG:4326"}

    def fake_export(image, filename, scale, region, file_per_band, **kw):
        _write_tif(filename, shape["width"], shape["height"], shape["count"],
                   shape["crs"])

    monkeypatch.setattr(geemap, "ee_export_image", fake_export)
    grid = tiler._compute_export_grid(*DHARAVI)
    shape["width"], shape["height"] = grid["width"], grid["height"]
    return shape


def _export(tmp_path):
    return tiler.export_image_local(
        FakeImage(), FakeAOI(*DHARAVI), str(tmp_path / "raw.tif"))


def test_correct_export_passes(fake_geemap, tmp_path):
    assert _export(tmp_path).endswith("raw.tif")


@pytest.mark.parametrize("field,value,named", [
    ("width", 290, "width"),           # one column short
    ("height", 258, "height"),         # one row extra
    ("count", 3, "band"),              # RGB-only download
    ("crs", "EPSG:3857", "crs"),       # right pixels, wrong CRS
])
def test_mismatched_export_fails_loudly(fake_geemap, tmp_path, field, value, named):
    fake_geemap[field] = value
    with pytest.raises(RuntimeError) as exc:
        _export(tmp_path)
    assert named in str(exc.value).lower()


def test_mismatched_export_is_not_left_on_disk(fake_geemap, tmp_path):
    """A file that failed validation must not survive at the output path,
    where a later step or a re-run could pick it up as a good export."""
    fake_geemap["width"] = 100
    with pytest.raises(RuntimeError):
        _export(tmp_path)
    assert not (tmp_path / "raw.tif").exists()


def test_validator_reports_every_mismatch_at_once(tmp_path):
    path = tmp_path / "bad.tif"
    _write_tif(path, 10, 20, 3, "EPSG:3857")
    with pytest.raises(tiler.ExportValidationError) as exc:
        tiler.validate_export(str(path), expected_width=11, expected_height=21,
                              expected_bands=6)
    msg = str(exc.value)
    for fragment in ("width", "height", "band", "crs"):
        assert fragment in msg.lower()


# ── The size gap: one number, not two ────────────────────────────────────

def test_tiler_no_longer_documents_a_5_km2_limit():
    doc = tiler.export_image_local.__doc__ or ""
    assert "5 sq km" not in doc


def test_api_cap_is_within_the_measured_tiler_limit():
    """The API admits nothing the tiler has not been measured to export."""
    import api
    assert api.MAX_AOI_AREA_KM2 <= tiler.MEASURED_MAX_EXPORT_AREA_KM2
