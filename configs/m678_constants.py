"""
M6–M8 product settings (susceptibility/conditional_flood.py).

METHODS are the pre-registered methods (experiments/flood_m678/PREREGISTRATION_M678.md); the trust
label is read only from the one-shot reserve test (experiments/flood_m678/results/test_m678.json).
Before that file exists every type is `experimental` with the reason "not yet tested".
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_RESULT = os.path.join(ROOT, "experiments", "flood_m678", "results", "test_m678.json")
PREREG = os.path.join(ROOT, "experiments", "flood_m678", "PREREGISTRATION_M678.md")

FLOOD_TYPE_ID = {"debris_flow_glof": "M6", "embankment_dam_breach": "M7", "snowmelt_ice_jam": "M8"}
_TYPE_KIND = {v: k for k, v in FLOOD_TYPE_ID.items()}

# Pre-registered methods (PREREGISTRATION_M678.md §6, tag m678-freeze).
METHODS = {"debris_flow_glof": "phys_laharz", "embankment_dam_breach": "elev", "snowmelt_ice_jam": "elev"}
DEFAULT_LAKE_VOLUME_M3 = 60.59e6   # median ice-dammed GLOF v4.2 V0 since 2013 (m6_physics rule e)

TRUNK_SHARE = 0.25           # trunk channel: MERIT upa >= 25 % of the area maximum (as in DEV)
MIN_TRUNK_UPA_KM2 = 10.0     # no trunk channel below this upstream area
LAKE_SEARCH_KM = 50.0        # M6 applies when an inventoried glacial lake lies this close
MIN_SNOW_DAYS = 30           # M8 applies with at least this many MODIS snow-covered days a year
CLASS_BREAKS = (0.2, 0.4, 0.6, 0.8)
CLASSES = ("very_low", "low", "moderate", "high", "very_high")

LIMITATIONS = {
    "debris_flow_glof": [
        "Ranks where water would go if a glacial lake upstream released; it does not say whether or when a lake will fail.",
        "Debris and sediment deposits are not water and are not modelled.",
        "Radar labels in steep valleys are unobservable (shadow, layover), so the test covers open valley floors only."],
    "embankment_dam_breach": [
        "Ranks where water would go if a dam, levee or embankment upstream failed; it does not say whether one will.",
        "Which side of a levee breaks is not known in advance, so land on both sides is ranked.",
        "Tailings flows are not water and are not modelled."],
    "snowmelt_ice_jam": [
        "Ranks where spring melt or an ice-jam flood would reach; it does not forecast a melt season.",
        "Snow- or ice-covered ground cannot be judged flooded or dry in imagery, so the test scores snow-free cells only."],
}


def classify(score):
    if score is None:
        return "unknown"
    for b, c in zip(CLASS_BREAKS, CLASSES):
        if score < b:
            return c
    return CLASSES[-1]


def _test():
    if not os.path.exists(TEST_RESULT):
        return None
    with open(TEST_RESULT) as fh:
        return json.load(fh)


def validation_status(kind: str) -> str:
    """`validated` only if the type passed the one-shot reserve test; `experimental` otherwise."""
    t = _test()
    if not t:
        return "experimental"
    v = (t.get("by_type") or {}).get(FLOOD_TYPE_ID[kind], {})
    return "validated" if v.get("verdict") == "pass" else "experimental"


def trust_note(kind: str) -> str:
    t = _test()
    if not t:
        return "Not yet tested on held-out events: experimental."
    v = (t.get("by_type") or {}).get(FLOOD_TYPE_ID[kind], {})
    if v.get("verdict") == "pass":
        return f"Validated on {v.get('clusters')} held-out independent events ({v.get('scope', 'see evidence pack')})."
    return f"Experimental: {v.get('reason', 'the held-out test did not pass')}."
