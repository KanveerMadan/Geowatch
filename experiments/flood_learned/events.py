"""
The training events for the learned flood model, their folds and settings.

Batch 0 = the 29 clean cached development events: every qualifying unit of
experiments/flood_baselines (>= 50 flooded and >= 50 dry evaluation cells)
MINUS the five whose reference is JRC GSW occurrence itself (accra,
capetown, dhaka, hcmc, nusantara; flood_baselines REPORT A3). Using those
five would put the label into a feature (JRC occurrence/recurrence).

Every unit passes the flood-core registry gate (flood_baselines.events.gate)
before any array is opened, so a reserved event cannot be read here.

Folds
  * leave-cluster-out ("event" split): the registry's link clusters
    (flood_baselines.events.clusters). Linked units -- the same EMS product,
    intersecting boxes or the same storm (paiporta = valencia_2024's AOI03;
    derna/derna_2023/volos = Storm Daniel; the four Typhoon Yagi boxes) --
    are always held out together.
  * leave-region-out: UN M49 regions (UN Statistics Division, "Standard
    country or area codes for statistical use"), grouped so that no registry
    cluster spans two regions. Storm Daniel links Libya and Greece, so
    Northern Africa joins Southern Europe ("Europe & Mediterranean").

Settings (event-level tags, each from a published rule; settings.py computes
the inputs from Earth Engine and stores them per event):
  urban / peri-urban / rural  GHSL GHS-SMOD 2020 (Degree of Urbanisation,
                              UN Statistical Commission 2020): the box's
                              most common settlement class.
  mountain                    Kapos et al. (2000) / UNEP-WCMC mountain classes.
  arid                        Koppen-Geiger group B (Peel et al. 2007, HESS 11:1633).
  coastal                     within the project's existing coastal applicability
                              distance (COASTAL_APPLICABILITY_THRESHOLD_KM, 10 km)
                              of the sat-io shoreline AND box median elevation
                              <= 10 m (the Low Elevation Coastal Zone's 10 m;
                              McGranahan et al. 2007).
  delta                       on a delta of Tessler et al. (2015, Science 349:638)
                              -- assigned by location, listed in DELTA_UNITS.
"""
from __future__ import annotations

import os

import numpy as np

from experiments.flood_baselines import build as BUILD
from experiments.flood_baselines import events as BE
from experiments.flood_core.registry import registry as REG

# The five round-2 waterlogging units whose reference is JRC occurrence
# (flood_baselines REPORT A3). Never used as flood labels here.
JRC_REFERENCE_UNITS = ("accra", "capetown", "dhaka", "hcmc", "nusantara")

# UN M49 region per unit (by the box's country), grouped as described above.
REGION = {
    # Southern Asia
    "assam_2026": "south_asia", "bihar_2026": "south_asia", "dharavi": "south_asia",
    "himachal_2023": "south_asia", "kerala_2018": "south_asia", "kolonnawa": "south_asia",
    "pakistan_2022": "south_asia", "sylhet_2022": "south_asia",
    # South-eastern Asia
    "hai_phong": "southeast_asia", "hanoi": "southeast_asia", "nam_dinh": "southeast_asia",
    "thai_binh": "southeast_asia", "kyaukpyu": "southeast_asia", "sittwe": "southeast_asia",
    # Europe + Northern Africa (Storm Daniel links Derna and Volos)
    "bad_neuenahr": "europe_mediterranean", "faenza": "europe_mediterranean",
    "paiporta": "europe_mediterranean", "valencia_2024": "europe_mediterranean",
    "volos": "europe_mediterranean", "derna": "europe_mediterranean",
    "derna_2023": "europe_mediterranean",
    # Latin America and the Caribbean + Northern America
    "belize_city": "americas", "choloma": "americas", "black_river": "americas",
    "fort_myers_beach": "americas", "encantado": "americas", "milagro": "americas",
    # Sub-Saharan Africa + Western Asia
    "beira": "africa_west_asia", "dubai_2024": "africa_west_asia",
}

# Units on a Tessler et al. (2015) delta: the Red River (Song Hong) delta.
DELTA_UNITS = ("hai_phong", "hanoi", "nam_dinh", "thai_binh")

# Flood types the brief asks about, from the registry's documented mechanism.
FLOOD_TYPES = ("pluvial", "waterlogging", "flash_flood", "fluvial", "coastal")


def batch0(reg: dict | None = None) -> list:
    """Catalogue entries (flood_baselines.events.catalogue) of the 29 clean
    events, gated, with the cached baseline inputs present."""
    reg = reg or REG.load()
    out = []
    for c in BE.catalogue(reg):
        if c["unit"] in JRC_REFERENCE_UNITS:
            continue
        if not os.path.exists(BUILD.path(c["unit"])):
            continue
        if not BUILD.qualifies(c):
            continue
        out.append(c)
    return out


def labels(entry: dict, jrc_occurrence: np.ndarray) -> np.ndarray:
    """Per 30 m cell: 1 flooded, 0 dry, -1 unobserved. Unobserved (the
    reference's invalid cells) is never dry. Permanent water (JRC occurrence
    >= JRC_PERMANENT_WATER_OCCURRENCE_PCT, 80 %) is unobserved as well, even
    where a reference did not already exclude it."""
    from experiments.flood_validation import references as R
    ref = BE.reference(entry)
    if ref["block"] != 1:
        raise ValueError(f"{entry['unit']}: evaluation block {ref['block']} != 1 is not "
                         "handled (no batch-0 unit has one)")
    lab = np.full(ref["flooded"].shape, -1, np.int8)
    ok = ref["valid"] & R.not_permanent(np.asarray(jrc_occurrence, np.float64))
    lab[ok & ref["flooded"]] = 1
    lab[ok & ~ref["flooded"]] = 0
    return lab


def clusters(names: list, reg: dict | None = None) -> dict:
    return BE.clusters(names, reg or REG.load())


def region(name: str) -> str:
    if name not in REGION:
        raise KeyError(f"{name}: no region assigned (add it to REGION with its M49 basis)")
    return REGION[name]


def check_folds(names: list, cluster_of: dict) -> None:
    """Raise if a registry cluster spans two regions (leave-region-out would
    then train on a linked unit of a held-out one)."""
    seen = {}
    for n in names:
        c, r = cluster_of[n], region(n)
        if seen.setdefault(c, r) != r:
            raise ValueError(f"cluster {c} spans regions {seen[c]} and {r} ({n})")
