"""
AOIs for the vector track. Each is (west, south, east, north), EPSG:4326.

Fixed before any vector result was computed (2026-10-27), so no AOI was chosen
for how it scored.

MORPHOLOGY_AOIS: item 19's acceptance needs formal European, formal Asian and
dense informal fabric. Footprint coverage was verified live first (Open
Buildings v3 polygon counts: Dharavi 19,339; Chandigarh 11,266; Lagos 34,056;
Barcelona 0, since Open Buildings does not cover Europe).

BASELINE_AOIS: the 11 training AOIs whose pedestrian-path density is
03_EVIDENCE.md Part B's baseline. These are the same boxes as
run_all_cities.CITIES; tests/test_vector_roads.py pins them equal.
"""

MORPHOLOGY_AOIS = {
    # Formal European: the Eixample grid. No Open Buildings coverage, so
    # footprints come from OSM building=* (dense and complete here).
    "barcelona_eixample": {"bbox": (2.150, 41.383, 2.175, 41.400),
                           "morphology": "formal_european"},
    # Formal Asian: Chandigarh's planned central sectors (Le Corbusier grid).
    "chandigarh_central": {"bbox": (76.765, 30.725, 76.790, 30.745),
                           "morphology": "formal_asian"},
    # Dense informal: the project's canonical Dharavi AOI.
    "dharavi": {"bbox": (72.836, 19.037, 72.862, 19.060),
                "morphology": "dense_informal"},
    # Dense informal, and the evidence base's clearest under-mapped case
    # (narrow pedestrian density 0.19 km/km^2): Ebute-Metta and Makoko.
    "lagos": {"bbox": (3.37, 6.475, 3.41, 6.51),
              "morphology": "dense_informal"},
}

BASELINE_AOIS = {
    "dharavi":   (72.836,  19.037,  72.862,  19.060),
    "nairobi":   (36.778,  -1.318,  36.812,  -1.284),
    "jakarta":   (106.78,  -6.13,   106.85,  -6.08),
    "hcmc":      (106.58,  10.78,   106.68,  10.88),
    "kigali":    (30.058,  -1.975,  30.082,  -1.952),
    "accra":     (-0.225,  5.54,    -0.19,   5.57),
    "dhaka":     (90.385,  23.765,  90.425,  23.795),
    "lagos":     (3.37,    6.475,   3.41,    6.51),
    "capetown":  (18.66,   -34.075, 18.71,   -34.03),
    "guatemala": (-90.54,  14.61,   -90.5,   14.65),
    "nusantara": (116.7,   -1.0,    116.76,  -0.945),
}
