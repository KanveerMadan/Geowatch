from datetime import datetime, timezone
from pathlib import Path

import pytest

from experiments.change_round2 import monitor, monitor_review
from experiments.change_round2.monitor_lock import ee_lock


def cell(c, *, flags=None, observed=True):
    return {"id":str(c),"water":{"gain":flags or [],"loss":[],"observed_targets":["gain","loss"] if observed else [],"observed":observed,"candidates":[]},
            "forest":{"confirmed":[],"observed_sources":[],"candidates":[]}}


def test_monitor_cutoff_month_boundary_and_utc():
    first, cutoff, end=monitor.period(datetime(2024,3,1,0,0,tzinfo=timezone.utc))
    assert list(map(str,(first,cutoff,end)))==["2024-02-01","2024-02-29","2024-03-01"]


def test_panel_masked_receipts_keep_gaps_distinct_and_pick_both_strata():
    snap=dict(method="v1",site="site",period=["2025-01-01","2025-01-15"],cutoff="2025-01-14",
              received="2025-01-15",cells=[cell(1,flags=["2025-01-03"]),cell(2),cell(3,observed=False)])
    s=monitor.summary([snap])["total"]
    assert s["unjudged_quiet_cells"]==1 and s["confirmed_cells"]==1
    cases=monitor_review.select([snap])
    assert {(c["stratum"],c["cell"]) for c in cases}=={("quiet","2"),("confirmed","1")}
    evidence={c["id"]:{"usable":{"prior":["X_20241220"],"during":["X_20250105","X_20250106"]}} for c in cases}
    labels=dict(reviewer="independent",prediction_blind=True,cases={
        c["id"]:{"water":"stable","vegetation":"unknown","reason":"water stable at three visible dates"} for c in cases})
    report=monitor_review.assess(cases,labels,evidence)
    assert report["sample_counts"]["water_gain"]=={"fp":1,"tn":1}
    assert report["always_silent_comparison"]["water_gain"]=={"tn":2}
    evidence[cases[0]["id"]]["usable"]["during"]=["X_20250105","Y_20250105"]
    with pytest.raises(ValueError,match="insufficient dates"):
        monitor_review.assess(cases,labels,evidence)


def test_review_cannot_be_replaced_after_join(tmp_path):
    path=tmp_path/"sealed.json"
    monitor_review.seal(path,{"case":"gain"})
    monitor_review.seal(path,{"case":"gain"})
    with pytest.raises(ValueError):
        monitor_review.seal(path,{"case":"loss"})


def test_serial_lock_is_reentrant_and_releases_on_exception(tmp_path):
    import fcntl
    path=tmp_path/"lock"
    with pytest.raises(RuntimeError):
        with ee_lock(path), ee_lock(path):
            with path.open("a") as other:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(other,fcntl.LOCK_EX | fcntl.LOCK_NB)
            raise RuntimeError()
    with path.open("a") as other:
        fcntl.flock(other,fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_receipts_preserve_late_arriving_evidence_without_counting_repeats(tmp_path):
    raw=cell(1,flags=["2025-01-03"])
    raw["water"]["candidates"]=[{"day":"2025-01-02","source":"radar","track":"a","target":"gain"}]
    r={"method":"v1","site":"x","cells":[raw],"cutoff":"2025-01-14","received":"2025-01-15"}
    from experiments.change_round2 import data
    initial_cache=data.CACHE
    try:
        with monitor.setup(tmp_path) as db:
            assert monitor.record(db,r)["new_evidence"]=={"candidate":1,"confirmation":1}
            raw["water"]["candidates"].append({"day":"2025-01-04","source":"optical","track":"b","target":"gain"})
            prior=monitor.record(db,r)
            assert len(prior["cells"][0]["water"]["candidates"])==1
            second=monitor.record(db,{**r,"cutoff":"2025-01-15","received":"2025-01-16"})
            assert second["new_evidence"]=={"candidate":1,"confirmation":0}
            assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]==3
    finally:
        data.CACHE=initial_cache


def test_unobserved_quiet_never_counts_as_a_correct_negative():
    snap=dict(method="v1",site="x",period=["2025-01-01","2025-01-15"],
              cutoff="2025-01-14",cells=[cell(0,observed=False)])
    cases=monitor_review.select([snap]); key=cases[0]["id"]
    reviewed={"reviewer":"blind","prediction_blind":True,
              "cases":{key:{"water":"gain","vegetation":"stable","reason":"Water increased, green canopy stable."}}}
    evidence={key:{"usable":{"prior":["X_20241220"],"during":["X_20250105","Y_20250115"]}}}
    r=monitor_review.assess(cases,reviewed,evidence)
    assert r["sample_counts"]["water_gain"]=={"abstained_reference_positive":1}
    assert r["sample_counts"]["water_loss"]=={"abstained_reference_negative":1}
    assert r["recall_including_abstentions"]["water_gain"]==0
    assert r["silent_on_judged_subset"]["water_loss"]=={}


def test_carry_needs_same_physical_scene_and_pixels(tmp_path, monkeypatch):
    from PIL import Image
    from experiments.change_round2 import data
    first, second, cutoff="a"*64,"b"*64,"2025-01-14"
    monkeypatch.setattr(monitor_review, "fingerprint", lambda: second)
    case=dict(site="city",cell="1",start="2025-01-01",end="2025-01-15")
    evidence={"usable":{"prior":["X_20241220"],"during":["X_20250105"]},"inventory":["scene"]}
    verdict={"water":"unknown","vegetation":"unknown","reason":"Indistinct boundaries."}
    for method,ident in [(first,"old"),(second,"new")]:
        path=tmp_path/"review"/method/cutoff
        (path/"data").mkdir(parents=True)
        (path/"blind").mkdir()
        data.save(path/"data/selection.json",[{**case,"id":ident}])
        data.save(path/"data"/(ident+".json"),evidence)
        strip=Image.new("RGB",(100,100),"green")
        strip.putpixel((1,1),(255,0,0) if ident=="old" else (0,0,255))
        strip.save(path/"blind"/(ident+".png"))
        if ident=="old":
            monitor_review.seal(path/"sealed_labels.json",dict(reviewer="blind",cases={ident:verdict}))
    result=monitor_review.carry_forward(tmp_path,cutoff,first)
    assert result["cases"]=={"new":verdict}
    assert result["carried_ids"]==["new"]
    png=tmp_path/"review"/second/cutoff/"blind/new.png"
    with Image.open(png) as current:
        strip=current.copy()
    strip.putpixel((1,24),(0,0,255))
    strip.save(png)
    assert not monitor_review.carry_forward(tmp_path,cutoff,first)["cases"]
