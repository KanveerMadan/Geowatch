"""
Decision 2026-10-28 (08_STATE.md): the Part 4 "no build past item 21" mandate
is overridden, and every output is labelled validated / experimental /
placeholder. Nothing in the vector track has been validated, so nothing may
claim "validated"; index-threshold stand-ins and not-computed fractions are
placeholders.

Run from the repo root:  pytest tests/test_vector_validation_labels.py
"""
import numpy as np

from vector import access, change, coverage, density, fractions, roads, units
from vector_synth import _fix_ns, _layer, _rows_of_huts, _way

REF = {"a": 0.19, "b": 2.0, "c": 8.35}


def _layer9():
    ways = [_fix_ns(_way(100 + k, "footway", 0, 0, 0, [1000 + 3 * k, 1001 + 3 * k, 1002 + 3 * k]))
            for k in range(9)]
    return _layer(ways, footprints=_rows_of_huts())


def test_every_vector_product_carries_a_label_and_none_claims_validated():
    layer = _layer9()
    outs = [layer.lengths_km(), layer.surface_coverage(), coverage.score_layer(layer, REF),
            density.density_metrics(layer, REF), access.access_indicators(layer, REF)]
    for o in outs:
        assert o["validation_status"] in roads.VALIDATION_LABELS
        assert o["validation_status"] != "validated"


def test_proxies_and_not_computed_are_placeholders():
    s = fractions.FRACTION_VALIDATION_STATUS
    assert s["vegetation"] == s["water"] == s["impervious_total"] == "placeholder"
    assert s["built"] == "experimental"
    assert all(v["validation_status"] == "placeholder" for v in change.not_computed_block().values())


def test_units_report_per_fraction_labels():
    layer = _layer9()
    tr, shape = fractions.grid_for(layer)
    fr = {"rasters": {f: np.zeros(shape, np.float32) for f in fractions.FRACTIONS},
          "observed": {f: np.ones(shape, bool) for f in fractions.FRACTIONS},
          "transform": tr, "shape": shape, "method": {}, "producer": {}}
    out = units.build_units(layer, fr, {"coverage_regime_flag": "adequate"})
    assert out["validation_status"] == "experimental"
    assert out["fraction_validation_status"]["vegetation"] == "placeholder"


def test_an_output_cannot_be_relabelled_validated_by_default():
    assert roads.VALIDATION_DEFAULT == "experimental"
