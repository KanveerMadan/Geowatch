"""Item 35 (C25/C26): per-ward observed_fraction and valid-pixel count. A
100%-unobserved and a 50%-unobserved ward are distinguishable from the
output alone, and a half-observed ward's value is over its observed part."""
import numpy as np
import pytest
from shapely.geometry import box

from analysis import contract as C
from analysis.wards import materialize, observation_per_unit, ward_context
from tests import analysis_synth as S


class AllVegLeftHalfUnobserved(S.SynthProducer):
    def fetch_composite(self, layer, transform, shape, window):
        c = super().fetch_composite(layer, transform, shape, window)
        H, W = shape
        c["ndvi"] = np.full(shape, 0.6, dtype=np.float32)        # vegetation = 1 everywhere
        c["mndwi"] = np.full(shape, -0.3, dtype=np.float32)
        c["valid_obs"] = np.full(shape, 10, dtype=np.int32)
        c["valid_obs"][:, : W // 2] = 0                            # left half unobserved
        return c


def test_unobserved_and_half_observed_units_are_distinguishable():
    from rasterio.transform import from_origin
    tr = from_origin(0, 100, 10, 10)                    # 10 x 10 pixels of 10 m
    valid = np.full((10, 10), 10)
    valid[:, :5] = 0
    fset = {"valid_obs": valid, "transform": tr, "shape": (10, 10)}
    # Units partition the AOI, so each case is its own partition here.
    dark, lit = observation_per_unit([box(0, 0, 50, 100), box(50, 0, 100, 100)], fset)
    assert dark == {"observed_fraction": 0.0, "valid_pixel_count": 0, "pixel_count": 50}
    assert lit == {"observed_fraction": 1.0, "valid_pixel_count": 50, "pixel_count": 50}
    (half,) = observation_per_unit([box(30, 0, 70, 100)], fset)
    assert half == {"observed_fraction": 0.5, "valid_pixel_count": 20, "pixel_count": 40}


@pytest.fixture(scope="module")
def half_dark():
    return S.run(producer=AllVegLeftHalfUnobserved())


def test_every_served_ward_carries_its_coverage_fields(half_dark):
    result, units = half_dark
    ctx = ward_context(result)
    fracs = set()
    for t, b in units.items():
        for u in b["units"]:
            m = materialize(u, t, ctx)
            ob = m["outputs"]["observability"]
            assert set(ob) == {"observed_fraction", "valid_pixel_count"}
            assert ob["valid_pixel_count"]["value"] <= ob["valid_pixel_count"]["pixel_count"]
            fracs.add(ob["observed_fraction"]["value"])
    assert 0.0 in fracs and 1.0 in fracs and any(0 < f < 1 for f in fracs)


def test_fully_dark_ward_reports_absence_not_zero(half_dark):
    result, units = half_dark
    ctx = ward_context(result)
    dark = [u for u in units["grid"]["units"] if u["observation"]["observed_fraction"] == 0.0]
    assert dark
    m = materialize(dark[0], "grid", ctx)
    veg = m["outputs"]["fractions"]["vegetation"]
    assert veg["value"] is None and veg["status"] == "insufficient_observation"
    assert m["outputs"]["observability"]["valid_pixel_count"]["value"] == 0


def test_half_observed_ward_value_is_over_its_observed_part(half_dark):
    """C25: a 50%-unknown ward once reported 50 where known-pixel truth was
    100. Vegetation is 1 everywhere here, so any observed part reads 1.0."""
    result, units = half_dark
    ctx = ward_context(result)
    part = [u for u in units["grid"]["units"]
            if 0.5 <= u["observation"]["observed_fraction"] < 1.0]
    assert part
    for u in part:
        veg = materialize(u, "grid", ctx)["outputs"]["fractions"]["vegetation"]
        assert veg["status"] == "available" and abs(veg["value"] - 1.0) < 1e-6
