"""
The result contract: one shape for every output of the analysis pipeline.

Every output is a dict carrying, at minimum:

    value               the measurement, or None when it was not measured
    status              why the value is what it is (see PRESENT / ABSENT)
    validation_status   validated | experimental | placeholder | failed
    coverage            {"observed_fraction": float in [0, 1], "basis": str}
    data_sources        non-empty list of strings
    model_version       {"code_commit", "artifact_hash", "version_id"}

`check_result()` walks a whole result and refuses anything that escapes the
contract, so a new output cannot be added without it.

LABEL PRECEDENCE (decided 2026-10-28, 08_STATE.md; "failed" added with item
26's Tier 2 run). An output takes the WORST label that applies to it:

    retired > failed > placeholder > experimental > validated

`failed` outranks `placeholder` because it is the stronger statement: the
output was tested against a pre-registered bar and did not pass. Pluvial and
waterlogging run on placeholder inputs AND failed Tier 2 (AUC 0.533, 0.432),
so they are `failed`. `retired` is the legacy 7-class pipeline's label and
outranks everything; nothing in this pipeline may carry it.

ABSENT IS NEVER ZERO (item 36, C33). A None value must carry an ABSENT status
saying why; a numeric value must carry status "available". A zero is then
always a measured zero.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess

# Worst first. Index = rank; lower is worse.
VALIDATION_PRECEDENCE = ("retired", "failed", "placeholder", "experimental", "validated")
# The labels a new-pipeline output may carry.
PIPELINE_LABELS = ("failed", "placeholder", "experimental", "validated")

OUTPUT_KEYS = ("value", "status", "validation_status", "coverage", "data_sources",
               "model_version")
MODEL_VERSION_KEYS = ("code_commit", "artifact_hash", "version_id")

PRESENT = ("available",)
ABSENT = ("not_computed", "insufficient_observation", "insufficient_evidence", "timeout",
          "failed", "unavailable", "not_applicable")

# The Tier 2 flood discrimination run (item 26, task 8). Its verdict is a
# label input for each module it tested. Pinned by hash: a different file is
# a different verdict and must not be read silently.
FLOOD_VALIDATION_RESULT = os.path.join("experiments", "flood_validation",
                                       "result_2026-10-28.json")
FLOOD_VALIDATION_SHA256 = "4bfcfc51d24beee56513ad8483d2d935c2b0f7d3bec0642d3802b7c6660a6b1a"
# Round 2 (item 26 Phase 1a): held-out verdicts, pinned the same way.
FLOOD_VALIDATION_ROUND2_RESULT = os.path.join("experiments", "flood_validation",
                                              "result_round2_2026-10-28.json")
FLOOD_VALIDATION_ROUND2_SHA256 = "6edde1eddd0a18c354db568f95babba1ec7af04754de6963a88f8a7f1108c73b"
# Round 2 replaced these modules' method (AOI-wide scalar -> per-pixel map), so
# round 1's verdict was on a method that no longer exists. Pluvial and coastal
# kept theirs: where round 2 could not test them (not-run), round 1 stands.
ROUND2_REPLACED_METHODS = ("fluvial", "flash_flood", "waterlogging")
# Round 3 (item 26 follow-ups): the same methods and weights re-tested with
# boxes centred on the mapped flood. Where it gave a verdict, that verdict is
# the module's; where it was not-run, the round-2 rule above decides.
FLOOD_VALIDATION_ROUND3_RESULT = os.path.join("experiments", "flood_validation",
                                              "result_round3_2026-10-29.json")
FLOOD_VALIDATION_ROUND3_SHA256 = "317daa1fcd96cb786463ca980ba1684bb89e9ba07da1e78f33a411518e6f5b5b"
# Flood round 4 replaced these modules' methods (PREREGISTRATION_ROUND4.md):
# rounds 1-3 tested methods that no longer run, so none of their verdicts is
# read for them; round 4's is. Round 4 failed all three (mean within-event
# AUC: pluvial 0.524, waterlogging 0.613, flash flood 0.640; bar 0.70).
ROUND4_REPLACED_METHODS = ("pluvial", "flash_flood", "waterlogging")
FLOOD_VALIDATION_ROUND4_RESULT = os.path.join("experiments", "flood_validation",
                                              "result_round4_2026-10-30.json")
FLOOD_VALIDATION_ROUND4_SHA256 = "b9f39615750c0c836c1c1ef6da1ceb195fb9d4fc660d76ac5af7f84776c013d3"
VERDICT_LABEL = {"failed": "failed", "passed": "validated", "validated": "validated"}

# C70 (item 26 flood follow-ups): a module that ran EXACTLY the configuration
# it was validated with keeps `validated`, and must say for what (SCOPE_KEYS).
# Any difference -- an input's source or method, a weight, a ceiling -- falls
# back to the worst-of-inputs rule. Literals, not today's constants: a changed
# constant is a changed configuration. Taken from the pinned round-2 run.
SCOPE_KEYS = ("events", "regions", "input_versions")
VALIDATED_CONFIGS = {
    "fluvial": {
        "config": {
            "method": "merit_hydro_hand_per_pixel_weighted",
            "weights": {"low_hand": 1.0, "river_size": 1.0},
            "ceilings": {"hand_m": 30.0, "upstream_area_km2": 10000.0},
            "inputs": {
                "hand_m": {"source": "MERIT/Hydro/v1_0_1", "method": "hnd, bilinear"},
                "upa_near_km2": {"source": "MERIT/Hydro/v1_0_1",
                                 "method": "upa focal max r=1000 m, nearest"},
            },
        },
        "scope": {
            "events": ["hanoi 2024-09-09 (Copernicus EMS EMSR754 AOI03), held-out AUC 0.9162",
                       "kolonnawa 2025-11-30 (Copernicus EMS EMSR851 AOI02), held-out AUC 0.7996"],
            "tuning_events": ["faenza 2023-05-02 (EMSR659 AOI02)",
                              "encantado 2024-05-02 (EMSR720 AOI02)"],
            "regions": ["Hanoi, Vietnam (Red River)", "Kolonnawa, Sri Lanka (Kelani Ganga)"],
            "input_versions": {"MERIT/Hydro": "v1_0_1"},
            "evidence": FLOOD_VALIDATION_ROUND2_RESULT,
            "note": "Validated for these events, regions and inputs only: two Asian river "
                    "cities, the pre-registered minimum of two (bar: mean within-event "
                    "AUC >= 0.70; held-out 0.8579). Not a claim about other places. "
                    "Narrowed by flood round 4 (2026-10-30): on three South Asian "
                    "monsoon floodplain events it failed (mean 0.5365), so the "
                    "validation does not extend to those events or regions.",
            # Flood round 4 (PREREGISTRATION_ROUND4.md, Labels): failed, so the
            # scope is narrowed, not the label (whether the label should change
            # too is C78, NEEDS FATE).
            "not_covered": {
                "evidence": "experiments/flood_validation/result_round4_2026-10-30.json",
                "round4_mean_auc": 0.5365,
                "events": ["bihar_2026 2026-09-11 (Kosi/Ganga at Kursela; Sentinel-1), AUC 0.6425",
                           "assam_2026 2026-07-20 (Dikhow at Nazira; Sentinel-1), AUC 0.3878",
                           "pakistan_2022 2022-08-31 (Sindh; UNOSAT FL20220808PAK), AUC 0.5791"],
                "regions": ["Bihar, India (Kosi-Ganga floodplain)",
                            "Upper Assam, India (Dikhow, Brahmaputra basin)",
                            "Sindh, Pakistan (Indus plain)"],
            },
        },
    },
}


# The eleven flood types (docs/flood_taxonomy.md, recorded 2026-10-30). Every
# type has an output under outputs.susceptibility.<module>, so none can go
# missing silently. Built types (M1-M5) are labelled by hazard_label; unbuilt
# ones by UNBUILT_FLOOD_TYPES below.
FLOOD_TAXONOMY = {
    "M1": {"module": "fluvial", "name": "fluvial",
           "status": "validated, scoped; round 4 failed, scope narrowed", "round": 4},
    "M2": {"module": "pluvial", "name": "pluvial", "status": "new method; round 4 failed",
           "round": 4},
    "M3": {"module": "waterlogging", "name": "waterlogging",
           "status": "new method; round 4 failed", "round": 4},
    "M4": {"module": "flash_flood", "name": "flash flood", "status": "new method; round 4 failed",
           "round": 4},
    "M5": {"module": "coastal", "name": "coastal", "status": "failed; new method planned",
           "round": 5},
    "M6": {"module": "debris_flow_glof", "name": "debris flow / glacial lake outburst",
           "status": "not built", "round": 5},
    "M7": {"module": "embankment_dam_breach", "name": "embankment / dam breach",
           "status": "not built", "round": 5},
    "M8": {"module": "snowmelt_ice_jam", "name": "snowmelt / ice jam", "status": "not built",
           "round": 5},
    "M9": {"module": "compound", "name": "compound", "status": "not built; after M1-M3",
           "round": 6},
    "M10": {"module": "groundwater", "name": "groundwater",
            "status": "not measurable: labelled, not tested", "round": None},
    "M11": {"module": "tsunami", "name": "tsunami", "status": "out of scope", "round": None},
}
# {module: (ABSENT status, validation label, reason)} for the types no module
# computes. `placeholder` as for every other not_computed output.
UNBUILT_FLOOD_TYPES = {
    "debris_flow_glof": ("not_computed", "placeholder", "not built; planned for flood round 5"),
    "embankment_dam_breach": ("not_computed", "placeholder",
                              "not built; planned for flood round 5"),
    "snowmelt_ice_jam": ("not_computed", "placeholder", "not built; planned for flood round 5"),
    "compound": ("not_computed", "placeholder",
                 "not built; planned for flood round 6, after fluvial, pluvial and "
                 "waterlogging"),
    "groundwater": ("not_computed", "placeholder",
                    "not measurable: no water-table observation to score or test against"),
    "tsunami": ("not_applicable", "placeholder", "out of scope"),
}


class ContractError(ValueError):
    pass


def worst(*labels: str) -> str:
    """The worst label among `labels`, by VALIDATION_PRECEDENCE."""
    if not labels:
        raise ContractError("worst() needs at least one label")
    for lab in labels:
        if lab not in VALIDATION_PRECEDENCE:
            raise ContractError(f"unknown validation label {lab!r}")
    return min(labels, key=VALIDATION_PRECEDENCE.index)


def verdict_label(verdict: str | None) -> str | None:
    """A Tier 2 verdict as a label input. "not-run" and absence add nothing:
    an untested module keeps the label its method and inputs give it."""
    return VERDICT_LABEL.get(verdict) if verdict else None


def module_config(mod: dict) -> dict:
    """What a module output says it ran, in VALIDATED_CONFIGS' shape."""
    return {"method": mod.get("method"), "weights": mod.get("weights"),
            "ceilings": mod.get("ceilings"),
            "inputs": {k: {"source": i.get("source"), "method": i.get("method")}
                       for k, i in (mod.get("inputs") or {}).items() if isinstance(i, dict)}}


