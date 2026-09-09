"""
Site registry for the item 21 Phase 0 VHR impervious-label pipeline.

Phase 0 ran on a single site (Old Fadama / Agbogbloshie, Accra) and returned a
CONFOUNDED miss: ridge R2 = 0.363 against a >=0.60 bar, but with a label whose
own binary accuracy was 0.711 and a target saturated at median 0.942. Section
7.6 of `06_UNMIXING_CEILING.md` named the two things that would close it, and
this module exists to run the same pipeline against them:

  1. a site without the scrap/roof ambiguity that capped the Accra label
  2. a site with real dynamic range in impervious fraction

Nothing about the METHOD changes. The pre-registered regression bar, the
spatially blocked split, the co-registration check and the patch-level accuracy
protocol are all carried over unchanged from the Accra run. What changes is the
site, and the Accra configuration is retained here verbatim so that result stays
reproducible.

PRE-REGISTRATION FOR THE RE-RUN — fixed before any Nairobi result existed
=========================================================================
Recorded here rather than in a commit message so it cannot drift.

(a) REGRESSION BAR — carried over unchanged from the Accra run:
        R2 >= 0.60  -> impervious_total works at 10 m per-pixel
        0.50 - 0.60 -> usable, ships with a prominent confidence caveat
        R2 <  0.50  -> does not work at 10 m per-pixel
    Primary model is ridge (`regress_built_fraction.PRIMARY_MODEL`), as before.
    GBT is reported alongside but is NOT the primary; the Accra run's GBT 0.537
    against ridge 0.363 is a result to be re-tested here, not a bar to move to.

(b) DE-CONFOUNDING CONDITIONS. The Accra miss could not distinguish "reflectance
    does not predict impervious" from "the label is too noisy and too saturated
    to tell". A re-run only removes that ambiguity if it beats Accra on BOTH
    axes, so both are pre-registered as gates on the INTERPRETATION, not on the
    result:

        LABEL_ACC_MIN  = 0.711   label binary accuracy must EXCEED Accra's
        TARGET_P50_MAX = 0.85    median impervious must be BELOW Accra's 0.942
                                 by enough to leave variance to explain
        TARGET_SD_MIN  = 0.20    and the spread must be at least Accra's ~0.28
                                 less a margin

    If a gate fails, the run inherits Accra's confound on that axis and MUST be
    reported as such -- a miss stays confounded, and a pass is still a pass
    (label noise and saturation both bias R2 DOWNWARD, so they can only make a
    pass harder, never manufacture one).

(c) DIRECTION OF THE LABEL-NOISE BIAS, restated so it cannot be re-argued after
    the fact: an independent-error label caps attainable R2. A PASS is therefore
    strong evidence and a MISS is confounded. This asymmetry is the reason the
    gates in (b) constrain interpretation rather than the verdict.

(d) CLOUD AND CLOUD SHADOW. The Nairobi mosaic carries scattered cumulus. The
    working extent was chosen, before labelling, to contain no opaque cloud
    (measured: 0.0 fraction of pixels saturated in all three bands). Residual
    cloud SHADOW is semi-transparent -- roof structure stays visible beneath it
    -- so it is treated as an illumination variation, not an occlusion: shadowed
    patches are labelled by the surface underneath, and the feature stack
    already carries brightness-normalised terms (gex, rex) plus texture and
    coherence, which are the terms that survive a brightness drop. This is a
    stated modelling choice made in advance, not a post-hoc explanation.

(e) CROSS-SITE TRANSFER. With two labelled sites, item 21's revised acceptance
    ("`impervious_total` validated against a held-out AOI rather than against a
    same-AOI split") becomes testable. Transfer is reported for completeness at
    whatever it comes to; no bar is pre-registered for it, because two sites on
    two continents with two different sensors is too thin a base to set one
    honestly. It is reported as an observation, not scored.

RECORDED DEVIATIONS FROM THE ACCRA RUN
======================================
  * SENSOR. Accra was UAV at 0.05 m. Nairobi is VHR SATELLITE (Maxar, 0.3 m) --
    6x coarser, and satellite rather than airborne. It is still 33x finer than
    the 10 m S2 cell (~1,111 VHR pixels per S2 cell), which is what the label
    needs, but "UAV" is not an accurate description of this site and is not used.
  * PATCH RENDERING. Accra patches were inspected as bare 5 m crops, and its own
    first labelling pass was wrong because of it (flat roofs read as bare at 1x).
    Nairobi patches are rendered WITH CONTEXT: a 30 m surround with the scored
    patch boxed, so the class is judged in situ. This is a change to how a human
    looks at the imagery, not to what is measured.
  * S2 SAMPLING. Accra point-sampled 13,090 cells through `reduceRegions`. This
    extent has ~4x the cells, so the composite is fetched as an array on the
    exact same grid via `computePixels`. Semantics are identical -- same crs,
    same crsTransform -- and equivalence is VERIFIED against `reduceRegions` on
    a random subset rather than assumed. See `test_vhr_impervious_regression`.
"""

