"""Phase 2, task 1: the end-to-end analysis pipeline, offline on a synthetic
layer. AOI -> layer -> coverage -> fractions -> susceptibility -> change ->
aggregation -> result, with no 7-class classifier anywhere."""
import ast
import glob
import sys

import numpy as np
import pytest

from analysis import contract as C
from analysis.fractions import StandInFractions
from analysis.run import change_epochs, resolve_window
from analysis.wards import materialize, ward_context
from tests import analysis_synth as S


@pytest.fixture(scope="module")
def run():
    return S.run()


def test_whole_result_follows_the_contract(run):
    result, _ = run
    n = C.check_result(result)
    assert n >= 20
    assert result["schema"] == "geowatch.analysis/1"
    assert result["seven_class_classifier"] is False


def test_chain_order_is_all_present(run):
    result, _ = run
    o = result["outputs"]
    assert set(o) == {"fractions", "observability", "estimate_quality", "osm_coverage",
                      "susceptibility", "change", "aggregation"}
    assert set(o["susceptibility"]) == {"pluvial", "fluvial", "coastal", "flash_flood",
                                        "waterlogging"}


def test_fraction_labels_and_not_computed(run):
    f = run[0]["outputs"]["fractions"]
    assert f["built"]["validation_status"] == "experimental" and f["built"]["value"] > 0
    for g in ("vegetation", "water"):
        assert f[g]["validation_status"] == "placeholder" and f[g]["status"] == "available"
    for g in ("impervious_total", "paved", "bare"):
        assert f[g]["value"] is None and f[g]["status"] == "not_computed"
        assert f[g]["validation_status"] == "placeholder"


def test_vegetation_observed_fraction_reflects_the_unobserved_corner(run):
    veg = run[0]["outputs"]["fractions"]["vegetation"]
    assert 0.8 < veg["coverage"]["observed_fraction"] < 1.0


def test_pluvial_and_waterlogging_are_failed(run):
    s = run[0]["outputs"]["susceptibility"]
    assert s["pluvial"]["validation_status"] == "failed"
    assert s["waterlogging"]["validation_status"] == "failed"
    assert s["fluvial"]["validation_status"] == "failed"
    assert s["flash_flood"]["validation_status"] == "failed"
    assert s["coastal"]["validation_status"] == "experimental"
    assert s["pluvial"]["spatial"] is True and s["pluvial"]["tier"] is not None


def test_change_names_its_fraction_and_leaves_item21_fractions_absent(run):
    ch = run[0]["outputs"]["change"]
    assert set(ch["vegetation"]["value"]) == {"increase", "decrease", "no_detectable_change"}
    for g in ("impervious_total", "paved", "bare"):
        assert ch[g]["status"] == "not_computed"


def test_every_ward_unit_materializes_to_the_contract(run):
    result, units = run
    ctx = ward_context(result)
    assert {"grid", "footprint", "path"} <= set(units)
    for t, b in units.items():
        assert b["units"], t
        for u in b["units"]:
            m = materialize(u, t, ctx)
            assert m["outputs"]["susceptibility"]["pluvial"]["validation_status"] == "failed"


def test_aggregation_reports_each_unit_type(run):
    agg = run[0]["outputs"]["aggregation"]
    assert set(agg) == {"grid", "footprint", "path"}
    assert all(a["value"] > 0 for a in agg.values())


def test_producer_is_swappable_and_enters_the_version():
    """An item-21-like producer computes impervious_total; nothing else changes."""
    class Item21Like(S.SynthProducer):
        name = "item21_like"
        FRACTIONS = ("built", "vegetation", "water", "impervious_total")
        NOT_COMPUTED = {"paved": "x", "bare": "x"}

        def labels(self):
            return {**super().labels(), "impervious_total": "experimental"}

        def sources(self, layer, window):
            return {**super().sources(layer, window), "impervious_total": ["regressor"]}

        def produce(self, layer, transform, shape, window):
            fs = super().produce(layer, transform, shape, window)
            fs["rasters"]["impervious_total"] = np.full(shape, 0.7, dtype=np.float32)
            fs["observed"]["impervious_total"] = np.ones(shape, dtype=bool)
            return fs

    base, _ = S.run()
    r, units = S.run(producer=Item21Like())
    imp = r["outputs"]["fractions"]["impervious_total"]
    assert imp["status"] == "available" and abs(imp["value"] - 0.7) < 1e-6
    assert r["model_version"]["version_id"] != base["model_version"]["version_id"]
    assert "impervious_total" in units["grid"]["units"][0]
    C.check_result(r)


def test_no_seven_class_classifier_is_reachable():
    """Static: nothing under analysis/ imports the retired pipeline or model."""
    banned = {"pipeline", "ingestion.inference", "ingestion.resnet_model",
              "ingestion.segmentation", "perception.hydrological_surfaces", "torch"}
    for path in glob.glob("analysis/*.py"):
        tree = ast.parse(open(path).read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert n not in banned, f"{path} imports {n}"


def test_a_run_imports_no_classifier_module():
    """In a fresh interpreter, so this process's module table is untouched
    (popping `pipeline` here broke every test holding a reference to it)."""
    import subprocess
    code = ("import sys; from tests import analysis_synth as S; S.run(); "
            "bad = [m for m in ('pipeline', 'ingestion.inference', 'ingestion.resnet_model', "
            "'torch') if m in sys.modules]; print('BAD', bad); sys.exit(1 if bad else 0)")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]


def test_window_resolution():
    from datetime import date
    assert resolve_window("2026-01-01", "2026-03-31")["mode"] == "manual"
    auto = resolve_window(None, None, today=date(2026, 10, 28))
    assert auto == {"start": "2026-07-29", "end": "2026-10-27", "mode": "latest_auto"}
    with pytest.raises(ValueError):
        resolve_window("2026-01-01", None)
    with pytest.raises(ValueError):
        resolve_window("2026-03-01", "2026-01-01")


def test_change_epochs():
    e = change_epochs({"start": "2026-01-01", "end": "2026-03-31"})
    assert e["s2"] == (("2021-01-01", "2021-03-31"), ("2026-01-01", "2026-03-31"))
    assert e["built"] == (2021, 2023) and e["built_noise"] == (2022, 2023)
    assert change_epochs({"start": "2014-01-01", "end": "2016-03-31"})["built"] is None