def validated_scope(name: str, mod: dict, verdict: str | None) -> dict | None:
    """C70: the scope note when module `name` passed Tier 2 and ran exactly
    its validated configuration; None otherwise."""
    cfg = VALIDATED_CONFIGS.get(name)
    if cfg is None or verdict_label(verdict) != "validated" or module_config(mod) != cfg["config"]:
        return None
    return json.loads(json.dumps(cfg["scope"]))          # a copy the caller cannot mutate


def hazard_label(module_status: str, verdict: str | None = None, *input_labels: str,
                 scope: dict | None = None) -> str:
    """A flood module's label: the worst of what the module says about
    itself, its Tier 2 verdict, and its inputs' labels. With a `scope`
    (validated_scope: exactly the validated configuration) the inputs do
    not cap it. Without one it is never `validated` (C70)."""
    v = verdict_label(verdict)
    if scope:
        check_scope(scope)
        return worst(module_status, *([v] if v else []))
    lab = worst(module_status, *([v] if v else []), *input_labels)
    return "experimental" if lab == "validated" else lab


def check_scope(scope, where: str = "") -> None:
    if not isinstance(scope, dict) or any(not scope.get(k) for k in SCOPE_KEYS):
        raise ContractError(f"{where}: a validated output needs a scope note with "
                            f"non-empty {SCOPE_KEYS}")