# --- pre-registered interpretation gates; fixed before any Nairobi result ---
LABEL_ACC_MIN = 0.711     # Accra's measured impervious-vs-not binary accuracy
TARGET_P50_MAX = 0.85     # Accra's median impervious fraction was 0.942
TARGET_SD_MIN = 0.20      # Accra's sd was 0.279
# ---------------------------------------------------------------------------

CLASSES = ["roof", "hard_unroofed", "vegetation", "bare", "water"]
IMPERVIOUS = {"roof", "hard_unroofed"}
NFEAT = 14

# Class definitions, fixed before labelling, and deliberately identical to the
# Accra run so the two labels mean the same thing:
#   roof           any roofed structure -- metal sheet, tile, concrete, thatch
#   hard_unroofed  sealed unroofed surface -- asphalt, concrete, paved yard
#   vegetation     trees, grass, crops, scrub
#   bare           permeable unpaved ground -- soil, dirt road, dirt yard
#   water          open water
# A DIRT ROAD IS `bare`, not `hard_unroofed`: Decision 11 defines `paved` as
# hard surface and `bare` as permeable unpaved ground, and the flood model
# downstream consumes exactly that distinction.


# ===========================================================================
# SITE REGISTRY
# ===========================================================================
import os

_OLD_SCRATCH = ("/private/tmp/claude-501/-Users-kanveermadan-geowatch/"
                "f0fb6a5f-62d2-4c09-93c4-806575bd5530/scratchpad")
_NEW_SCRATCH = ("/private/tmp/claude-501/-Users-kanveermadan-geowatch/"
                "9bd25d23-1fd4-4be1-b476-57a7d6efb46c/scratchpad")

# --- Old Fadama / Agbogbloshie, Accra -- the Phase 0 site -------------------
# Assignments below are the SECOND pass. The first was made at 1x zoom and
# contained real errors, which a held-out run exposed: bare recall was 0.29 and
# 2412 of 4375 bare pixels were predicted roof. Re-inspecting at 2x showed the
# classifier was frequently right and the labels wrong -- patches 14 and 63 are
# flat ROOFS with visible seams, and 50 and 55 are WATER with floating rubbish,
# all four of which the first pass called bare. Every patch was therefore
# re-assigned at 2x, and anything spanning two classes was discarded rather
# than forced. The discard lists are long for that reason.
_ACCRA_SHEETS = [
    # sheet 1 = 64 random patches
    ("patch_meta.json", {
        "roof": [0, 1, 3, 4, 5, 6, 7, 8, 10, 11, 12, 14, 16, 17, 18, 19, 24,
                 27, 29, 31, 33, 44, 47, 51, 52, 54, 61, 63],
        "hard_unroofed": [13, 38, 46],
        "vegetation": [20, 23, 28, 35, 48, 57, 59],
        "bare": [37, 40, 41, 53, 56, 58],
        "water": [43, 50, 55],
    }),  # discarded: 2,9,15,21,22,25,26,30,32,34,36,39,42,45,49,60,62
    # sheet 2 = 36 targeted patches (lagoon, highway/apron, vegetated block)
    ("patch_meta2.json", {
        "water": [0, 1, 2, 3, 4, 6, 7, 10, 11, 12],
        "hard_unroofed": [13, 14, 16, 17, 21, 23],
        "vegetation": [15, 24, 26, 28, 29, 30, 31, 32, 33, 34, 35],
        "bare": [],
        "roof": [19, 20],
    }),  # discarded: 5,8,9,18,22,25,27
    # sheet 3 = 36 patches near confirmed bare/hard
    ("patch_meta3.json", {
        "bare": [1, 2, 13, 14],
        "hard_unroofed": [4, 8, 9, 18, 19, 20, 24, 25, 26, 27, 30, 31, 32, 35],
        "roof": [7, 11, 17, 33, 34],
        "vegetation": [22],
        "water": [],
    }),  # discarded: 0,3,5,6,10,12,15,16,21,23,28,29
    # sheet 4 = 40 CLASSIFIER-PROPOSED bare/hard candidates. The classifier
    # proposed; every one was still verified by eye and 15 of 40 rejected.
    ("patch_meta4.json", {
        "bare": [1, 5, 12, 20, 25, 29, 31, 32, 33, 35, 37],
        "hard_unroofed": [4, 8, 19, 22, 28, 34, 38],
        "roof": [9, 13, 14, 15, 17, 23, 27],
        "vegetation": [],
        "water": [],
    }),  # discarded: 0,2,3,6,7,10,11,16,18,21,24,26,30,36,39
]

