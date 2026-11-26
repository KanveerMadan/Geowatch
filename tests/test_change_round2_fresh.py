import numpy as np

from experiments.change_round2 import fresh


def test_selection_uses_southwest_grid_and_abstains_on_unknown_cells():
    arr=np.array([[0,1,0],[3,0,4]])
    rows=fresh.choose(arr,"x",100,1000,fresh.WATER_CLASSES,{"cap_per_direction":10,"minimum_separation_m":500})
    assert rows==[{"xy":[200,900],"label":"gain"},{"xy":[100,800],"label":"stable_dry"},{"xy":[300,800],"label":"stable_wet"}]


def test_scoring_keeps_unobservable_in_recall_and_preserves_unreviewed():
    result=fresh.metrics([{"positive":p,"call":c} for p,c in
                          [(True,None),(True,True),(False,None),(False,True),(None,True),(False,False)]])
    assert result["recall_all"]==.5
    assert result["recall_observed"]==1
    assert result["stable_false_alarm_fraction_observed"]==.5
    assert result["unknown_reference"]==1
    assert result["baseline_no_change"]["tn_on_observed"]==2


def test_undefined_holdout_metrics_remain_unknown():
    result=fresh.metrics([])
    assert result["recall_all"] is None and result["sample_precision"] is None
    assert not result["ranking"]


def test_fresh_run_cannot_open_reference_when_github_sha_differs(monkeypatch):
    checks=[]
    monkeypatch.setattr(fresh.data,"read",lambda p:{"sha256":{}})
    monkeypatch.setattr(fresh,"sealed_files",lambda:{})
    def git(*args):
        checks.append(args[0])
        return "0"*40 if args[0]=="rev-parse" else "1"*40+" refs/heads/codex/change-history"
    monkeypatch.setattr(fresh,"git",git)
    monkeypatch.setattr(fresh.data,"connect",lambda: (_ for _ in ()).throw(AssertionError("EE opened")))
    import pytest
    with pytest.raises(ValueError,match="live origin"):
        fresh.evaluate("0"*40)
    assert checks==["rev-parse","ls-remote"]


def test_class_specific_scores_separate_gain_and_loss_and_skip_ambiguous():
    r=fresh.metrics([{"positive":True,"call":True,"score":.8},{"positive":False,"call":False,"score":.41},
                     {"positive":None,"call":True,"score":.99}])
    assert r["ranking"]["auc"]==1.0
    assert r["ranking"]["constant_average_precision"]==.5
    assert r["baseline_no_change"]["sample_precision"] is None
