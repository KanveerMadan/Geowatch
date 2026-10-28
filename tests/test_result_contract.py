"""Phase 2: the result contract (analysis/contract.py) -- label precedence,
model_version, and enforcement across a whole result."""
import copy

import numpy as np
import pytest

from analysis import contract as C


MV = C.model_version({"producer": "abc"}, commit={"commit": "deadbeef", "dirty": False,
                                                  "diff_sha256": None})


def _out(value=0.5, **kw):
    args = dict(validation_status="experimental", coverage=C.coverage(1.0, "aoi"),
                data_sources=["src"], model_version=MV)
    args.update(kw)
    return C.output(value, **args)


def _result(outputs):
    return {"model_version": MV, "outputs": outputs}


# ── precedence: failed > placeholder > experimental > validated ──

def test_precedence_is_failed_placeholder_experimental_validated():
    assert C.VALIDATION_PRECEDENCE == ("retired", "failed", "placeholder", "experimental",
                                       "validated")
    assert C.worst("validated", "experimental") == "experimental"
    assert C.worst("experimental", "placeholder") == "placeholder"
    assert C.worst("placeholder", "failed") == "failed"
    assert C.worst("failed", "placeholder", "experimental", "validated") == "failed"
    assert C.worst("failed", "retired") == "retired"


def test_unknown_label_is_refused():
    with pytest.raises(C.ContractError):
        C.worst("experimental", "probably_fine")


def test_pinned_tier2_verdicts():
    """Round 2's held-out verdicts; pluvial's method is unchanged and round 2
    could not test it, so round 1's verdict stands. Fluvial, flash flood and
    waterlogging got a new (per-pixel) method, so round 1 no longer applies."""
    v = C.flood_verdicts()
    assert v == {"pluvial": "failed", "fluvial": "validated", "waterlogging": "not-run",
                 "coastal": "failed", "flash_flood": "not-run"}


def test_verdict_file_hash_is_enforced(tmp_path):
    with pytest.raises(C.ContractError, match="pinned"):
        C.flood_verdicts(expected_sha256="0" * 64)
    with pytest.raises(C.ContractError, match="pinned"):
        C.flood_verdicts(round2_sha256="0" * 64)


def test_pluvial_and_waterlogging_show_failed_not_placeholder():
    """(a) Pluvial runs on placeholder inputs and failed Tier 2 (round 1;
    round 2 could not test it): the worst applicable label wins, `failed`.
    Waterlogging's round-1 failure was on the retired scalar method; its
    per-pixel method was not-run in round 2 and, with its tuned weights, does
    not weight the placeholder impervious input: `experimental`."""
    from susceptibility.inputs import surface
    from susceptibility.pluvial import compute_pluvial_susceptibility
    from susceptibility.waterlogging import compute_waterlogging_susceptibility
    imp = surface(np.full((4, 4), 0.6), "OB", "footprint_union_area_fraction", "placeholder")
    inf = surface(np.full((4, 4), 0.2), "S2", "ndvi", "placeholder")
    rasters = {"status": "available", "shape": (4, 4), "errors": {},
               "layers": {"hand_m": surface(np.full((4, 4), 2.0), "MERIT", "hnd", "experimental")}}
    pluvial = compute_pluvial_susceptibility(impervious=imp, infiltration=inf)
    water = compute_waterlogging_susceptibility(rasters, impervious=imp)
    assert pluvial["validation_status"] == "placeholder"        # the module's own view
    assert water["validation_status"] == "experimental"
    v = C.flood_verdicts()
    assert C.hazard_label(pluvial["validation_status"], v["pluvial"]) == "failed"
    assert C.hazard_label(water["validation_status"], v["waterlogging"]) == "experimental"


def test_untested_module_keeps_its_own_label_and_a_tested_one_takes_its_verdict():
    v = C.flood_verdicts()
    assert C.hazard_label("experimental", v["flash_flood"]) == "experimental"   # not-run
    assert C.hazard_label("experimental", None, "placeholder") == "placeholder"
    assert C.hazard_label("experimental", v["coastal"]) == "failed"            # round 2
    # fluvial passed; without its scope (C70) the worst-of-inputs rule caps it
    # and `validated` never stands unscoped
    assert C.hazard_label("validated", v["fluvial"]) == "experimental"
    assert C.hazard_label("validated", v["fluvial"], "experimental") == "experimental"
    scope = C.VALIDATED_CONFIGS["fluvial"]["scope"]
    assert C.hazard_label("validated", v["fluvial"], "experimental", scope=scope) == "validated"
    with pytest.raises(C.ContractError):
        C.hazard_label("validated", v["fluvial"], scope={"events": ["x"]})


