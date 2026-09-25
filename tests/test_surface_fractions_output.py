"""Item 21 Phase A — output contract: every fraction has provenance, the
placeholder banner cannot be off while a fraction is tainted, and coverage
fields can never be mistaken for a fraction."""
import json
import pathlib
import sys

import numpy as np
import pytest
import rasterio

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from surface_fractions import output
from surface_fractions.bookkeeping import EIGHT
from surface_fractions.grid import Grid


def rec(prov="footprints", tainted=False):
    return {"status": "computed", "provenance": prov, "placeholder_inputs": [],
            "placeholder_tainted": tainted, "aoi_mean_known_pixels": 0.1}


def result(**over):
    r = {"banner": {"contains_placeholder": False},
         "fractions": {n: rec() for n in EIGHT},
         "derived": {"impervious_total": rec("regression")},
         "observability": {"observed_fraction": 1.0},
         "estimate_quality": {}, "flags": {}}
    r.update(over)
    return r


def test_valid_result_writes(tmp_path):
    path = output.write_result(result(), str(tmp_path))
    assert json.load(open(path))["fractions"]["built"]["provenance"] == "footprints"


def test_missing_provenance_refused(tmp_path):
    r = result()
    r["fractions"]["paved"]["provenance"] = None
    with pytest.raises(output.OutputContractError, match="paved"):
        output.write_result(r, str(tmp_path))


def test_tainted_fraction_with_banner_off_refused(tmp_path):
    r = result()
    r["fractions"]["vegetation"] = rec("placeholder", tainted=True)
    with pytest.raises(output.OutputContractError, match="banner"):
        output.write_result(r, str(tmp_path))


def test_ninth_fraction_refused(tmp_path):
    r = result()
    r["fractions"]["shadow"] = rec()
    with pytest.raises(output.OutputContractError):
        output.write_result(r, str(tmp_path))


def test_observability_cannot_reuse_a_fraction_name(tmp_path):
    with pytest.raises(output.OutputContractError, match="observability"):
        output.write_result(result(observability={"water": 0.3}), str(tmp_path))


def test_arrays_never_go_into_json(tmp_path):
    with pytest.raises(output.OutputContractError, match="raster"):
        output.write_result(result(flags={"x": np.zeros(2)}), str(tmp_path))


def test_raster_skips_none_layers_and_names_bands(tmp_path):
    g = Grid("EPSG:32643", (10.0, 0.0, 0.0, 0.0, -10.0, 20.0), 3, 2)
    path, written, skipped = output.write_raster(
        {"built": np.ones((2, 3)), "snow_ice": None}, g, str(tmp_path))
    assert written == ["built"] and skipped == ["snow_ice"]
    with rasterio.open(path) as src:
        assert src.descriptions == ("built",) and src.count == 1
        assert tuple(src.transform)[:6] == g.transform


def test_tainted_fraction_must_say_placeholder_in_provenance(tmp_path):
    r = result(banner={"contains_placeholder": True})
    r["fractions"]["bare"] = rec("residual", tainted=True)
    with pytest.raises(output.OutputContractError, match="does not say so"):
        output.write_result(r, str(tmp_path))
    r["fractions"]["bare"] = rec("placeholder:residual", tainted=True)
    output.write_result(r, str(tmp_path))
