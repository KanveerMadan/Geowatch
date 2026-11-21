"""
Build experiments/flood_core/registry/events.json (flood-core prototype).

Sources, all already in the repo: the pinned result files of rounds 1-4
(boxes, dates, reference products) and the pre-registrations (roles, the
round-4b reserved events). The curated table below adds what no file holds:
storm and region clusters, exposure levels, and approximate place points for
the reserved events.

Reserved events get NO box: the box rule derives a box from the reference's
flood geometry, which must not be read before a registered run. Their point
is an approximate town location from general geography, marked as such.

Exposure ladder (highest level reached; see README.md):
  0 unseen  1 facts/news  2 product metadata  3 reference geometry/counts
  4 scored  5 tuning or method choice  6 post-hoc diagnostics viewed
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FV = os.path.join(HERE, "..", "..", "flood_validation")
RESULTS = {"r2": "result_round2_2026-10-28.json", "r3": "result_round3_2026-10-29.json",
           "r4": "result_round4_2026-10-30.json"}

# name: (event date, storm cluster, region cluster, kind, exposure, [(round, module, role)], products)
CURATED = {
    # round-1 sites and round-2 JRC tuning AOIs (city climatology, not single events)
    "dharavi": ("2017-08-29", "mumbai_2017", "mumbai", "event+site", 5,
                [("r1", "pluvial", "test"), ("r1", "fluvial", "site"), ("r1", "waterlogging", "site"),
                 ("r2", "pluvial", "tuning"), ("r2", "waterlogging", "tuning")], ["S1"]),
    "jakarta": (None, None, "jakarta", "site", 4, [("r1", "fluvial", "site"), ("r1", "waterlogging", "site")], ["JRC"]),
    "jakarta_gfd_3280": ("2008-03-01", "jakarta_2008", "jakarta", "event", 4,
                         [("r2", "waterlogging", "held_out")], ["GFD:3280"]),
    **{c: (None, None, c, "site", 5, [("r1", "fluvial", "site"), ("r1", "waterlogging", "site"),
                                      ("r2", "waterlogging", "tuning")], ["JRC"])
       for c in ("hcmc", "kigali", "accra", "dhaka", "capetown", "guatemala", "nusantara")},
    # coastal
    "beira": ("2019-03-15", "idai_2019", "mozambique_coast", "event", 4,
              [("r1", "coastal", "test"), ("r2", "coastal", "held_out")], ["S1"]),
    "chennai_velachery": ("2023-12-04", "michaung_2023", "chennai", "event", 2,
                          [("r1", "coastal", "test_not_run")], ["S1"]),
    "chennai_2023": ("2023-12-04", "michaung_2023", "chennai", "event", 2,
                     [("r4", "pluvial", "test_not_run")], []),
    "fort_myers_beach": ("2022-09-28", "ian_2022", "florida_gulf", "event", 4,
                         [("r1", "coastal", "test"), ("r2", "coastal", "held_out")], ["S1"]),
    "kyaukpyu": ("2023-05-14", "mocha_2023", "rakhine", "event", 5, [("r2", "coastal", "tuning")], ["EMSR661:AOI02"]),
    "sittwe": ("2023-05-14", "mocha_2023", "rakhine", "event", 4, [("r2", "coastal", "held_out")], ["EMSR661:AOI01"]),
    "black_river": ("2025-10-28", "melissa_2025", "jamaica", "event", 4, [("r2", "coastal", "held_out")], ["EMSR847:AOI15"]),
    # flash flood
    "paiporta": ("2024-10-29", "dana_valencia_2024", "valencia", "event", 5,
                 [("r1", "flash_flood", "test"), ("r2", "flash_flood", "tuning")], ["S1", "EMSR773:AOI03"]),
    "valencia_2024": ("2024-10-29", "dana_valencia_2024", "valencia", "event", 6,
                      [("r4", "pluvial", "test"), ("r4", "flash_flood", "test")], ["EMSR773:AOI03"]),
    "derna": ("2023-09-11", "daniel_2023", "derna", "event", 5,
              [("r1", "flash_flood", "test"), ("r2", "flash_flood", "tuning")], ["S1"]),
    "derna_2023": ("2023-09-11", "daniel_2023", "derna", "event", 6, [("r4", "flash_flood", "test")], ["EMSR696:AOI01"]),
    "bad_neuenahr": ("2021-07-14", "bernd_2021", "ahr", "event", 5,
                     [("r1", "flash_flood", "test"), ("r2", "flash_flood", "tuning")], ["S1"]),
    "volos": ("2023-09-05", "daniel_2023", "thessaly", "event", 5,
              [("r2", "flash_flood", "held_out"), ("r3", "flash_flood", "held_out"), ("r4", "flash_flood", "tuning")],
              ["EMSR692:AOI01"]),
    "kastelli": ("2026-10-01", "crete_2026", "crete", "event", 5,
                 [("r2", "flash_flood", "held_out"), ("r3", "flash_flood", "held_out"), ("r4", "flash_flood", "tuning")],
                 ["EMSR933:AOI01"]),
    "choloma": ("2024-11-16", "sara_2024", "sula_valley", "event", 5,
                [("r2", "flash_flood", "held_out"), ("r3", "flash_flood", "held_out"), ("r4", "flash_flood", "tuning")],
                ["EMSR778:AOI10"]),
    "himachal_2023": ("2023-07-10", "monsoon_2023_wh", "beas", "event", 6, [("r4", "flash_flood", "test")], ["S1"]),
    # pluvial
    "hai_phong": ("2024-09-07", "yagi_2024", "red_river_delta", "event", 5,
                  [("r2", "pluvial", "held_out"), ("r3", "pluvial", "held_out"), ("r4", "pluvial", "tuning")],
                  ["EMSR754:AOI05"]),
    "milagro": ("2025-02-26", "ecuador_2025", "guayas", "event", 5,
                [("r2", "pluvial", "held_out"), ("r3", "pluvial", "held_out"), ("r4", "pluvial", "tuning")],
                ["EMSR796:AOI06"]),
    "belize_city": ("2024-11-15", "sara_2024", "belize", "event", 5,
                    [("r2", "pluvial", "held_out"), ("r3", "pluvial", "held_out"), ("r4", "pluvial", "tuning")],
                    ["EMSR777:AOI01"]),
    "dubai_2024": ("2024-04-16", "uae_2024", "dubai", "event", 6, [("r4", "pluvial", "test")], ["S1"]),
    # fluvial
    "faenza": ("2023-05-02", "emilia_2023", "lamone", "event", 5, [("r2", "fluvial", "tuning")], ["EMSR659:AOI02"]),
    "encantado": ("2024-05-02", "rs_2024", "taquari", "event", 5, [("r2", "fluvial", "tuning")], ["EMSR720:AOI02"]),
    "hanoi": ("2024-09-09", "yagi_2024", "red_river_delta", "event", 4, [("r2", "fluvial", "held_out")], ["EMSR754:AOI03"]),
    "kolonnawa": ("2025-11-30", "ditwah_2025", "kelani", "event", 4, [("r2", "fluvial", "held_out")], ["EMSR851:AOI02"]),
    "nysa": ("2024-09-14", "boris_2024", "odra", "event", 4, [("r2", "fluvial", "held_out")], ["EMSR756:AOI03"]),
    "hue": ("2025-10-29", "vn_central_2025", "perfume", "event", 4, [("r2", "fluvial", "held_out")], ["EMSR848:AOI06"]),
    "bihar_2026": ("2026-09-11", "kosi_sep_2026", "gbm_system", "event", 6, [("r4", "fluvial", "test")], ["S1"]),
    "assam_2026": ("2026-07-20", "nagaland_cloudburst_jul_2026", "gbm_system", "event", 6,
                   [("r4", "fluvial", "test"), ("r4", "waterlogging", "test")], ["S1"]),
    "pakistan_2022": ("2022-08-31", "monsoon_2022_pk", "indus", "event", 6, [("r4", "fluvial", "test")],
                      ["UNOSAT:FL20220808PAK"]),
    # waterlogging
    "thai_binh": ("2024-09-09", "yagi_2024", "red_river_delta", "event", 5,
                  [("r2", "waterlogging", "held_out"), ("r3", "waterlogging", "held_out"),
                   ("r4", "waterlogging", "tuning")], ["EMSR754:AOI06"]),
    "nam_dinh": ("2024-09-09", "yagi_2024", "red_river_delta", "event", 5,
                 [("r2", "waterlogging", "held_out"), ("r3", "waterlogging", "held_out"),
                  ("r4", "waterlogging", "tuning")], ["EMSR754:AOI07"]),
    "sylhet_2022": ("2022-06-18", "monsoon_2022_bd", "gbm_system", "event", 6, [("r4", "waterlogging", "test")],
                    ["UNOSAT:FL20220525BGD"]),
    "kerala_2018": ("2018-08-16", "monsoon_2018_kl", "kuttanad", "event", 6, [("r4", "waterlogging", "test")], ["S1"]),
}
# The dhaka JRC site sits in the GBM delta: region cluster overridden.
REGION_OVERRIDE = {"dhaka": "gbm_system"}

# Round-4b reserved events: facts and product metadata only (PREREGISTRATION_ROUND4B.md).
RESERVED = {
    "noakhali_2024": {"date": "2024-08-25", "storm": "bd_aug_2024", "region": "gbm_system",
                      "products": ["UNOSAT:FL20240825BGD"], "point_approx": [91.10, 22.87],
                      "point_note": "Maijdee/Noakhali town, approximate, general geography; not from any reference"},
    "calais_2023": {"date": "2023-11-07", "storm": "ciaran_domingos_2023", "region": "aa_wateringues",
                    "products": ["EMSR706:AOI01"], "point_approx": [1.86, 50.95],
                    "point_note": "Calais town, approximate, general geography; not from any reference"},
    "redon_2025": {"date": "2025-01-30", "storm": "herminia_2025", "region": "vilaine",
                   "products": ["EMSR788:AOI06"], "point_approx": [-2.08, 47.65],
                   "point_note": "Redon town, approximate, general geography; not from any reference"},
}
# Product metadata looked at without an event unit (4b pre-registration).
METADATA_ONLY_PRODUCTS = ["EMSR712"]

# Fixed boxes for round-1-only sites (vector/aois.py BASELINE_AOIS; PREREGISTRATION.md).
R1_BOXES = {"jakarta": [106.78, -6.13, 106.85, -6.08], "chennai_velachery": [80.20, 12.96, 80.24, 13.00],
            "derna": [22.62, 32.75, 22.66, 32.78], "bad_neuenahr": [7.09, 50.53, 7.13, 50.56],
            "beira": [34.83, -19.85, 34.87, -19.81], "fort_myers_beach": [-81.97, 26.43, -81.93, 26.47],
            "paiporta": [-0.44, 39.41, -0.40, 39.45], "dharavi": [72.836, 19.037, 72.862, 19.06]}


def boxes_from_results() -> dict:
    out = {}
    for rnd, f in RESULTS.items():
        d = json.load(open(os.path.join(FV, f)))
        for mod, v in d["modules"].items():
            evs = dict(v.get("events") or {})
            evs.update((v.get("tuning") or {}).get("events") or {})
            for name, e in evs.items():
                if isinstance(e, dict) and e.get("bbox"):
                    bb = [round(float(x), 6) for x in e["bbox"]]
                    if bb not in [b["bbox"] for b in out.get(name, [])]:
                        out.setdefault(name, []).append({"round": rnd, "module": mod, "bbox": bb})
    return out


def build() -> dict:
    boxes = boxes_from_results()
    units = []
    for name, (date, storm, region, kind, exp, uses, products) in CURATED.items():
        geoms = list(boxes.get(name, []))
        if name in R1_BOXES and R1_BOXES[name] not in [g["bbox"] for g in geoms]:
            geoms.insert(0, {"round": "r1", "module": "site", "bbox": R1_BOXES[name]})
        geometry = ({"type": "boxes", "boxes": geoms} if geoms else
                    {"type": "none", "note": "never boxed: not-run before any reference was read"})
        units.append({"event_id": name, "role": "dev", "kind": kind, "date": date,
                      "storm_cluster": storm, "region_cluster": REGION_OVERRIDE.get(name, region),
                      "products": products, "uses": [{"round": r, "module": m, "role": ro} for r, m, ro in uses],
                      "exposure_level": exp, "geometry": geometry})
    for name, r in RESERVED.items():
        units.append({"event_id": name, "role": "reserved", "kind": "event", "date": r["date"],
                      "storm_cluster": r["storm"], "region_cluster": r["region"], "products": r["products"],
                      "uses": [{"round": "r4b", "module": "waterlogging", "role": "registered_test"}],
                      "exposure_level": 2,
                      "exposure_note": "PREREGISTRATION_ROUND4B.md: event facts, product lists, layer names; "
                                       "Noakhali also one attribute row of the flood layer. No geometry.",
                      "geometry": {"type": "point_approx", "point": r["point_approx"], "note": r["point_note"]}})
    # flood_final DEV and RESERVED units (experiments/flood_final/register_final.py),
    # kept on a registry rebuild.
    heldout = os.path.join(HERE, "..", "..", "flood_final", "registry_units.json")
    if os.path.exists(heldout):
        with open(heldout) as fh:
            units.extend(json.load(fh)["units"])
    return {"schema_version": 1, "built_from": list(RESULTS.values()) + ["PREREGISTRATION*.md"],
            "metadata_only_products": METADATA_ONLY_PRODUCTS,
            "exposure_ladder": {0: "unseen", 1: "facts/news", 2: "product metadata", 3: "reference geometry/counts",
                                4: "scored", 5: "tuning or method choice", 6: "post-hoc diagnostics viewed"},
            "units": units}


if __name__ == "__main__":
    reg = build()
    with open(os.path.join(HERE, "events.json"), "w") as f:
        json.dump(reg, f, indent=1)
    print(len(reg["units"]), "units written")
