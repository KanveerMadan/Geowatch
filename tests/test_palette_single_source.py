r"""
C31 regression tests — the palette had drifted on all 8 categories.

04_FINDINGS_LEDGER.md C31 [E], build item 43: 0 of 8 exact matches between
`ingestion/inference.py`'s `CATEGORY_COLORS_RGB`, which paints the
server-rendered PNG, and `App.jsx`'s `CAT_COLORS`, which painted the legend
beside it. Worst was `dense_vegetation`, Δ(34, 37, 75) — forest green in the
overlay, mint green in the legend.

Measured before the fix, reproducing the ledger exactly:

    dense_informal_roofing   #e03c3c  vs  #e0625a   Δ(0, 38, 30)
    sparse_informal_roofing  #f08c50  vs  #e8a35a   Δ(8, 23, 10)
    paved_road               #7878b4  vs  #8888c8   Δ(16, 16, 20)
    standing_water           #2864c8  vs  #4a90e2   Δ(34, 44, 26)
    vegetation_clearing      #d2c850  vs  #d8c85a   Δ(6, 0, 10)
    active_construction      #c850c8  vs  #c878d0   Δ(0, 40, 8)
    dense_vegetation         #3cb450  vs  #5ed99b   Δ(34, 37, 75)
    unknown                  #606080  vs  #716fa0   Δ(17, 15, 32)

WHAT THE FIX HAS TO BE. The item is explicit that copying the values across is
NOT it: that restores agreement until the next edit and leaves the same
unenforceable comment in place. `inference.py` carried "must match App.jsx's
CAT_COLORS ... exactly" above the dict — a Python comment asserting a JavaScript
constant, which is 01_DIAGNOSIS.md §4 S3 ("a rule enforced only by prose fails
at the first edit made by someone who did not read the prose"). It failed on all
eight.

So the assertions below are structural, not value comparisons: there is ONE
definition, it is emitted with the result, and nothing on the frontend holds a
competing copy. The behavioural half — change a colour in the backend, the
rendered legend changes with no frontend edit — is in
tests/test_palette_ui.mjs, because that is where rendering lives.

Run from the repo root:  pytest tests/test_palette_single_source.py
"""

import inspect
import json
import re
from pathlib import Path

import pytest

from configs import palette as palette_mod
from configs.palette import (
    CATEGORY_COLORS_RGB,
    ML_CATEGORY_COLORS_RGB,
    OSM_ONLY_CATEGORY_COLORS_RGB,
    UNKNOWN_COLOR_RGB,
    palette_for_result,
    rgb_to_hex,
)

APP_JSX = Path("geowatch-ui/src/App.jsx")
PALETTE_JS = Path("geowatch-ui/src/palette.js")


# ── One definition ──

def test_inference_does_not_define_its_own_palette():
    """
    `inference.py` re-exports the canonical names; it must not redefine them.
    A second literal is how the original drift started.
    """
    src = inspect.getsource(__import__("ingestion.inference", fromlist=["x"]))
    assert "CATEGORY_COLORS_RGB = {" not in src, (
        "inference.py has a literal palette again; it must import from configs.palette"
    )
    from ingestion.inference import CATEGORY_COLORS_RGB as reexported
    assert reexported is CATEGORY_COLORS_RGB, "must be the same object, not a copy"


def test_the_lying_comment_is_gone():
    """
    The comment that made the promise nothing enforced. Leaving it would invite
    the next person to satisfy it by hand-copying, which is the failure mode.
    """
    src = inspect.getsource(__import__("ingestion.inference", fromlist=["x"]))
    assert "must match App.jsx's CAT_COLORS" not in src


def test_ml_colours_are_unchanged_by_the_refactor():
    """
    The overlay was never the wrong half -- the legend was. These values must
    survive exactly, or the fix would silently repaint every archived PNG's
    meaning.
    """
    assert ML_CATEGORY_COLORS_RGB == {
        "dense_informal_roofing":  (224, 60, 60),
        "sparse_informal_roofing": (240, 140, 80),
        "paved_road":              (120, 120, 180),
        "standing_water":          (40, 100, 200),
        "vegetation_clearing":     (210, 200, 80),
        "active_construction":     (200, 80, 200),
        "dense_vegetation":        (60, 180, 80),
    }
    assert UNKNOWN_COLOR_RGB == (96, 96, 128)


# ── What gets emitted ──

