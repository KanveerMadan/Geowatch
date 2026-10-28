"""
Item 20 — the per-area OSM coverage score. Mandatory, never null.

Named for what it measures (manual item 20, "Naming caution"): a peer-relative
density rank and a regime flag, NOT a completeness rate. There is no
reference network to measure completeness against (03_EVIDENCE.md Part B).

Components, as specified:
  1. narrow pedestrian-path density, ranked against the measured reference
     set  -> `osm_density_percentile`
  2. arterial-to-pedestrian length ratio (good arterials + near-zero
     pedestrian is the signature of partial mapping)
  3. footprint count per road km

This item also sets the low-coverage policy's thresholds (Part 4 mandate,
decided 2026-09-24): topology metrics are SUPPRESSED below them, and
footprint metrics are computed with a reduced-confidence flag.

Every threshold below was fixed on 2026-10-27, before any coverage score was
computed on real data.
"""
from __future__ import annotations

from vector.roads import NEGATIVE_SPACE_TRIGGER_KM_PER_KM2

# ── Reference set: narrow pedestrian density, km/km^2 ───────────────────
#
# MEASURED LIVE 2026-10-27 by measure_reference() over the 11 baseline AOIs
# (vector.aois.BASELINE_AOIS) plus two formal anchors. Manual item 20 warns
# that a Global-South, informal-heavy baseline lets a formal city saturate
# the scale. The 03_EVIDENCE.md Part B figures are NOT reused: they were
# re-measured, and both are recorded in the manual.
#
# Two AOIs were measured with one clause unretrieved: guatemala without
# `arterial`, kigali without `other`. Neither clause feeds narrow pedestrian
# density, so neither value is a lower bound (see measure_reference).
REFERENCE_NARROW_KM_PER_KM2 = {
    # 11 baseline AOIs                         03_EVIDENCE.md Part B said
    "dharavi": 2.7817,                       # 2.78
    "nairobi": 2.1097,                       # 2.11
    "jakarta": 0.4072,                       # 0.39
    "hcmc": 0.9898,                          # 0.90
    "kigali": 1.8744,                        # 1.94
    "accra": 1.3027,                         # 1.29
    "dhaka": 2.2841,                         # 2.27
    "lagos": 0.1928,                         # 0.19
    "capetown": 8.3480,                      # 8.35 (Khayelitsha)
    "guatemala": 1.8303,                     # 1.83
    "nusantara": 0.6326,                     # 0.63
    # formal anchors
    "barcelona_eixample": 37.8070,           # sidewalks mapped as footways
    "chandigarh_central": 2.2482,
}
REFERENCE_MEASURED_ON = "2026-10-27"

# ── Regime thresholds (fixed before any score was computed) ──────────────
VERY_LOW_NARROW_KM_PER_KM2 = 0.3
LOW_NARROW_KM_PER_KM2 = NEGATIVE_SPACE_TRIGGER_KM_PER_KM2      # 1.0, one number for both
PARTIAL_MAPPING_ARTERIAL_TO_PEDESTRIAN = 5.0

# Zero denominators are reported as a capped value with `capped: true`,
# never as null and never as infinity, which JSON cannot carry.
RATIO_CAP = 1000.0
FOOTPRINTS_PER_KM_CAP = 1_000_000.0

REGIMES = ("adequate", "low", "very_low", "not_measurable")
# The regimes a reader must be warned about. The UI reads the per-block
# `low_coverage_warning` this sets; it never keeps its own list of regimes.
LOW_COVERAGE_REGIMES = frozenset({"low", "very_low", "not_measurable"})
SUPPRESS_TOPOLOGY_IN = LOW_COVERAGE_REGIMES


def percentile_rank(x: float, reference) -> float:
    """Mid-rank percentile of x within reference, in [0, 100]."""
    ref = list(reference)
    below = sum(1 for r in ref if r < x)
    equal = sum(1 for r in ref if r == x)
    return 100.0 * (below + 0.5 * equal) / len(ref)