# --- Kibera + Kilimani, Nairobi -- the re-run site -------------------------
# Every patch was assigned by looking at it, rendered with 30 m of CONTEXT and
# the scored 6 m patch boxed (see `vhr_patch_sheets.py` for why context is
# shown). Anything spanning two classes was DISCARDED rather than forced; the
# discard lists below are long for that reason.
#
# Sheets 1-4 are random. Sheets 5-8 are targeted, because random sampling
# under-hits rare classes -- water is well under 1% of this extent. A target
# only PROPOSES locations and every proposal was still judged by eye:
#   5  the dam basin        6  the highway corridor
#   7  spectrally grey + smooth (asphalt/concrete), 0.14% of the extent
#   8  the dam basin again, re-centred on open water after sheet 5 under-hit it
#
# NINE tiles were re-rendered at 140-150 m context because 30 m did not settle
# them, and FOUR of those changed class as a result -- recorded here because
# the same check is what the Accra run had to do retrospectively:
#   sheet2 #17  water  -> bare   a bare-earth sports field, pitch markings and
#                                goalposts only visible at the wider view
#   sheet3 #18  discard-> roof   a long pink building, not a clay court
#   sheet7 #0   hard   -> bare   the red-earth embankment ABOVE the highway,
#                                not the carriageway
#   sheet5 #12  water  -> veg    the grassy embankment at the waterline
# and two were downgraded to discards (sheet7 #7 a dusty light roadway that
# could not be called sealed vs compacted; sheet6 #12 a verge strip).
#
# NOTE ON THE DAM. Its surface is largely covered by floating hyacinth and
# waste. Tiles on the mat were DISCARDED and only open dark water was called
# `water`. This is the same trap the Accra run fell into in reverse (it called
# rubbish-covered water `bare`), and it is harmless to the target either way --
# water and vegetation are both non-impervious. The damaging confusion is
# bare<->roof, and that is what the discards protect.
_KIBERA_SHEETS = [
    ("kib_meta1.json", {
        "roof": [1, 4, 5, 11, 12, 21],
        "hard_unroofed": [],
        "vegetation": [3, 8, 9, 10, 14, 15, 17, 18, 20, 22, 23],
        "bare": [2, 16, 19],
        "water": [],
    }),  # discarded: 0,6,7,13,24
    ("kib_meta2.json", {
        "roof": [2, 6, 7, 12, 13, 16, 19, 20],
        "hard_unroofed": [11, 21],
        "vegetation": [0, 3, 8, 9, 18, 22, 23, 24],
        "bare": [1, 14, 15, 17],
        "water": [],
    }),  # discarded: 4,10,5
    ("kib_meta3.json", {
        "roof": [6, 8, 18, 19],
        "hard_unroofed": [10, 17],
        "vegetation": [3, 5, 9, 16, 20, 22, 23, 24],
        "bare": [0, 14],
        "water": [],
    }),  # discarded: 1,2,4,11,12,13,15,21,7
    ("kib_meta4.json", {
        "roof": [1, 2, 5, 7, 10, 12, 14, 16, 22],
        "hard_unroofed": [],
        "vegetation": [4, 8, 19, 20, 21, 23, 24],
        "bare": [0, 3, 11, 13, 17],
        "water": [],
    }),  # discarded: 6,9,15,18
    ("kib_meta5.json", {
        "roof": [9, 14],
        "hard_unroofed": [],
        "vegetation": [5, 8, 12, 17, 19, 22],
        "bare": [3, 7, 10, 13, 16, 20, 24],
        "water": [0, 2, 18],
    }),  # discarded: 1,4,6,11,15,21,23
    ("kib_meta6.json", {
        "roof": [1, 11, 14, 17, 18, 19, 21, 22, 24],
        "hard_unroofed": [],
        "vegetation": [5, 8, 10, 23],
        "bare": [2, 6, 7, 13],
        "water": [],
    }),  # discarded: 0,3,4,9,12,15,16,20
    ("kib_meta7.json", {
        "roof": [1, 2, 3, 6, 8, 10, 18, 19, 21, 22, 23],
        "hard_unroofed": [4, 11, 12, 14, 20, 24],
        "vegetation": [],
        "bare": [0],
        "water": [],
    }),  # discarded: 5,7,9,13,15,16,17
    ("kib_meta8.json", {
        "roof": [17],
        "hard_unroofed": [],
        "vegetation": [3, 6, 21, 22, 23, 24],
        "bare": [],
        "water": [0, 2, 4, 8, 12, 13, 14],
    }),  # discarded: 1,5,7,9,10,11,15,16,18,19,20
    # sheet 9 = hard-negative round for `bare`, the weakest class after the
    # first refit (recall 0.53, 42% of bare pixels called impervious). Proposed
    # spectrally as reddish/tan low-texture ground -- the surfaces confused with
    # metal and painted roofing -- then assigned by eye. #17 is the valuable
    # one: a red-PAINTED church roof with lettering, which is exactly the case
    # the classifier was getting wrong in the damaging direction.
    ("kib_meta9.json", {
        "roof": [4, 17],
        "hard_unroofed": [],
        "vegetation": [5, 20],
        "bare": [0, 1, 3, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 21, 22, 23],
        "water": [],
    }),  # discarded: 2,6,16,24
]