def test_emitted_palette_covers_every_category_plus_unknown():
    """
    Item 43 requires the "unknown" row to travel with the rest. If it did not,
    the frontend would still need a private map for it and the single source of
    truth would be only partly true.
    """
    block = palette_for_result()
    colors = block["colors"]
    for name in CATEGORY_COLORS_RGB:
        assert name in colors, f"{name} missing from the emitted palette"
    assert "unknown" in colors, "the unknown row must be emitted (item 43)"
    assert len(colors) == len(CATEGORY_COLORS_RGB) + 1


def test_emitted_values_are_css_ready_hex():
    """CSS cannot read a tuple; a consumer must never have to convert."""
    for name, value in palette_for_result()["colors"].items():
        assert re.fullmatch(r"#[0-9a-f]{6}", value), f"{name} = {value!r}"


def test_emitted_palette_matches_the_definition_exactly():
    block = palette_for_result()
    for name, rgb in CATEGORY_COLORS_RGB.items():
        assert block["colors"][name] == rgb_to_hex(rgb)
    assert block["colors"]["unknown"] == rgb_to_hex(UNKNOWN_COLOR_RGB)


def test_palette_block_is_self_describing():
    """
    A reader holding a result.json should be able to find the definition and
    know the encoding without grepping the codebase.
    """
    block = palette_for_result()
    assert block["format"] == "hex_rgb"
    assert block["source"] == "configs/palette.py"
    assert block["unknown_index"] == 255


def test_pipeline_emits_the_palette_into_the_landcover_block():
    """The mechanism the whole item rests on."""
    src = Path("pipeline.py").read_text()
    assert '"palette": palette_for_result()' in src, (
        "pipeline.py must emit the palette into result.json"
    )
    assert "from configs.palette import palette_for_result" in src


def test_emitted_palette_is_json_serialisable():
    json.dumps(palette_for_result())


# ── Nothing competes with it ──

def test_frontend_has_no_palette_literal():
    """
    The other half of C31. A hardcoded map on the frontend is the thing that
    drifted; if one comes back, this fails.
    """
    src = APP_JSX.read_text()
    assert "const CAT_COLORS = {" not in src, (
        "App.jsx defines a colour map again -- colours must come from the result"
    )


@pytest.mark.parametrize("hexval", [rgb_to_hex(v) for v in ML_CATEGORY_COLORS_RGB.values()])
def test_backend_colours_are_not_hardcoded_in_app_jsx(hexval):
    """
    Not even the CORRECT values may be pasted in. A correct copy is still a
    copy, and drifts at the next edit -- which is exactly how 0 of 8 happened.
    """
    assert hexval not in APP_JSX.read_text(), (
        f"{hexval} is hardcoded in App.jsx; read it from the result instead"
    )


def test_legacy_fallback_holds_only_the_old_wrong_values():
    """
    palette.js keeps the OLD frontend colours for runs that predate this item,
    deliberately. It must not be quietly upgraded into a second live palette:
    if someone "fixes" it to the correct values it becomes a competing source
    again, so assert it still holds the wrong ones.
    """
    src = PALETTE_JS.read_text()
    assert "#5ed99b" in src, "legacy dense_vegetation should stay as it was"
    for rgb in ML_CATEGORY_COLORS_RGB.values():
        assert rgb_to_hex(rgb) not in src, (
            f"{rgb_to_hex(rgb)} appears in palette.js -- the fallback must not "
            f"mirror the canonical values, or it becomes a second source"
        )


def test_annotate_third_copy_is_recorded_not_forgotten():
    """
    annotate.py holds a THIRD palette that also disagrees
    (dense_informal_roofing 220 vs 224). It is out of scope for item 43, which
    measured the backend-to-frontend path -- but it must be written down rather
    than discovered again later.
    """
    assert "annotate.py" in palette_mod.__doc__
    from annotate import CATEGORY_COLORS as annotate_palette
    assert annotate_palette["dense_informal_roofing"] != \
        ML_CATEGORY_COLORS_RGB["dense_informal_roofing"], (
        "annotate.py now agrees -- update configs/palette.py's scope note"
    )


# ── The acceptance property, at the backend boundary ──

def test_changing_a_backend_colour_changes_what_is_emitted(monkeypatch):
    """
    Half of item 43's acceptance: a colour change must propagate outward with no
    other edit. The frontend half is in tests/test_palette_ui.mjs.
    """
    monkeypatch.setitem(CATEGORY_COLORS_RGB, "dense_vegetation", (1, 2, 3))
    assert palette_for_result()["colors"]["dense_vegetation"] == "#010203"