def _ratio(num: float, den: float, cap: float) -> dict:
    if den > 0:
        v = num / den
        return {"value": min(v, cap), "capped": v > cap}
    return {"value": cap if num > 0 else 0.0, "capped": num > 0}


def score_layer(layer, reference=None, *, region=None, footprint_count=None) -> dict:
    """The coverage block for a layer, or for `region` within it.

    Always returns every field. When the pedestrian clause could not be
    fetched, the regime is "not_measurable" and topology is suppressed:
    the absence of data is reported, never scored as zero mapping.

    `footprint_count` overrides the count of the layer's own footprints. It
    is the server-side Open Buildings count (see coverage_inputs()), and is
    AOI-level only, so it cannot be combined with `region`.
    """
    if footprint_count is not None and region is not None:
        raise ValueError("footprint_count is an AOI-level count; it cannot score a region")
    ref = REFERENCE_NARROW_KM_PER_KM2 if reference is None else reference
    if not ref:
        raise RuntimeError("coverage reference set is not populated")
    # Leave-one-out: an AOI that is itself a reference member is ranked
    # against the OTHER members. Ranking it against its own (rounded) entry
    # made its percentile depend on the 4th decimal place of that rounding.
    if isinstance(ref, dict):
        ref_values = [v for k, v in ref.items() if k != layer.name]
        rank_basis = "leave_one_out" if layer.name in ref else "full_reference"
    else:
        ref_values, rank_basis = list(ref), "full_reference"

    area = (layer.aoi if region is None else region).area / 1e6
    L = layer.lengths_km(region)
    narrow_density = L["narrow_pedestrian"] / area if area else 0.0
    arterial_ratio = _ratio(L["arterial"], L["narrow_pedestrian"], RATIO_CAP)
    if footprint_count is not None:
        n_fp, fp_method = int(footprint_count), "open_buildings_server_count"
    elif region is None:
        n_fp, fp_method = len(layer.footprints), "layer_footprints"
    else:
        n_fp = sum(1 for p in layer.footprints if p.representative_point().within(region))
        fp_method = "layer_footprints_in_region"
    fp_per_km = _ratio(n_fp, L["all"], FOOTPRINTS_PER_KM_CAP)

    unavailable = list(layer.fetch.get("unavailable", []))
    reasons = []
    if "narrow_pedestrian" in unavailable or "arterial" in unavailable:
        regime = "not_measurable"
        reasons.append(f"Overpass clause(s) not retrieved: {unavailable}")
    elif narrow_density < VERY_LOW_NARROW_KM_PER_KM2:
        regime = "very_low"
        reasons.append(f"narrow pedestrian density {narrow_density:.2f} < "
                       f"{VERY_LOW_NARROW_KM_PER_KM2} km/km^2")
    else:
        regime = "adequate"
        if narrow_density < LOW_NARROW_KM_PER_KM2:
            regime = "low"
            reasons.append(f"narrow pedestrian density {narrow_density:.2f} < "
                           f"{LOW_NARROW_KM_PER_KM2} km/km^2")
        if arterial_ratio["value"] > PARTIAL_MAPPING_ARTERIAL_TO_PEDESTRIAN:
            regime = "low"
            reasons.append(f"arterial/pedestrian {arterial_ratio['value']:.1f} > "
                           f"{PARTIAL_MAPPING_ARTERIAL_TO_PEDESTRIAN} (partial-mapping signature)")
    suppress = regime in SUPPRESS_TOPOLOGY_IN

    return layer.stamp({
        "osm_density_percentile": round(percentile_rank(narrow_density, ref_values), 1),
        "coverage_regime_flag": regime,
        "low_coverage_warning": regime in LOW_COVERAGE_REGIMES,
        "regime_reasons": reasons,
        "narrow_pedestrian_km_per_km2": round(narrow_density, 4),
        "broad_pedestrian_km_per_km2": round(L["broad_pedestrian"] / area if area else 0.0, 4),
        "arterial_to_pedestrian_ratio": {**{k: (round(v, 3) if isinstance(v, float) else v)
                                            for k, v in arterial_ratio.items()},
                                         "fetch": layer.fetch_status("arterial", "narrow_pedestrian")},
        "footprints_per_road_km": {**{k: (round(v, 2) if isinstance(v, float) else v)
                                      for k, v in fp_per_km.items()},
                                   "fetch": layer.fetch_status("all")},
        # Per-grouping fetch completeness of the road lengths above.
        "road_length_fetch": {g: layer.fetch_status(g) for g in
                              ("all", "arterial", "narrow_pedestrian", "broad_pedestrian")},
        "footprint_count": n_fp,
        "footprint_count_method": fp_method,
        "footprint_source": layer.footprint_source,
        "topology_metrics_suppressed": suppress,
        "footprint_metrics_confidence": {"adequate": "normal", "low": "reduced",
                                         "very_low": "low", "not_measurable": "low"}[regime],
        "reference_set_size": len(ref_values),
        "percentile_basis": rank_basis,
        "reference_measured_on": REFERENCE_MEASURED_ON,
        # What this is. Deliberately not called a completeness rate (item 20).
        "measure": "peer_relative_density_rank",
        "scored": True,
    })


