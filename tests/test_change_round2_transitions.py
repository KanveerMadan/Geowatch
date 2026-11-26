from experiments.change_round2.forest import forest
from experiments.change_round2.water import water


def radar(day,vv,vh,track="A/ASCENDING/95"):
    return dict(day=day,VV=vv,VH=vh,texture=2.,track=track,source="radar")


def test_radar_water_confirmation_requires_matched_support_and_uses_no_later_data():
    rows=[radar(d,-9,-15) for d in ("2022-05-01","2022-05-13","2022-05-25")]
    rows += [radar("2022-06-06",-16,-23),radar("2022-06-07",-16,-23,"B/DESCENDING/88"),
             radar("2022-06-18",-17,-24)]
    assert water(rows,"2022-06-01","2022-06-18",0)["gain"] == []
    assert water(rows,"2022-06-01","2022-06-19",0)["gain"] == ["2022-06-18"]
    assert not water(rows,"2022-06-01","2022-06-19",.95)["gain"]
    assert not water(rows,"2022-06-01","2022-06-19",None)["observed"]


def test_forest_classification_requires_prior_forest_and_persistent_observed_change():
    rows=[radar("2021-06-"+s,-9,-14) for s in ("01","05","10","15","20")]
    rows += [radar("2022-06-"+s,-12,-18) for s in ("01","05","10","15")]
    confirmed=forest(rows,"2022-06-01","2022-06-16",.9)["confirmed"]
    assert [v["day"] for v in confirmed] == ["2022-06-15"]
    assert not forest(rows,"2022-06-01","2022-06-15",.9)["confirmed"]
    assert not forest(rows,"2022-06-01","2022-06-16",None)["observed_sources"]
    assert forest(rows,"2022-06-01","2022-06-16",.1)["domain"] == "outside_prior_forest"


def test_water_observability_requires_a_usable_confirmation_pair():
    history=[radar(d,-9,-15,t) for t in ("track1","track2") for d in
             ("2022-05-01","2022-05-13","2022-05-25")]
    june=[radar("2022-06-01",-9,-15,"track1"),radar("2022-06-02",-9,-15,"track2")]
    assert not water(history+june,"2022-06-01","2022-07-01",0)["observed"]
    late=radar("2022-06-29",-9,-15,"track1")
    assert not water(history+june+[late],"2022-06-01","2022-07-01",0)["observed"]
    optical=[dict(day=d,source="optical",track="o",water=-.4) for d in
             ("2022-05-01","2022-05-13","2022-05-25","2022-06-01")]
    assert set(water(history+june[:1]+optical,"2022-06-01","2022-07-01",0)["observed_targets"])=={"gain","loss"}
