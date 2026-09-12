r"""
C4 regression tests — band order was asserted by a comment, not by code.

04_FINDINGS_LEDGER.md C4 [S], build item 44: `RGB_BAND_INDICES` pinned indices
2/1/0 assuming the GeoTIFF's bands are
["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"], enforced only by a
top-of-file comment reading "Must match S2_BAND_NAMES order in sentinel2.py".
If it drifted, R and B would be silently swapped into both the SAM segmentation
input and the classifier input — no error, same array shapes, just a different
image than the model was trained on.

01_DIAGNOSIS.md §4 S3: "a rule enforced only by prose fails at the first edit
made by someone who did not read the prose."

WHAT THE INVESTIGATION FOUND, which changed the shape of the fix. Item 44 says
to check the file's actual band descriptions. Measured first, across every
GeoTIFF this project has produced:

    150 of 150 raw.tif files report descriptions == (None,) * 6

Neither geemap's export nor the chunked stitcher writes band descriptions, so
the check as specified had nothing to read. Asserting equality would have failed
on every existing file; asserting only-when-present would never have fired —
decoration, which is the standard C16 and item 47 were held to.

So the fix has four parts, and the tests below cover each:
  1. BAND_NAMES is DERIVED from sentinel2.py, not retyped, plus an import-time
     assertion — the cross-module contract is code now.
  2. RGB_BAND_INDICES is DERIVED from BAND_NAMES, so a reorder moves the indices
     with it. This is what makes the silent swap impossible rather than merely
     detectable.
  3. Exports STAMP the band names into the file, so the contract travels with
     the data and the read check has something real to verify.
  4. The read boundary verifies against the FILE, with three distinct verdicts.

Run from the repo root:  pytest tests/test_band_order.py
"""

import os

import numpy as np
import pytest
import rasterio

from ingestion.sentinel2 import S2_BAND_NAMES
from ingestion.tiler import (
    BAND_NAMES,
    BAND_ORDER_STRICT_ENV,
    RGB_BAND_INDICES,
    BandOrderError,
    assert_band_order,
    stamp_band_descriptions,
)


