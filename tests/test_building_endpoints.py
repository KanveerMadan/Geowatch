"""The endpoint benchmark keeps survey inputs out of features and holds out entire sites."""
from pathlib import Path
import json

import numpy as np
import pytest

from experiments.change_history import building_endpoints as bench


def test_registered_training_and_test_areas_are_disjoint():
    sites = json.loads(bench.SPLITS.read_text())
    assert [s["split"] for s in sites] == ["development"] * 3 + ["heldout"] * 2
    geod = bench.Geod(ellps="WGS84")
    for i, site in enumerate(sites):
        for other in sites[:i]:
            assert geod.inv(*site["centre"], *other["centre"])[2] >= 300_000
        a, b = sorted(site["epochs"])
        assert int(b[:4]) - int(a[:4]) == 1 and a[5:] == b[5:]
        assert sum(f["bytes"] for v in site["epochs"].values() for f in v.values()) <= 12 * bench.MIB


def _fixture(root, name, values, keep, feature):
    ids = [f"grid/100/{i}" for i in range(len(keep))]
    np.savez(root / (name + "-survey.npz"), ids=ids, y=np.array(values, dtype=float), keep=keep)
    np.savez(root / (name + "-s2.npz"), ids=ids, x=np.array(feature, dtype=float)[:, None])


def test_missing_support_is_excluded_and_heldout_labels_cannot_train_baselines(tmp_path):
    sites = [{"site":"dev_a","split":"development"},{"site":"dev_b","split":"development"},
             {"site":"held","split":"heldout"}]
    _fixture(tmp_path,"dev_a",[[10,1]]*3,[True]*3,[0,1,2])
    _fixture(tmp_path,"dev_b",[[20,2]]*3,[True]*3,[3,4,5])
    _fixture(tmp_path,"held",[[100,30],[9999,9999],[8888,8888]], [True,False,True],[1,2,np.nan])
    result = bench.evaluate(tmp_path, sites, "s2")
    assert result["coverage"]["held"] == {"grid":3,"survey":2,"joint":1}
    assert result["by_site"]["held"]["gain"]["median"]["mae"] == pytest.approx(85.0)
    assert result["by_site"]["held"]["loss"]["zero"]["mae"] == pytest.approx(30.0)
    (tmp_path/"dev_b-s2.npz").unlink()
    assert bench.evaluate(tmp_path, sites, "s2")["status"] == "insufficient_geographic_support"
