"""
The applicability gate — 04_FINDINGS_LEDGER.md C14/C20, build item 40.

`compute_applicability()` produced a correct out-of-distribution verdict on
every run and nothing consumed it. All 8 `compute_*` functions in
`susceptibility/` and `perception/` were enumerated by AST and none took an
applicability argument, so a run at `unknown_pct = 60` returned
`urban_landcover_model: out_of_distribution` in the same dictionary as
`pluvial: applicable` and `waterlogging: applicable`.

01_DIAGNOSIS.md §4 S2 names the shape: *signals computed, then never consumed*
— "designed as a router, wired as a report." This module is the wiring.

TWO DESIGN RULES, both from build item 40.

1. COMPUTE-AND-FLAG, NOT REFUSE-TO-COMPUTE. A refused computation destroys
   information: the caller learns neither the value nor how much to trust it,
   and cannot tell a refusal apart from a failure. A flagged computation keeps
   the number and attaches the reason it may be wrong. This also avoids
   recreating S1 — the system's inability to distinguish "measured", "measured
   absent" and "failed to measure" — by inventing a fourth ambiguous state
   ("withheld") that downstream code would have to guess about.

2. MODEL THE DEPENDENCY CHAIN, DON'T BLANKET-FLAG. Marking every mechanism
   out-of-distribution whenever the land-cover model is OOD would be wrong, not
   merely conservative: `fluvial` reads MERIT Hydro, `coastal` reads a GEE
   shoreline dataset, and `flash_flood` reads slope and upstream catchment.
   **None of those touch the semantic model**, so an OOD land-cover verdict
   says nothing about them. Flagging them anyway would train a reader to
   ignore the flag — the same way C33's `{pct ? ... : '0.0%'}` taught readers
   that "0.0%" means nothing in particular. A flag that fires everywhere
   carries no information.

WHAT ACTUALLY DEPENDS ON THE SEMANTIC MODEL, traced through the code rather
than assumed:

    urban_landcover_model  (unknown_pct / ambiguous_pct)
      │
      ├─ pluvial       — compute_pluvial_susceptibility(landcover_map=...,
      │                  categories=...) consumes the classified raster
      │
      ├─ hydrological_surfaces — compute_hydrological_surfaces(
      │    │             category_area_pct) is a weighted sum of the model's
      │    │             own category percentages
      │    └─ waterlogging — compute_waterlogging_susceptibility(
      │                      hydrological_surfaces=...) consumes that sum
      │
      └─ exposure      — landcover_builtup_pct is built in pipeline.py from
                         category_area_pct (dense_informal_roofing +
                         sparse_informal_roofing + paved_road)

    hand_context     → fluvial, flash_flood          (MERIT Hydro)
    coastal_context  → coastal                       (GEE shoreline)
    slope_context    → flash_flood                   (DEM slope)

    risk ← hazard + exposure  — compute_risk() consumes a susceptibility block
                                and an exposure block, so it inherits the worst
                                trust level of the two.

TWO SEPARATE AXES, deliberately not merged into one status. Conflating them is
how `not_applicable` (a statement about relevance — there is no coastline here)
would get mistaken for `out_of_distribution` (a statement about reliability —
the measurement cannot be trusted). They answer different questions and a
consumer may reasonably act on one and not the other:

    TRUST     — in_distribution / degraded / out_of_distribution
                Can this number be believed?
    RELEVANCE — applicable / low_relevance / not_applicable / not_calculated
                Does this mechanism apply to this AOI at all?
"""

# Mechanisms whose inputs are derived from the semantic land-cover model, and
# which therefore inherit its trust level. Declared as data rather than encoded
# in branches so the chain is auditable in one place, and so adding a mechanism
# is a one-line edit that cannot silently miss a consumer.
#
# Membership here is a claim about DATA FLOW and is verified by a test that
# fails if a mechanism's real inputs stop matching this table.
LANDCOVER_DERIVED = frozenset({"pluvial", "waterlogging", "exposure"})

# Mechanisms that read only external context (MERIT Hydro, GEE shoreline, DEM
# slope). An OOD land-cover verdict is irrelevant to these, and saying
# otherwise would be false.
LANDCOVER_INDEPENDENT = frozenset({"fluvial", "coastal", "flash_flood"})

# Ordered worst-first. Used to combine trust levels along the chain: a
# consumer's trust is the worst of its own and everything upstream of it.
_TRUST_ORDER = ("out_of_distribution", "degraded", "in_distribution")
_TRUST_RANK = {name: i for i, name in enumerate(_TRUST_ORDER)}

_UNTRUSTWORTHY = frozenset({"out_of_distribution", "degraded"})


def _worst_trust(*levels: str) -> str:
    """Worst (lowest-rank) trust level among those given; unknown names ignored."""
    known = [lv for lv in levels if lv in _TRUST_RANK]
    if not known:
        return "unknown"
    return min(known, key=lambda lv: _TRUST_RANK[lv])


def landcover_trust(applicability: dict | None) -> str:
    """The semantic model's own verdict — the root of the dependency chain."""
    if not applicability:
        return "unknown"
    return (applicability.get("urban_landcover_model") or {}).get("status", "unknown")