def _pinned_modules(path: str, expected: str) -> dict:
    digest = sha256_file(path)
    if expected and digest != expected:
        raise ContractError(f"{path}: sha256 {digest} is not the pinned {expected}")
    with open(path) as fh:
        return json.load(fh)["modules"]


def flood_verdicts(path: str = FLOOD_VALIDATION_RESULT, expected_sha256: str | None = None,
                   round2_path: str = FLOOD_VALIDATION_ROUND2_RESULT,
                   round2_sha256: str | None = None,
                   round3_path: str = FLOOD_VALIDATION_ROUND3_RESULT,
                   round3_sha256: str | None = None,
                   round4_path: str = FLOOD_VALIDATION_ROUND4_RESULT,
                   round4_sha256: str | None = None) -> dict:
    """{module: verdict}: each module's round-3 held-out verdict where round 3
    gave one; else its round-2 verdict; where that is not-run and the
    module's method is unchanged since round 1, round 1's verdict. A module
    whose method round 4 replaced takes round 4's verdict only (None where
    round 4 was not-run). Fluvial's round-4 result narrows its scope note, not
    its verdict (pre-registered). Raises if any file's hash is not the pinned
    one."""
    r1 = _pinned_modules(path, FLOOD_VALIDATION_SHA256 if expected_sha256 is None
                         else expected_sha256)
    r2 = _pinned_modules(round2_path, FLOOD_VALIDATION_ROUND2_SHA256 if round2_sha256 is None
                         else round2_sha256)
    r3 = _pinned_modules(round3_path, FLOOD_VALIDATION_ROUND3_SHA256 if round3_sha256 is None
                         else round3_sha256)
    r4 = _pinned_modules(round4_path, FLOOD_VALIDATION_ROUND4_SHA256 if round4_sha256 is None
                         else round4_sha256)
    out = {}
    for m in r1.keys() | r2.keys():
        if m in ROUND4_REPLACED_METHODS:
            v4 = (r4.get(m) or {}).get("held_out", {}).get("verdict")
            out[m] = v4 if v4 and v4 != "not-run" else None
            continue
        v2 = (r2.get(m) or {}).get("held_out", {}).get("verdict")
        v3 = (r3.get(m) or {}).get("held_out", {}).get("verdict")
        if v3 and v3 != "not-run":
            out[m] = v3
        elif v2 and (v2 != "not-run" or m in ROUND2_REPLACED_METHODS):
            out[m] = v2
        else:
            out[m] = (r1.get(m) or {}).get("verdict")
    return out


