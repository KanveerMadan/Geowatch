"""Flood round 4, step 0: the eleven flood types (docs/flood_taxonomy.md).
Every type has an output with a label under outputs.susceptibility, even
when nothing computes it."""
from analysis import contract as C
from analysis import hazards as H

MV = C.model_version({"producer": "abc"}, commit={"commit": "deadbeef", "dirty": False,
                                                  "diff_sha256": None})


def test_taxonomy_has_eleven_types_and_maps_every_module():
    assert list(C.FLOOD_TAXONOMY) == [f"M{i}" for i in range(1, 12)]
    modules = [t["module"] for t in C.FLOOD_TAXONOMY.values()]
    assert len(set(modules)) == 11
    assert set(modules) == set(H.HAZARDS) | set(C.UNBUILT_FLOOD_TYPES)
    assert not set(H.HAZARDS) & set(C.UNBUILT_FLOOD_TYPES)


def test_unbuilt_types_are_labelled_absent_outputs():
    out = H.unbuilt_outputs(MV)
    assert set(out) == set(C.UNBUILT_FLOOD_TYPES)
    for m, o in out.items():
        C.check_output(o, where=m, version_id=MV["version_id"])
        assert o["value"] is None and o["validation_status"] == "placeholder"
        assert o["flood_type"] in C.FLOOD_TAXONOMY
    assert out["tsunami"]["status"] == "not_applicable"
    assert out["groundwater"]["status"] == "not_computed"
    assert "not measurable" in out["groundwater"]["reason"]


def test_hazard_outputs_carry_all_eleven_types():
    mod = {"status": "insufficient_evidence", "validation_status": "experimental",
           "aoi_mean_score": None, "reason": "no input"}
    hz = H.hazard_outputs({h: dict(mod) for h in H.HAZARDS}, MV, {}, has_waterways=False)
    assert set(hz) == {t["module"] for t in C.FLOOD_TAXONOMY.values()}
    n = C.check_result({"model_version": MV, "outputs": {"susceptibility": hz}})
    assert n == 11