def build_flag(mechanism: str, applicability: dict | None) -> dict:
    """
    Build the applicability flag for one mechanism.

    Returned shape is identical for every mechanism and every code path, so a
    consumer never has to branch on which mechanism produced a block. That
    uniformity is the point: C31 and C4 are both cases of a contract enforced
    only by prose, and a flag whose shape varies by caller is the same trap.
    """
    if not applicability:
        # The signal was not threaded through. Say so explicitly rather than
        # implying the computation was trusted — the precise failure C14 was.
        return {
            "status": "unknown",
            "reason": "No applicability block was passed to this consumer.",
            "trust": "unknown",
            "out_of_distribution": False,
            "degraded": False,
            "depends_on": {},
            "degraded_by": [],
            "gate": "not_wired",
        }

    own = applicability.get(mechanism) or {}
    own_status = own.get("status", "unknown")
    own_reason = own.get("reason")

    lc_trust = landcover_trust(applicability)
    inherits_landcover = mechanism in LANDCOVER_DERIVED

    depends_on: dict[str, str] = {}
    degraded_by: list[str] = []
    if inherits_landcover:
        depends_on["urban_landcover_model"] = lc_trust
        if lc_trust in _UNTRUSTWORTHY:
            degraded_by.append("urban_landcover_model")
        trust = _worst_trust(lc_trust, "in_distribution")
    else:
        # Explicitly recorded as independent, so a reader can tell "not
        # affected" apart from "nobody checked".
        trust = "in_distribution" if lc_trust != "unknown" else "unknown"

    return {
        "status": own_status,
        "reason": own_reason,
        "trust": trust,
        "out_of_distribution": trust == "out_of_distribution",
        "degraded": trust == "degraded",
        "depends_on": depends_on,
        "degraded_by": degraded_by,
        "gate": "compute_and_flag",
    }


def annotate(block: dict, applicability: dict | None, mechanism: str) -> dict:
    """
    Attach the flag to a computed block.

    The block is returned with its value intact — this never withholds or
    rewrites a computed number. Mutates and returns the same dict so callers
    that already hold a reference see the flag.
    """
    if not isinstance(block, dict):
        return block
    block["applicability"] = build_flag(mechanism, applicability)
    return block


def inherit(block: dict, *upstream_blocks: dict, mechanism: str) -> dict:
    """
    Attach a flag derived from already-flagged upstream blocks.

    For consumers like `compute_risk()` whose trust is a function of what they
    consumed rather than of any single applicability entry. Takes the worst
    trust level across all upstream blocks and unions their `degraded_by`, so
    the reason survives the hop instead of being flattened to a bare boolean.
    """
    if not isinstance(block, dict):
        return block

    flags = [
        b.get("applicability") for b in upstream_blocks
        if isinstance(b, dict) and isinstance(b.get("applicability"), dict)
    ]
    if not flags:
        block["applicability"] = build_flag(mechanism, None)
        return block

    trust = _worst_trust(*[f.get("trust", "unknown") for f in flags])
    depends_on: dict[str, str] = {}
    degraded_by: list[str] = []
    for f in flags:
        depends_on.update(f.get("depends_on") or {})
        for src in f.get("degraded_by") or []:
            if src not in degraded_by:
                degraded_by.append(src)

    block["applicability"] = {
        "status": block.get("status", "unknown"),
        "reason": None,
        "trust": trust,
        "out_of_distribution": trust == "out_of_distribution",
        "degraded": trust == "degraded",
        "depends_on": depends_on,
        "degraded_by": degraded_by,
        "gate": "inherited",
    }
    return block


def gated(mechanism: str):
    """
    Decorator: accept an `applicability=` keyword and flag whatever is returned.

    Applied at the decorator level rather than by editing return statements
    because these functions have several early returns each
    (`insufficient_evidence`, `not_applicable`, the success path). Item 40's
    acceptance requires the flag on EVERY block, and a rule applied at the
    boundary cannot miss a path the way fifteen hand-edited returns can. This
    is the same argument that made item 70's auth a middleware rather than a
    per-endpoint decoration.

    `applicability` is consumed by the wrapper, so the wrapped function's own
    signature and body are untouched, and existing callers that omit it keep
    working — they get a flag with `gate: "not_wired"`, which is the honest
    description of that call.
    """
    import functools

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, applicability=None, **kwargs):
            return annotate(fn(*args, **kwargs), applicability, mechanism)

        wrapper.__gated_mechanism__ = mechanism
        return wrapper

    return decorate


def gated_inherit(mechanism: str, *upstream_params: str):
    """
    Decorator for consumers whose trust comes from what they consumed.

    `compute_risk()` has no applicability entry of its own -- it is not a
    mechanism the router reasons about. Its trustworthiness is entirely a
    function of the hazard and exposure blocks it was handed, both of which are
    already flagged by the time it runs. So it inherits, taking the worst trust
    level of its inputs and carrying their `degraded_by` forward.

    Binds the real signature rather than reading kwargs directly, so the
    upstream arguments are found whether the caller passed them positionally or
    by keyword.
    """
    import functools
    import inspect

    def decorate(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            try:
                bound = sig.bind_partial(*args, **kwargs)
                upstream = [bound.arguments.get(name) for name in upstream_params]
            except TypeError:
                upstream = []
            return inherit(
                result,
                *[u for u in upstream if isinstance(u, dict)],
                mechanism=mechanism,
            )

        wrapper.__gated_mechanism__ = mechanism
        return wrapper

    return decorate