# ── model_version ──────────────────────────────────────────────────────

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# The code a result depends on: every package the pipeline imports. Docs,
# tests, the UI and api.py do not change an output, so a commit or an
# uncommitted edit that touches only those must not change version_id --
# otherwise any docs edit would invalidate every cached result. Measured
# 2026-10-28: a ledger edit made mid-run gave Dharavi's rerun a new ID.
CODE_PATHS = ("analysis", "vector", "susceptibility", "ingestion", "perception", "configs")


def code_commit(repo_dir: str | None = None, paths=CODE_PATHS) -> dict:
    """{"commit": the last commit touching `paths`, "dirty": bool,
    "diff_sha256": hash of the uncommitted diff under `paths` or None,
    "repo_head": HEAD, for traceability}. Outside a git checkout,
    GEOWATCH_CODE_COMMIT is used; failing that, "unknown"."""
    cwd = repo_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        def git(*a):
            return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True,
                                  timeout=30, check=True).stdout
        head = git("rev-parse", "HEAD").strip()
        sha = git("log", "-1", "--format=%H", "--", *paths).strip() or head
        diff = git("diff", "HEAD", "--", *paths)
    except (OSError, subprocess.SubprocessError):
        return {"commit": os.getenv("GEOWATCH_CODE_COMMIT", "unknown"), "dirty": None,
                "diff_sha256": None, "repo_head": None}
    return {"commit": sha, "dirty": bool(diff), "repo_head": head,
            "diff_sha256": hashlib.sha256(diff.encode()).hexdigest() if diff else None}


def model_version(artifacts: dict, commit: dict | None = None) -> dict:
    """The version stamp. `artifacts` is {name: sha256} for every model,
    parameter set or reference file the outputs depend on.

    version_id changes when the code, its uncommitted diff, or any artifact
    changes, so it is safe to key a cache on."""
    commit = commit if commit is not None else code_commit()
    artifact_hash = sha256_json(artifacts)
    version_id = sha256_json([commit["commit"], commit.get("diff_sha256"), artifact_hash])[:16]
    return {"code_commit": commit["commit"], "code_dirty": commit.get("dirty"),
            "repo_head": commit.get("repo_head"), "code_paths": list(CODE_PATHS),
            "artifact_hash": artifact_hash, "artifacts": dict(artifacts),
            "version_id": version_id}


def output_version(mv: dict) -> dict:
    """The compact per-output form of a model_version."""
    return {k: mv[k] for k in MODEL_VERSION_KEYS}


# ── building outputs ───────────────────────────────────────────────────

def coverage(observed_fraction, basis: str, **extra) -> dict:
    if observed_fraction is not None:
        observed_fraction = float(observed_fraction)
    return {"observed_fraction": observed_fraction, "basis": basis, **extra}


