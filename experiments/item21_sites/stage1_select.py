"""
Item 21 Stage 1 tile selection (decided 2026-09-29; 05_BUILD_MANUAL.md item
21, "Decisions after Pilot A", 5).

Per training site, the frozen sampler (labelling.tiles.build_frame, seed
tiles.random_seed) ranks the eligible tiles of each stratum. For each stratum
in configs/labelling.yaml stage1_tiles, the first tile in rank order is taken
unless the frozen §9.1 change test drops it; then the next rank replaces it.
A dropped tile is recorded and is never relabelled.

Inputs are the frozen ones: strata.gpkg (hash-checked), the real-data frame
(data/strata_packages/<site>/frame.geojson), and the change-test decisions of
experiments/item21_sites/results/pilot_a_detrended.json (the frozen rule's
implementation). The sampler's tiles are checked against both.

Writes (refusing to overwrite):
  data/frames/<site>_frame.json   the sampler frame with its run metadata
  data/stage1/selection.json      the 8 tiles, the ranks walked, the drops

    python experiments/item21_sites/stage1_select.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

CHANGE_TEST = os.path.join(HERE, "results", "pilot_a_detrended.json")
FRAMES = os.path.join(REPO, "data", "frames")
OUT = os.path.join(REPO, "data", "stage1", "selection.json")


def frame_geometry(site: str):
    from shapely.geometry import shape
    from shapely.ops import unary_union
    with open(os.path.join(REPO, "data", "strata_packages", site, "frame.geojson")) as fh:
        fc = json.load(fh)
    return unary_union([shape(f["geometry"]) for f in fc["features"]])


def pick(ranked: list, decisions: dict) -> tuple:
    """Walk `ranked` (rank order); return (chosen tile, dropped tiles). A tile
    with no change-test decision is an error, never a silent keep."""
    dropped = []
    for t in ranked:
        d = decisions.get(t["tile_id"])
        if d is None or d["dropped"] is None:
            raise RuntimeError(f"{t['tile_id']}: no change-test decision")
        if d["dropped"]:
            dropped.append({**t, "change_test": d})
            continue
        return {**t, "change_test": d}, dropped
    raise RuntimeError("every tile in the stratum was dropped by the change test")


def run_site(site: str, cfg: dict, ct: dict) -> dict:
    import pyogrio
    from labelling.strata_io import load_strata
    from labelling.strata_style import UNASSIGNED
    from labelling.tiles import build_frame, save_frame, site_box
    gpkg = os.path.join(REPO, "data", "strata_packages", site, "strata.gpkg")
    strata, _ = load_strata(gpkg, site, cfg)                    # hash-checked (FROZEN)
    crs, box = site_box(site, cfg)
    frame = build_frame(site, crs, box.bounds, strata, cfg, frame_geometry(site))

    # the sampler's tiles must be exactly the frozen strata's assigned tiles
    g = pyogrio.read_dataframe(gpkg, layer="strata")
    frozen = {t: s for t, s in zip(g.tile_id, g.stratum) if s != UNASSIGNED}
    sampled = {t["tile_id"]: t["stratum"] for t in frame["tiles"]}
    if sampled != frozen:
        raise RuntimeError(f"{site}: sampler tiles differ from the frozen strata "
                           f"({len(set(sampled) ^ set(frozen))} tile ids differ)")
    decisions = {r["tile_id"]: r for r in ct["sites"][site]["tiles"]}
    if set(decisions) != set(sampled):
        raise RuntimeError(f"{site}: change-test tiles differ from the sampler's")

    os.makedirs(FRAMES, exist_ok=True)
    fpath = os.path.join(FRAMES, f"{site}_frame.json")
    if not os.path.exists(fpath):
        save_frame(frame, fpath, cfg)

    plan = cfg["stage1_tiles"]
    out = {"site": site, "random_seed": frame["random_seed"], "frame_file": os.path.relpath(fpath, REPO),
           "strata": {}}
    for stratum in plan["strata_per_site"][site]:
        ranked = sorted((t for t in frame["tiles"] if t["stratum"] == stratum),
                        key=lambda t: t["rank_in_stratum"])
        if len(ranked) < plan["min_eligible_per_stratum"]:
            raise RuntimeError(f"{site}/{stratum}: {len(ranked)} eligible tiles < "
                               f"{plan['min_eligible_per_stratum']}")
        chosen, dropped = pick(ranked, decisions)
        keep = ("tile_id", "x0", "y1", "stratum", "rank_in_stratum")
        ct_keep = ("share", "changed", "evaluable", "dropped")
        out["strata"][stratum] = {
            "eligible": len(ranked),
            "chosen": {**{k: chosen[k] for k in keep},
                       "change_test": {k: chosen["change_test"][k] for k in ct_keep}},
            "dropped_by_change_test": [{**{k: t[k] for k in keep},
                                        "change_test": {k: t["change_test"][k] for k in ct_keep}}
                                       for t in dropped],
        }
    return out


def main():
    from labelling.common import load_config
    from labelling.tiles import config_sha256, git_head
    cfg = load_config()
    with open(CHANGE_TEST) as fh:
        ct = json.load(fh)
    rule = cfg["open"]["change_test"]
    assert rule["status"] == "FROZEN" and (ct["rule"]["k"], ct["rule"]["drop_if_changed_share_above"]) == \
        (rule["change"]["k"], rule["drop_tile_if_changed_share_above"])
    if os.path.exists(OUT):
        raise SystemExit(f"{OUT} exists: the Stage 1 selection is a fixed record")
    sel = {"decided": cfg["stage1_tiles"]["decided"], "guide_version": cfg["guide_version"],
           "labelling_config_sha256": config_sha256(), "git_head": git_head(),
           "change_test_source": os.path.relpath(CHANGE_TEST, REPO), "sites": {}}
    for site in cfg["stage1_tiles"]["strata_per_site"]:
        sel["sites"][site] = run_site(site, cfg, ct)
        for s, r in sel["sites"][site]["strata"].items():
            c = r["chosen"]
            print(f"{site:10s} {s:15s} rank {c['rank_in_stratum']} {c['tile_id']} "
                  f"changed {c['change_test']['share']:.1%}; dropped before it: "
                  f"{[d['tile_id'] for d in r['dropped_by_change_test']]}", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "x") as fh:
        json.dump(sel, fh, indent=1)
    print(OUT)


if __name__ == "__main__":
    main()
