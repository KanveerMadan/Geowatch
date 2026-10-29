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
    # fluvial passed, but the worst-of-inputs rule still caps it by its inputs
    assert C.hazard_label("validated", v["fluvial"]) == "validated"
    assert C.hazard_label("validated", v["fluvial"], "experimental") == "experimental"


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


def test_serving_code_does_not_change_the_result_id_but_a_stage_does(tmp_path):
    """Editing analysis/jobs.py (or store.py) leaves version_id, and so the
    result ID, unchanged, committed or not; editing a stage changes both."""
    import subprocess
    from analysis import store

    def git(*a):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=tmp_path,
                       check=True, capture_output=True)

    files = {"analysis/jobs.py": "A = 1\n", "analysis/store.py": "B = 1\n",
             "analysis/run.py": "STEP = 1\n", "vector/roads.py": "R = 1\n"}
    for f, text in files.items():
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text(text)
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    window = {"start": "2026-01-01", "end": "2026-03-31"}

    def rid():
        mv = C.model_version({"p": "1"}, commit=C.code_commit(str(tmp_path)))
        return store.result_id((36.77, -1.32, 36.8, -1.3), window, None, mv["version_id"])

    base = rid()
    for serving in ("analysis/jobs.py", "analysis/store.py"):
        (tmp_path / serving).write_text("A = 2  # serving change\n")
        assert rid() == base, f"uncommitted {serving} edit changed the result ID"
        git("commit", "-qam", f"edit {serving}")
        assert rid() == base, f"committed {serving} edit changed the result ID"
    (tmp_path / "analysis/run.py").write_text("STEP = 2\n")
    dirty_stage = rid()
    assert dirty_stage != base
    git("commit", "-qam", "edit a stage")
    assert rid() != base                     # committed stage edit: a new ID too
    (tmp_path / "vector/roads.py").write_text("R = 2\n")
    assert rid() != base


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