def output(value, *, validation_status: str, coverage: dict, data_sources, model_version: dict,
           status: str | None = None, **extra) -> dict:
    """One contract-shaped output. `status` defaults from `value`: "available"
    for a value, and a None value must name its ABSENT status explicitly."""
    if status is None:
        if value is None:
            raise ContractError("a None value needs an explicit ABSENT status")
        status = "available"
    out = {"value": value, "status": status, "validation_status": validation_status,
           "coverage": coverage, "data_sources": list(data_sources),
           "model_version": output_version(model_version), **extra}
    check_output(out, where="output()")
    return out


def absent(status: str, *, reason: str, validation_status: str, data_sources, model_version: dict,
           basis: str = "not measured", **extra) -> dict:
    """An output with no value. Its coverage is 0.0: nothing was observed for it."""
    return output(None, status=status, reason=reason, validation_status=validation_status,
                  coverage=coverage(0.0, basis), data_sources=data_sources,
                  model_version=model_version, **extra)


# ── enforcement ────────────────────────────────────────────────────────

def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_output(o: dict, *, where: str = "", version_id: str | None = None,
                 allowed_labels=PIPELINE_LABELS) -> None:
    """Raise ContractError if `o` is not a contract-shaped output."""
    missing = [k for k in OUTPUT_KEYS if k not in o]
    if missing:
        raise ContractError(f"{where}: missing {missing}")
    if o["validation_status"] not in allowed_labels:
        raise ContractError(f"{where}: validation_status {o['validation_status']!r} "
                            f"not in {allowed_labels}")
    if o["validation_status"] == "validated":        # C70: validated says for what
        check_scope(o.get("validated_scope"), where)
    if o["value"] is None:
        if o["status"] not in ABSENT:
            raise ContractError(f"{where}: value None with status {o['status']!r}; "
                                f"absent must say why ({ABSENT})")
    elif o["status"] not in PRESENT:
        raise ContractError(f"{where}: a value with status {o['status']!r}; "
                            f"a measured value is {PRESENT}")
    if _is_number(o["value"]) and not math.isfinite(o["value"]):
        raise ContractError(f"{where}: non-finite value {o['value']!r}")
    cov = o["coverage"]
    if not isinstance(cov, dict) or "observed_fraction" not in cov or "basis" not in cov:
        raise ContractError(f"{where}: coverage must carry observed_fraction and basis")
    of = cov["observed_fraction"]
    if of is not None and not (_is_number(of) and 0.0 <= of <= 1.0):
        raise ContractError(f"{where}: observed_fraction {of!r} outside [0, 1]")
    if not isinstance(o["data_sources"], list) or not o["data_sources"] \
            or not all(isinstance(s, str) and s for s in o["data_sources"]):
        raise ContractError(f"{where}: data_sources must be a non-empty list of strings")
    mv = o["model_version"]
    if not isinstance(mv, dict) or any(not mv.get(k) for k in MODEL_VERSION_KEYS):
        raise ContractError(f"{where}: model_version must carry {MODEL_VERSION_KEYS}")
    if version_id is not None and mv["version_id"] != version_id:
        raise ContractError(f"{where}: model_version {mv['version_id']} is not the "
                            f"result's {version_id}")


def is_output(node) -> bool:
    return isinstance(node, dict) and "value" in node and "validation_status" in node


def walk_outputs(node, path: str = "outputs"):
    """Yield (path, output) for every output under `node`. A dict that is not
    an output is a container, and every one of its values must itself be an
    output or a container: nothing is allowed to sit beside the contract."""
    if is_output(node):
        yield path, node
        return
    if not isinstance(node, dict):
        raise ContractError(f"{path}: {type(node).__name__} outside the contract "
                            f"(containers hold only outputs and containers)")
    if not node:
        raise ContractError(f"{path}: empty container")
    for k, v in node.items():
        yield from walk_outputs(v, f"{path}.{k}")


def check_result(result: dict) -> int:
    """Enforce the contract across a whole result. Returns the number of
    outputs checked. Raises ContractError on the first violation."""
    mv = result.get("model_version")
    if not isinstance(mv, dict) or any(not mv.get(k) for k in MODEL_VERSION_KEYS):
        raise ContractError("result.model_version is missing or incomplete")
    n = 0
    for path, o in walk_outputs(result.get("outputs"), "outputs"):
        check_output(o, where=path, version_id=mv["version_id"])
        n += 1
    if n == 0:
        raise ContractError("result has no outputs")
    return n


def label_summary(result: dict) -> dict:
    """Count of outputs per validation label. Deliberately not collapsed into
    one result-level label: a single "failed" would misdescribe the outputs
    that did not fail."""
    counts = {lab: 0 for lab in PIPELINE_LABELS}
    for _, o in walk_outputs(result["outputs"]):
        counts[o["validation_status"]] += 1
    return counts
