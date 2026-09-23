"""
The category palette — one definition, 04_FINDINGS_LEDGER.md C31, build item 43.

C31 measured 0 of 8 categories matching between `ingestion/inference.py`'s
`CATEGORY_COLORS_RGB` (which paints the server-rendered PNG) and `App.jsx`'s
`CAT_COLORS` (which paints the legend beside it). Worst was `dense_vegetation`,
Δ(34, 37, 75) — forest green in the overlay, mint green in the legend.

The deltas are small enough to read as opacity variation, which is what makes
misidentification easy: a user comparing legend to overlay does not conclude
"these disagree", they conclude "that patch is a slightly different shade of the
same thing."

WHAT ACTUALLY FAILED. `inference.py` carried this comment above its palette:

    # Category color palette — must match App.jsx's CAT_COLORS for the
    # 7 ML-resolvable categories exactly, so the frontend legend and the
    # PNG overlay agree visually.

A Python comment asserting a JavaScript constant. That is 01_DIAGNOSIS.md §4 S3
exactly — "a rule enforced only by prose fails at the first edit made by someone
who did not read the prose" — and it failed on every one of the eight.

SO COPYING THE VALUES ACROSS WOULD NOT BE A FIX. It would restore agreement
until the next edit, and leave the same comment making the same unenforceable
promise. This module is the single definition; the values reach the frontend by
being emitted into `result.json` (see `palette_for_result()`), never by being
retyped.

SCOPE. `annotate.py` holds a THIRD copy (`CATEGORY_COLORS`), which also
disagrees with this one — `dense_informal_roofing` is (220, 60, 60) there versus
(224, 60, 60) here. It is a standalone annotation tool, not part of the
pipeline → result.json → frontend path C31 measured, so it is deliberately left
alone rather than changed under an item that did not scope it. It is worth its
own item.
"""

# The seven categories the ML model can resolve. These values are authoritative:
# they are what inference.py has always painted into the PNG overlay, so keeping
# them means the overlay does not change appearance — only the legend, which was
# the half that was wrong.
ML_CATEGORY_COLORS_RGB = {
    "dense_informal_roofing":  (224, 60, 60),
    "sparse_informal_roofing": (240, 140, 80),
    "paved_road":              (120, 120, 180),
    "standing_water":          (40, 100, 200),
    "vegetation_clearing":     (210, 200, 80),
    "active_construction":     (200, 80, 200),
    "dense_vegetation":        (60, 180, 80),
}

# Categories that only ever arrive from OSM vector labels, never from the model
# (see osm_dem.py's OVERRIDABLE set). The frontend renders them, so they belong
# in the emitted palette; without them the frontend would still need a private
# map and the single source of truth would be only three-quarters true.
#
# Values taken from annotate.py, which is where these three have always been
# coloured — chosen over inventing new ones so nothing visibly changes for a
# category that already had an established colour somewhere.
OSM_ONLY_CATEGORY_COLORS_RGB = {
    "unpaved_dirt_road":     (180, 140, 80),
    "open_drainage_channel": (80, 160, 220),
    "open_waste":            (140, 100, 60),
}

# Painted where the CAAT threshold rejected every class. Emitted under the key
# "unknown" so the frontend can colour it like any other category rather than
# special-casing it -- item 43 requires the "unknown" row to travel with the
# rest.
UNKNOWN_COLOR_RGB = (96, 96, 128)
UNKNOWN_INDEX = 255

CATEGORY_COLORS_RGB = {**ML_CATEGORY_COLORS_RGB, **OSM_ONLY_CATEGORY_COLORS_RGB}


def rgb_to_hex(rgb) -> str:
    """(r, g, b) -> '#rrggbb'. The wire format; CSS cannot read a tuple."""
    r, g, b = rgb
    return "#%02x%02x%02x" % (int(r), int(g), int(b))


def palette_for_result() -> dict:
    """
    The palette block emitted into `result.json` under `landcover.palette`.

    This is the mechanism that makes drift structurally impossible rather than
    merely currently-absent: the frontend has no palette of its own to drift
    from, because it reads these values at render time. Changing a colour here
    changes the legend with no frontend edit, which is item 43's acceptance
    criterion.

    `source` is carried so a reader looking at a result.json can find the
    definition without grepping, and `format` so a consumer never has to guess
    whether it is holding tuples or strings.
    """
    colors = {name: rgb_to_hex(rgb) for name, rgb in CATEGORY_COLORS_RGB.items()}
    colors["unknown"] = rgb_to_hex(UNKNOWN_COLOR_RGB)
    return {
        "format": "hex_rgb",
        "source": "configs/palette.py",
        "unknown_index": UNKNOWN_INDEX,
        "ml_categories": sorted(ML_CATEGORY_COLORS_RGB),
        "osm_only_categories": sorted(OSM_ONLY_CATEGORY_COLORS_RGB),
        "colors": colors,
    }