# ── C70: exactly the validated configuration keeps `validated`, scoped ──

def _fluvial():
    from susceptibility.fluvial import compute_fluvial_susceptibility
    from susceptibility.hydro_rasters import SOURCES
    from susceptibility.inputs import surface
    _, x = np.mgrid[0:6, 0:6]
    vals = {"hand_m": 0.5 + 2.0 * x, "upa_near_km2": np.full((6, 6), 50.0)}
    rasters = {"status": "available", "shape": (6, 6), "errors": {},
               "layers": {k: surface(a, *SOURCES[k], "experimental") for k, a in vals.items()}}
    return compute_fluvial_susceptibility(rasters)


def _hz(mod, verdicts=None):
    from analysis import hazards as H
    other = {"status": "insufficient_evidence", "validation_status": "experimental"}
    mods = {h: other for h in H.HAZARDS} | {"fluvial": mod}
    return H.hazard_outputs(mods, MV, verdicts or C.flood_verdicts(), has_waterways=False)["fluvial"]


def test_fluvial_with_its_validated_inputs_reads_validated_with_its_scope():
    o = _hz(_fluvial())
    assert o["validation_status"] == "validated"
    sc = o["validated_scope"]
    assert all(sc[k] for k in C.SCOPE_KEYS)
    assert any("hanoi" in e for e in sc["events"]) and any("kolonnawa" in e for e in sc["events"])
    assert sc["input_versions"] == {"MERIT/Hydro": "v1_0_1"}
    C.check_output(o)


@pytest.mark.parametrize("change", [
    lambda m: m["inputs"]["hand_m"].update(source="MERIT/Hydro/v1_0_2"),        # input version
    lambda m: m["inputs"]["upa_near_km2"].update(method="upa focal max r=2000 m, nearest"),
    lambda m: m["inputs"].pop("upa_near_km2"),                                  # input missing
    lambda m: m["weights"].update(river_size=0.5),
    lambda m: m["ceilings"].update(hand_m=20.0),
])
def test_any_differing_input_caps_fluvial_at_the_worst_label(change):
    mod = copy.deepcopy(_fluvial())
    change(mod)
    o = _hz(mod)
    assert o["validation_status"] == "experimental"
    assert o["validated_scope"] is None


def test_a_failed_verdict_is_not_rescued_by_a_matching_configuration():
    v = dict(C.flood_verdicts(), fluvial="failed")
    assert _hz(_fluvial(), v)["validation_status"] == "failed"


def test_the_validated_configuration_is_the_pinned_round2_run():
    """The literal record agrees with the pinned result and today's fetch."""
    import json
    from susceptibility.hydro_rasters import SOURCES
    cfg = C.VALIDATED_CONFIGS["fluvial"]
    with open(C.FLOOD_VALIDATION_ROUND2_RESULT) as fh:
        r2 = json.load(fh)["modules"]["fluvial"]
    assert r2["held_out"]["verdict"] == "validated"
    assert cfg["config"]["weights"] == r2["weights_used"]
    qualifying = sorted(e for e, p in r2["held_out_per_event"].items() if p["qualifies"])
    assert sorted(s.split()[0] for s in cfg["scope"]["events"]) == qualifying
    assert {k: tuple(i.values()) for k, i in cfg["config"]["inputs"].items()} == \
        {k: SOURCES[k] for k in ("hand_m", "upa_near_km2")}


def test_a_validated_output_without_a_scope_is_refused():
    o = _out()
    o["validation_status"] = "validated"
    with pytest.raises(C.ContractError):
        C.check_output(o)
    o["validated_scope"] = C.VALIDATED_CONFIGS["fluvial"]["scope"]
    C.check_output(o)


# ── model_version ──