SITES = {
    "oldfadama": dict(
        label="Old Fadama / Agbogbloshie, Accra",
        scratch=_OLD_SCRATCH,
        raster="oldfadama.tif",
        sensor="UAV (OpenAerialMap), 3-band RGB",
        acquired="2024-08-26",
        native_res_m=0.05,
        working_res_m=0.20,
        patch_m=5.0,
        bbox=[-0.225852, 5.541892, -0.214147, 5.556530],
        epsg="EPSG:32630",
        s2_start="2024-06-01",
        s2_end="2024-11-30",
        sheets=_ACCRA_SHEETS,
        meta_prefix="patch_meta",
    ),
    "kibera": dict(
        label="Kibera + Kilimani, Nairobi",
        scratch=_NEW_SCRATCH,
        raster="kibera.tif",
        sensor="VHR satellite, Maxar 2019 Nairobi Mosaic, 3-band RGB",
        acquired="2019-05-14",
        native_res_m=0.30,
        working_res_m=0.30,
        patch_m=6.0,
        # UTM 32737 extent 251460-253920 E, 9853600-9856040 N (2.46 x 2.44 km).
        # Chosen before labelling to span dense informal (Kibera), formal
        # residential, Ngong Forest, bare earth, road corridor and the Nairobi
        # Dam channel -- i.e. for DYNAMIC RANGE, which is what Accra lacked --
        # and shifted west of the first candidate to exclude opaque cloud.
        bbox=[36.7665, -1.3235, 36.7885, -1.3015],
        epsg="EPSG:32737",
        # brackets the 2019-05-14 acquisition
        s2_start="2019-02-14",
        s2_end="2019-08-14",
        sheets=_KIBERA_SHEETS,
        meta_prefix="kib_meta",
    ),
}

ACTIVE = os.environ.get("GW_SITE", "oldfadama")


def site(name=None):
    name = name or ACTIVE
    if name not in SITES:
        raise KeyError(f"unknown site {name!r}; have {sorted(SITES)}")
    s = dict(SITES[name])
    s["key"] = name
    s["raster_path"] = os.path.join(s["scratch"], s["raster"])
    s["ds"] = int(round(s["working_res_m"] / s["native_res_m"]))
    s["patch_native"] = int(round(s["patch_m"] / s["native_res_m"]))
    return s