def not_measurable_block(reason: str) -> dict:
    """The coverage block for an AOI whose inputs could not be built at all
    (an Earth Engine or Overpass failure that raised). It carries the regime
    and the policy fields, and NO numeric score: there was nothing to measure,
    and a number here would read as a measurement."""
    return {
        "coverage_regime_flag": "not_measurable",
        "low_coverage_warning": True,
        "regime_reasons": [reason],
        "scored": False,
        "topology_metrics_suppressed": True,
        "footprint_metrics_confidence": "low",
        "validation_status": "experimental",
        "measure": "peer_relative_density_rank",
    }


def measure_reference(aois: dict, *, fetch=None) -> dict:
    """Narrow pedestrian density per AOI, measured live from OSM.
    Footprints are not needed for this, so none are downloaded."""
    from vector import roads, sources
    fetch = fetch or sources.fetch_osm_highways
    out = {}
    for name, bbox in aois.items():
        hw = fetch(name, bbox)
        # The reference value is narrow pedestrian density, which depends on
        # the narrow_pedestrian clause alone. Any OTHER missing clause cannot
        # bias it. A missing narrow clause would make it a lower bound, which
        # a reference value must never be.
        if "narrow_pedestrian" in hw["unavailable"]:
            raise RuntimeError(f"{name}: narrow_pedestrian clause not retrieved; "
                               f"a reference value must not be a lower bound")
        layer = roads.build_road_layer(name, bbox, highways=hw, footprints_4326=[],
                                       footprint_source="none")
        out[name] = layer.lengths_km()["narrow_pedestrian"] / layer.area_km2
    return out


def coverage_inputs(name: str, bbox):
    """(layer, footprint_count) for item 20, with ONE count method per source.

    Open Buildings AOIs: footprints are NOT downloaded. The count is the
    server-side count for every such AOI, never a mix with downloaded counts.
    OSM-footprint AOIs (no Open Buildings coverage): the OSM building ways
    themselves, a different source recorded as footprint_source.
    """
    from vector import roads, sources
    hw = sources.fetch_osm_highways(name, bbox)
    n_ob = sources.count_open_buildings(bbox)
    if n_ob > 0:
        layer = roads.build_road_layer(name, bbox, highways=hw, footprints_4326=[],
                                       footprint_source="open_buildings_v3")
        return layer, n_ob
    fps, src = roads.load_footprints(name, bbox)
    layer = roads.build_road_layer(name, bbox, highways=hw, footprints_4326=fps,
                                   footprint_source=src)
    return layer, None