def _write_tif(path, descriptions, count=None, size=4):
    """
    A real GeoTIFF with chosen band descriptions.

    Written rather than mocked: the thing under test is how rasterio reports a
    file's metadata, and a mock would only assert that the test author
    understands rasterio, which is the assumption most likely to be wrong.
    """
    n = count if count is not None else len(descriptions)
    data = np.zeros((n, size, size), dtype=np.float32)
    profile = {
        "driver": "GTiff", "width": size, "height": size, "count": n,
        "dtype": "float32", "crs": "EPSG:4326",
        "transform": rasterio.transform.from_origin(0, 0, 1e-4, 1e-4),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
        if descriptions is not None:
            dst.descriptions = tuple(descriptions)
    return str(path)


# ── 1. The cross-module contract ──

def test_band_names_are_derived_from_sentinel2_not_retyped():
    """
    The comment said these must match. They are now the same list, so they
    cannot disagree — there is no second literal to drift.
    """
    assert BAND_NAMES == list(S2_BAND_NAMES)


def test_tiler_does_not_redefine_the_band_list():
    src = open("ingestion/tiler.py").read()
    assert 'BAND_NAMES = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]' not in src, (
        "tiler.py has a literal band list again; derive it from sentinel2.py"
    )
    assert "from ingestion.sentinel2 import S2_BAND_NAMES" in src


# ── 2. Derived indices: the silent-swap fix ──

def test_rgb_indices_are_derived_not_pinned():
    src = open("ingestion/tiler.py").read()
    assert 'RGB_BAND_INDICES = {"Red": 2, "Green": 1, "Blue": 0}' not in src, (
        "RGB_BAND_INDICES is hardcoded again; it must be derived from BAND_NAMES"
    )


def test_rgb_indices_match_the_current_order():
    """Current values are unchanged — the refactor must not repaint anything."""
    assert RGB_BAND_INDICES == {"Red": 2, "Green": 1, "Blue": 0}
    for name, idx in RGB_BAND_INDICES.items():
        assert BAND_NAMES[idx] == name


def test_reordering_bands_moves_the_indices_with_them():
    """
    The property that kills C4 at the root. With pinned 2/1/0 a reordered band
    list would leave the indices pointing at the wrong channels; derived, they
    follow. Recomputed the same way tiler.py does rather than re-importing,
    since the module binds at import.
    """
    swapped = ["Red", "Green", "Blue", "NIR", "SWIR1", "SWIR2"]
    derived = {n: swapped.index(n) for n in ("Red", "Green", "Blue")}
    assert derived == {"Red": 0, "Green": 1, "Blue": 2}, (
        "derived indices did not follow the reordered band list"
    )
    for name, idx in derived.items():
        assert swapped[idx] == name


# ── 3. Stamping: making the check checkable ──

def test_export_stamps_band_descriptions(tmp_path):
    path = _write_tif(tmp_path / "unstamped.tif", [None] * 6)
    with rasterio.open(path) as src:
        assert all(d is None for d in src.descriptions), "precondition"
    assert stamp_band_descriptions(path) is True
    with rasterio.open(path) as src:
        assert list(src.descriptions) == BAND_NAMES


def test_stamping_refuses_a_file_with_the_wrong_band_count(tmp_path):
    """Stamping six names onto three bands would invent a contract."""
    path = _write_tif(tmp_path / "three.tif", [None] * 3)
    assert stamp_band_descriptions(path) is False


def test_stamping_never_raises_on_a_bad_path():
    """Failing to ANNOTATE a good export must not fail the export."""
    assert stamp_band_descriptions("/nonexistent/path/nope.tif") is False


def test_export_path_calls_the_stamper():
    src = open("ingestion/tiler.py").read()
    assert "stamp_band_descriptions(output_path)" in src, (
        "export_image_local must stamp, or the read check can never verify"
    )


# ── 4. The read boundary: the item's stated test ──

def test_correct_order_does_not_fire(tmp_path):
    """The negative control. A fix that always raises would be useless."""
    path = _write_tif(tmp_path / "good.tif", BAND_NAMES)
    with rasterio.open(path) as src:
        assert assert_band_order(src, path) == "verified"


WRONG_ORDERS = [
    pytest.param(["Red", "Green", "Blue", "NIR", "SWIR1", "SWIR2"], id="rgb-swapped"),
    pytest.param(["Blue", "Red", "Green", "NIR", "SWIR1", "SWIR2"], id="green-red-swapped"),
    pytest.param(["Blue", "Green", "Red", "SWIR1", "NIR", "SWIR2"], id="nir-swir1-swapped"),
    pytest.param(["SWIR2", "SWIR1", "NIR", "Red", "Green", "Blue"], id="fully-reversed"),
    pytest.param(["B2", "B3", "B4", "B8", "B11", "B12"], id="raw-gee-band-ids"),
    pytest.param(["Blue", "Green", "Red", "NIR", "SWIR1", "Cirrus"], id="one-band-different"),
]


@pytest.mark.parametrize("descriptions", WRONG_ORDERS)
def test_wrong_order_fires(tmp_path, descriptions):
    """
    The item's core assertion: a deliberately wrong band order must raise.
    `rgb-swapped` is C4's exact failure — R and B transposed.
    """
    path = _write_tif(tmp_path / "wrong.tif", descriptions)
    with rasterio.open(path) as src:
        with pytest.raises(BandOrderError, match="BAND ORDER MISMATCH"):
            assert_band_order(src, path)


def test_the_error_names_both_orders(tmp_path):
    """A mismatch the reader cannot diagnose is only half a control."""
    wrong = ["Red", "Green", "Blue", "NIR", "SWIR1", "SWIR2"]
    path = _write_tif(tmp_path / "wrong.tif", wrong)
    with rasterio.open(path) as src:
        with pytest.raises(BandOrderError) as exc:
            assert_band_order(src, path)
    msg = str(exc.value)
    assert str(wrong) in msg, "must report what the file says"
    assert str(BAND_NAMES) in msg, "must report what the pipeline assumes"


# ── The third verdict: absent descriptions ──

def test_absent_descriptions_are_unverifiable_not_verified(tmp_path):
    """
    The state 150 of 150 existing files are in. It must NOT read as verified:
    "nobody checked" rendering as "checked and fine" is the same collapse C23
    made with Gate C's waiver.
    """
    path = _write_tif(tmp_path / "bare.tif", [None] * 6)
    with rasterio.open(path) as src:
        assert assert_band_order(src, path) == "unverifiable"


def test_absent_descriptions_warn_loudly(tmp_path, capsys):
    path = _write_tif(tmp_path / "bare.tif", [None] * 6)
    with rasterio.open(path) as src:
        assert_band_order(src, path)
    out = capsys.readouterr().out
    assert "UNVERIFIED" in out
    assert "stamp_band_descriptions" in out, "the warning must say how to fix it"


def test_strict_mode_promotes_unverifiable_to_an_error(tmp_path):
    path = _write_tif(tmp_path / "bare.tif", [None] * 6)
    with rasterio.open(path) as src:
        with pytest.raises(BandOrderError, match="UNVERIFIED"):
            assert_band_order(src, path, strict=True)


def test_strict_mode_reads_the_env_var(tmp_path, monkeypatch):
    path = _write_tif(tmp_path / "bare.tif", [None] * 6)
    monkeypatch.setenv(BAND_ORDER_STRICT_ENV, "1")
    with rasterio.open(path) as src:
        with pytest.raises(BandOrderError):
            assert_band_order(src, path)


def test_strict_mode_still_accepts_a_correctly_stamped_file(tmp_path):
    """Strict must reject the unverifiable, not everything."""
    path = _write_tif(tmp_path / "good.tif", BAND_NAMES)
    with rasterio.open(path) as src:
        assert assert_band_order(src, path, strict=True) == "verified"


# ── Band count: previously a print() execution ran past ──

@pytest.mark.parametrize("count", [1, 3, 5, 7])
def test_wrong_band_count_raises(tmp_path, count):
    path = _write_tif(tmp_path / f"bands{count}.tif", [None] * count, count=count)
    with rasterio.open(path) as src:
        with pytest.raises(BandOrderError, match="expected 6 bands"):
            assert_band_order(src, path)


def test_wrong_count_raises_even_in_non_strict_mode(tmp_path):
    """
    A wrong count is never merely unverifiable: every index into the array is
    meaningless, including RGB_BAND_INDICES. It was previously a print().
    """
    path = _write_tif(tmp_path / "three.tif", [None] * 3, count=3)
    with rasterio.open(path) as src:
        with pytest.raises(BandOrderError):
            assert_band_order(src, path, strict=False)


# ── Both read boundaries are guarded ──

@pytest.mark.parametrize("func", ["generate_tiles", "generate_rgb_preview_tiles"])
def test_both_read_boundaries_assert(func):
    """
    generate_tiles is the TRAINING path (a wrong order is baked into every .npy);
    generate_rgb_preview_tiles is the function that actually indexes with
    RGB_BAND_INDICES. Both must check.
    """
    import inspect
    import ingestion.tiler as tiler
    src = inspect.getsource(getattr(tiler, func))
    assert "assert_band_order(src, image_path)" in src, (
        f"{func} opens a GeoTIFF without verifying its band order"
    )


def test_stamp_then_verify_round_trip(tmp_path):
    """The full loop, as it will run on a fresh export."""
    path = _write_tif(tmp_path / "run.tif", [None] * 6)
    with rasterio.open(path) as src:
        assert assert_band_order(src, path) == "unverifiable"
    stamp_band_descriptions(path)
    with rasterio.open(path) as src:
        assert assert_band_order(src, path, strict=True) == "verified"
