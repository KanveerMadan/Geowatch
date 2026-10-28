"""
Phase 3: derive physical hydrological surfaces from the semantic
land-cover model's category_area_pct, instead of future susceptibility
engines (Phase 4+) consuming raw semantic labels directly.

Deliberately uses category_area_pct (aggregate percentages) rather than
per-pixel probabilities for this first pass -- the model's per-pixel
softmax probabilities exist in inference.py's mean_probs array but are
not currently threaded through to pipeline.py's output. Using the
already-available aggregate percentages is the smallest correct step
for this phase; switching to per-pixel fractional surfaces is a
reasonable future improvement, not done here to avoid scope creep.
"""

from configs.applicability_constants import (
    IMPERVIOUS_CLASS_WEIGHTS,
    INFILTRATION_CLASS_WEIGHTS,
)


def compute_hydrological_surfaces(category_area_pct: dict) -> dict:
    """
    Args:
        category_area_pct: {category: pct} from the mosaicked
            inference_result (see compute_area_stats() in inference.py)

    Returns:
        dict with status, impervious_fraction_pct, infiltration_proxy_pct,
        and per-class contribution breakdowns for transparency.

    Item 34 (C21): the failure path. When the model classified NO pixel --
    `category_area_pct` empty, or every share zero, i.e. an all-unknown AOI --
    there is no evidence for either surface, so both are None with status
    "insufficient_evidence". Before this they were 0.0 with no status, which
    finalize_applicability() and waterlogging read as a measured zero and
    turned into a confident "very_low".
    """
    known_pct = sum(v for v in (category_area_pct or {}).values() if v)
    if known_pct <= 0:
        return {
            "status": "insufficient_evidence",
            "reason": "No pixel was classified (all-unknown AOI): there is no "
                      "evidence for imperviousness or infiltration.",
            "impervious_fraction_pct": None,
            "infiltration_proxy_pct": None,
            "method": "weighted_sum_of_category_area_pct",
            "validated": False,
        }
    impervious_contributions = {}
    impervious_total = 0.0
    for cat, weight in IMPERVIOUS_CLASS_WEIGHTS.items():
        pct = category_area_pct.get(cat, 0.0)
        contribution = round(pct * weight, 4)
        impervious_contributions[cat] = contribution
        impervious_total += contribution

    infiltration_contributions = {}
    infiltration_total = 0.0
    for cat, weight in INFILTRATION_CLASS_WEIGHTS.items():
        pct = category_area_pct.get(cat, 0.0)
        contribution = round(pct * weight, 4)
        infiltration_contributions[cat] = contribution
        infiltration_total += contribution

    return {
        "status": "available",
        "impervious_fraction_pct": round(impervious_total, 2),
        "impervious_contributions_by_class": impervious_contributions,
        "infiltration_proxy_pct": round(infiltration_total, 2),
        "infiltration_contributions_by_class": infiltration_contributions,
        "method": "weighted_sum_of_category_area_pct",
        "validated": False,
        "limitations": [
            "Weights are provisional/uncalibrated against any real runoff "
            "measurement.",
            "Uses aggregate category_area_pct, not per-pixel fractional "
            "probabilities -- a coarser approximation than the model's "
            "actual per-pixel confidence would allow.",
            "active_construction is deliberately excluded from both "
            "surfaces -- its imperviousness is genuinely variable "
            "(bare soil early-stage vs. impervious late-stage) and "
            "guessing a fixed weight would be worse than omitting it.",
        ],
    }