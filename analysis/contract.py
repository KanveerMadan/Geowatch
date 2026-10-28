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
VERDICT_LABEL = {"failed": "failed", "passed": "validated", "validated": "validated"}


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


def hazard_label(module_status: str, verdict: str | None = None, *input_labels: str) -> str:
    """A flood module's label: the worst of what the module says about
    itself, its Tier 2 verdict, and its inputs' labels."""
    v = verdict_label(verdict)
    return worst(module_status, *([v] if v else []), *input_labels)


def flood_verdicts(path: str = FLOOD_VALIDATION_RESULT, expected_sha256: str | None = None) -> dict:
    """{module: verdict} from the pinned Tier 2 result file. Raises if the
    file's hash is not the pinned one."""
    expected = FLOOD_VALIDATION_SHA256 if expected_sha256 is None else expected_sha256
    digest = sha256_file(path)
    if expected and digest != expected:
        raise ContractError(f"{path}: sha256 {digest} is not the pinned {expected}")
    with open(path) as fh:
        mods = json.load(fh)["modules"]
    return {k: v.get("verdict") for k, v in mods.items()}


# ── model_version ──────────────────────────────────────────────────────

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def code_commit(repo_dir: str | None = None) -> dict:
    """{"commit": sha, "dirty": bool, "diff_sha256": str | None}. Outside a
    git checkout, GEOWATCH_CODE_COMMIT is used; failing that, "unknown"."""
    cwd = repo_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True,
                             text=True, timeout=10, check=True).stdout.strip()
        diff = subprocess.run(["git", "diff", "HEAD", "--", ".", ":(exclude)data"], cwd=cwd,
                              capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {"commit": os.getenv("GEOWATCH_CODE_COMMIT", "unknown"), "dirty": None,
                "diff_sha256": None}
    return {"commit": sha, "dirty": bool(diff),
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
