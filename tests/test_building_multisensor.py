import json

import numpy as np
import pytest
from pyproj import Geod

from experiments.change_history import building_multisensor as experiment
from experiments.change_history import building_multisensor_recent as recent


def test_study_lock_and_geographic_holdout():
    experiment.verify_lock()
    sites = json.loads(experiment.MANIFEST.read_text())
    dev = [s for s in sites if s["split"] == "development"]
    test = [s for s in sites if s["split"] == "test"]
    assert (len(dev),len(test)) == (7,4)
    geod = Geod(ellps="WGS84")
    assert all(geod.inv(*a["centre"],*b["centre"])[2] > 300_000 for a in dev for b in test)
    assert all(len(s["epochs"])==2 for s in sites)
    assert all(set(ep)=={"tracked","image","unusable"} for s in sites for ep in s["epochs"].values())


def test_whole_block_support_and_missing_sensor(tmp_path):
    ids = [f"EPSG:32610/{x}/{y}" for x,y in [(0,200),(100,200),(0,100),(100,100),(200,200)]]
    data = np.arange(5,dtype=float)[:,None]
    experiment.save_arrays(tmp_path/"s-sentinel1.npz",x=data,ids=ids)
    cloud = data.copy()
    cloud[2,0] = np.nan
    experiment.save_arrays(tmp_path/"s-sentinel2.npz",x=cloud,ids=ids)
    experiment.save_arrays(tmp_path/"s-targets.npz",ids=ids,keep=[1,1,1,1,1],y=np.array([[0,0],[12,0],[0,5],[3,0],[100,100]]))
    row = experiment.block_inputs(tmp_path,"s",with_labels=True)
    assert row["ids"]==["EPSG:32610/0/0"]
    assert row["keep"].tolist()==[True]
    assert row["y"].tolist()==[[15,5]]
    assert row["x"]["radar"][0,0]==1.5
    assert np.isnan(row["x"]["combined"]).any()


def test_grid_disagreement_is_rejected(tmp_path):
    for source,ids in (("sentinel1",["foo"]),("sentinel2",["bar"])):
        experiment.save_arrays(tmp_path/f"s-{source}.npz",x=[[0]],ids=ids)
    with pytest.raises(ValueError,match="grids differ"):
        experiment.block_inputs(tmp_path,"s",with_labels=False)


def test_common_denominator_and_supported_zero():
    row = {"y":np.array([[0,0],[5,10],[100,8]]),"keep":np.array([True,True,False])}
    preds = {"radar":np.array([[1,0],[5,10],[0,0]],dtype=float),
             "optical":np.array([[0,0],[np.nan,np.nan],[0,0]])}
    report = experiment.score(row,preds)
    assert report["mapped_added"]==1 and report["stable"]==1
    assert report["available"]["radar"]["zero"]["gain"]["mae_m2"]==2.5
    assert report["common"]["zero"]["gain"]["mae_m2"]==0
    assert report["common"]["radar"]["blocks"]==1


def test_fire_inspection_controls_exclude_unknown_and_partial():
    ids = ["destroyed","undamaged","partially damaged","uninspected"]
    groups = {ids[0]:{"Destroyed (>50%)":1,"No Damage":1},ids[1]:{"No Damage":3},ids[2]:{"Minor (10-25%)":1}}
    ranked = np.array([[0,10],[0,0],[0,12],[0,20]],dtype=float)
    result = recent.score({"radar":ranked}, ids, groups)
    assert result["destroyed_positive_blocks"]==result["assessed_undamaged_blocks"]==1
    assert result["common_block_scores"]["radar"]["auc"]==1
    assert result["common_block_scores"]["zero"]["auc"]==0.5


def test_metrics_insufficient_strata_are_unknown():
    pred = {"radar":np.array([[0,1],[np.nan,np.nan]])}
    result = recent.score(pred,["p","n"],{"p":{"Destroyed (>50%)":1},"n":{"No Damage":1}})
    assert result["common_block_scores"]["radar"]["auc"] is None
    assert experiment.metrics(np.zeros((2,2)), np.zeros((2,2)),np.array([False,False])) is None


def test_published_training_bundle_has_only_development_areas():
    from experiments.change_history.building_multisensor_apply import development
    rows = development()
    assert len(rows)==7
    for row in rows:
        np.testing.assert_allclose(row["x"]["combined"], np.hstack([row["x"]["optical"],row["x"]["radar"]]), equal_nan=True)
        assert row["x"]["radar"].shape[0] == len(row["y"]) == len(row["keep"])


def test_training_bundle_rejects_changed_bytes(tmp_path):
    from experiments.change_history.building_multisensor_apply import development
    other = tmp_path/"bundle.gz"
    other.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="differ"):
        development(other)


def test_recent_dutch_review_matches_projection_and_reference_support():
    from experiments.change_history import building_multisensor_dutch as dutch
    for centre in dutch.SITES.values():
        _,_,block_ids = dutch.fixed_grid(centre)
        cells,_ = experiment.old._grid(experiment.old._layer(centre))
        reporting = experiment.group_blocks([c["cell_id"] for c in cells])
        assert len(set(block_ids.values()))==16
        assert set(block_ids.values()) <= set(reporting)


def test_dutch_score_abstains_under_missing_optical():
    from experiments.change_history.building_multisensor_dutch import metric
    score=metric(np.array([True,False]),np.array([2.,np.nan]))
    assert score["positive"]==1 and score["covered_blocks"]==1 and score["auc"] is None


def test_all_blind_aerial_labels_bound_to_source_and_protocol():
    from experiments.change_history import building_multisensor_dutch as dutch
    labels = dutch.read_labels(dutch.LABELS)
    seal = json.loads(dutch.SEAL.read_text())
    assert len(labels)==48
    assert seal["labels_sha256"] == experiment.digest(dutch.LABELS)
    assert seal["protocol_lock_sha256"] == experiment.digest(dutch.LOCK)
    assert set(seal["reference_sha256"]) == {f"{s}-{y}.jpg" for s in dutch.SITES for y in dutch.YEARS}
    for name, expected in json.loads(dutch.LOCK.read_text()).items():
        assert experiment.digest(experiment.ROOT/name)==expected