def test_model_version_tracks_code_and_artifacts():
    a = C.model_version({"p": "1"}, commit={"commit": "c1", "diff_sha256": None})
    assert C.model_version({"p": "1"}, commit={"commit": "c1", "diff_sha256": None}) == a
    assert C.model_version({"p": "2"}, commit={"commit": "c1", "diff_sha256": None})["version_id"] \
        != a["version_id"]
    assert C.model_version({"p": "1"}, commit={"commit": "c2", "diff_sha256": None})["version_id"] \
        != a["version_id"]
    assert C.model_version({"p": "1"}, commit={"commit": "c1", "diff_sha256": "x"})["version_id"] \
        != a["version_id"]


def test_code_commit_reads_git():
    c = C.code_commit()
    assert len(c["commit"]) == 40


# ── enforcement ──

def test_a_well_formed_result_passes():
    r = _result({"fractions": {"built": _out(), "paved": C.absent(
        "not_computed", reason="item 21", validation_status="placeholder",
        data_sources=["none"], model_version=MV)}})
    assert C.check_result(r) == 2
    assert C.label_summary(r) == {"failed": 0, "placeholder": 1, "experimental": 1,
                                  "validated": 0}


@pytest.mark.parametrize("key", C.OUTPUT_KEYS)
def test_every_key_is_required(key):
    o = _out()
    del o[key]
    with pytest.raises(C.ContractError):
        C.check_result(_result({"x": o}))


def test_absent_is_never_a_measured_value():
    o = _out()
    o["value"] = None                     # status still "available"
    with pytest.raises(C.ContractError, match="absent must say why"):
        C.check_result(_result({"x": o}))
    o = _out(0.0)
    o["status"] = "not_computed"          # a zero claiming to be unmeasured
    with pytest.raises(C.ContractError, match="measured value"):
        C.check_result(_result({"x": o}))


def test_none_value_needs_an_explicit_status():
    with pytest.raises(C.ContractError):
        _out(None)


def test_non_finite_value_is_refused():
    with pytest.raises(C.ContractError, match="non-finite"):
        _out(float("nan"))


def test_retired_label_cannot_appear_in_the_new_pipeline():
    with pytest.raises(C.ContractError):
        _out(validation_status="retired")


def test_coverage_must_be_a_fraction():
    with pytest.raises(C.ContractError):
        _out(coverage=C.coverage(1.5, "aoi"))
    with pytest.raises(C.ContractError):
        _out(coverage={"basis": "aoi"})


def test_empty_data_sources_refused():
    with pytest.raises(C.ContractError):
        _out(data_sources=[])


def test_nothing_may_sit_beside_the_contract():
    with pytest.raises(C.ContractError, match="outside the contract"):
        C.check_result(_result({"fractions": {"built": _out(), "note": "free text"}}))


def test_every_output_carries_the_results_version():
    other = C.model_version({"producer": "zzz"}, commit={"commit": "x", "diff_sha256": None})
    with pytest.raises(C.ContractError, match="is not the result's"):
        C.check_result(_result({"x": _out(model_version=other)}))


def test_result_without_outputs_is_refused():
    with pytest.raises(C.ContractError):
        C.check_result({"model_version": MV, "outputs": {}})


def test_docs_changes_do_not_change_the_version(tmp_path):
    """A docs-only commit or uncommitted docs edit keeps version_id; a code
    change moves it. Before the fix any tracked edit made the tree dirty."""
    import subprocess
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "m.py").write_text("x = 1\n")
    (tmp_path / "NOTES.md").write_text("a\n")
    git("add", ".")
    git("commit", "-q", "-m", "code")
    base = C.code_commit(str(tmp_path))
    (tmp_path / "NOTES.md").write_text("b\n")                 # uncommitted docs edit
    assert C.code_commit(str(tmp_path))["diff_sha256"] is None
    git("commit", "-q", "-am", "docs")                        # docs-only commit
    after = C.code_commit(str(tmp_path))
    assert after["commit"] == base["commit"] and after["repo_head"] != base["repo_head"]
    mv = lambda c: C.model_version({"p": "1"}, commit=c)["version_id"]
    assert mv(after) == mv(base)
    (tmp_path / "analysis" / "m.py").write_text("x = 2\n")    # uncommitted code edit
    dirty = C.code_commit(str(tmp_path))
    assert dirty["dirty"] and mv(dirty) != mv(base)
