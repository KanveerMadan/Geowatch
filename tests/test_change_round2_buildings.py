from experiments.change_round2 import buildings as b


def test_half_observed_blocks_and_uncertain_reference_abstain():
    assert [b.weak_target(v) for v in [None,0,16,96,112]]==[None,False,None,None,True]
    assert b.vector({"radar":[0,1],"optical":None,"ghsl":.1},"combined") is None
    assert b.vector({"radar":[0,1],"optical":None,"ghsl":.1},"radar")==[.1,0,1]


def test_disjoint_tracks_are_unusable():
    def row(day,track):return dict(source="radar",track=track,day=day,VV=-7,VH=-13,texture=2.)
    a=[row("2020-01-01","A"),row("2020-01-13","A")]
    new=[row("2021-01-01","B"),row("2021-01-13","B")]
    assert b.sensor_features(a,new)["radar"] is None
    matched=[{**r,"track":"A"} for r in new]
    assert b.sensor_features(a,matched)["radar"]==[-7.,-13.,2.,-7.,-13.,2.,0.,0.,0.]


def test_branch_selection_and_comparable_silence_baseline():
    sample=[dict(ghsl=.2,radar=[float(i)],optical=None,gain=i>=10,loss=None) for i in range(20)]
    classifiers=b.fit(sample)
    result=b.classify(sample[-1],classifiers)
    assert result["gain_mode"]=="radar" and result["gain_score"]>.5
    assert result["loss"] is None
    counts=b.metrics([{**r,"gain_score":None if i==0 else float(i>=10)} for i,r in enumerate(sample)],"gain",True)
    assert counts["observed"]==19 and counts["fn_observed"]==10 and counts["tp"]==0


def test_portable_bundle_uses_only_development_rows_and_reproduces_models():
    import gzip
    import json
    import numpy as np

    rows=json.loads(gzip.decompress(b.DATASET.read_bytes()))
    bundle=b.read(b.BUNDLE)
    assert bundle["development_sha256"]==b.sha256(b.DATASET.read_bytes()).hexdigest()
    assert set(bundle["sites"])=={r["site"] for r in rows}==set(b.seen_sites())
    with b.threadpool_limits(limits=1):
        trained=b.fit(rows)
    for mode,targets in trained.items():
        for target,model in targets.items():
            saved=bundle["models"][mode][target]
            if model is None:
                assert saved is None
            else:
                np.testing.assert_allclose(saved["coef"],model["coef"],rtol=1e-7,atol=1e-9)
                np.testing.assert_allclose(saved["mean"],model["mean"],rtol=1e-9)
                assert saved["negative"]==model["negative"] and saved["positive"]==model["positive"]


def test_map_output_preserves_unknown_and_block_geometry(monkeypatch,tmp_path):
    artifact=tmp_path/"model.json"
    artifact.write_text("{}")
    monkeypatch.setattr(b,"BUNDLE",artifact)
    unknown={"gain":None,"loss":False,"gain_score":None,"loss_score":.1,
             "gain_mode":None,"loss_mode":"radar","mode":"target_specific"}
    monkeypatch.setattr(b,"classify_blocks",lambda ee,crs,cells,before,after:[unknown]*len(cells))
    mapped=b.map_site(None,88.463,22.545,"2019-06-30","2020-06-30")
    assert len({f["id"] for f in mapped["features"]})==49
    assert all(f["properties"]["gain"] is None and f["geometry"]["type"]=="Polygon" for f in mapped["features"])
