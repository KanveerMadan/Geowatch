"""
Stratified random tile frame (LABELLING_GUIDE.md §3).

Tiles are 200 m squares (20 x 20 Sentinel-2 cells) whose edges sit on
multiples of 200 m in the native UTM grid, so a tile ID is stable across
runs and every tile is aligned to the exact Sentinel-2 grid.

Sampling is split in two so the random order exists before any count:

  build_frame   every eligible tile, its stratum, and a seeded random rank
                within its stratum. Fixed once, recorded.
  select        the first N per stratum from that frame. N is the §9.3 open
                number (UNSET until decided), and LOCO decides after that.

A tile is eligible only if it lies entirely inside the imagery footprint
(every pixel must be labellable, §3) when one is given, and a stratum can be
assigned to it.
"""

from __future__ import annotations

import math

import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union

from labelling.common import OpenNumberUnset, require_open
from surface_fractions.grid import S2_RESOLUTION_M, Grid


def tile_id(crs: str, x0: float, y1: float) -> str:
    return f"{crs.replace(':', '')}_{int(x0)}_{int(y1)}"


def tile_grid(crs: str, x0: float, y1: float, size_m: float) -> Grid:
    n = int(round(size_m / S2_RESOLUTION_M))
    return Grid(crs=crs, transform=(float(S2_RESOLUTION_M), 0.0, float(x0), 0.0,
                                    -float(S2_RESOLUTION_M), float(y1)),
                width=n, height=n)


def tile_origins(bounds: tuple, size_m: float) -> list:
    """(x0, y1) of every whole tile inside `bounds` (grid CRS), on the
    size_m lattice anchored at 0 -- which lies on the 10 m S2 lattice."""
    minx, miny, maxx, maxy = bounds
    xs = range(math.ceil(minx / size_m), math.floor(maxx / size_m))
    ys = range(math.ceil(miny / size_m) + 1, math.floor(maxy / size_m) + 1)
    return [(i * size_m, j * size_m) for i in xs for j in ys]


def assign_stratum(tile, strata: dict, rule: str) -> tuple:
    """-> (stratum or None, {stratum: area share of the tile})."""
    if rule != "plurality":
        raise ValueError(f"unknown stratum_assignment {rule!r}")
    shares = {name: tile.intersection(geom).area / tile.area
              for name, geom in strata.items()}
    shares = {k: v for k, v in shares.items() if v > 0}
    if not shares:
        return None, shares
    top = max(shares.values())
    winners = [k for k, v in shares.items() if v == top]
    return (winners[0] if len(winners) == 1 else None), shares


def build_frame(site: str, crs: str, bounds: tuple, strata: dict, cfg: dict,
                footprint=None) -> dict:
    """strata: {stratum name: shapely geometry in `crs`} from the hand-drawn
    GeoJSON. footprint: optional imagery coverage geometry in `crs`."""
    tcfg = cfg["tiles"]
    unknown = set(strata) - set(tcfg["strata"])
    if unknown:
        raise ValueError(f"strata {sorted(unknown)} are not in the guide's {tcfg['strata']}")
    size = tcfg["size_m"]
    strata = {k: unary_union(v) if isinstance(v, (list, tuple)) else v for k, v in strata.items()}
    tiles, ineligible = [], {"outside_footprint": 0, "no_stratum": 0, "tied_strata": 0}
    for x0, y1 in tile_origins(bounds, size):
        t = box(x0, y1 - size, x0 + size, y1)
        if footprint is not None and not footprint.contains(t):
            ineligible["outside_footprint"] += 1
            continue
        stratum, shares = assign_stratum(t, strata, tcfg["stratum_assignment"])
        if stratum is None:
            ineligible["tied_strata" if shares else "no_stratum"] += 1
            continue
        tiles.append({"tile_id": tile_id(crs, x0, y1), "x0": x0, "y1": y1,
                      "stratum": stratum, "stratum_shares": shares})
    rng = np.random.default_rng(tcfg["random_seed"])
    for s in tcfg["strata"]:
        members = sorted((t for t in tiles if t["stratum"] == s), key=lambda t: t["tile_id"])
        for rank, i in enumerate(rng.permutation(len(members))):
            members[i]["rank_in_stratum"] = rank
    return {"site": site, "crs": crs, "tile_size_m": size,
            "random_seed": tcfg["random_seed"],
            "stratum_assignment": tcfg["stratum_assignment"],
            "tiles": sorted(tiles, key=lambda t: (t["stratum"], t["rank_in_stratum"])),
            "ineligible": ineligible}


def config_sha256(path: str | None = None) -> str:
    import hashlib
    from labelling.common import DEFAULT_CONFIG_PATH
    with open(path or DEFAULT_CONFIG_PATH, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def git_head() -> str | None:
    import subprocess
    from surface_fractions.config import REPO_ROOT
    try:
        return subprocess.run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 -- metadata only, never fail a save on it
        return None


def save_frame(frame: dict, path: str, cfg: dict) -> str:
    """Write the frame with its run metadata, including the sampler seed
    (ruling 2026-09-25, second round, 6). Refuses to overwrite: a frame, once
    fixed, is the record the counts are later drawn from."""
    import json
    from datetime import datetime, timezone
    record = {
        "run_metadata": {
            "tile_sampler_seed": frame["random_seed"],
            "stratum_assignment": frame["stratum_assignment"],
            "tile_size_m": frame["tile_size_m"],
            "guide_version": cfg["guide_version"],
            "labelling_config_sha256": config_sha256(),
            "git_head": git_head(),
            "created_utc": datetime.now(timezone.utc).isoformat(),
        },
        "frame": frame,
    }
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    return path


def select(frame: dict, cfg: dict, counts: dict | None = None) -> list:
    """First N tiles per stratum by rank. N comes from the §9.3 open number
    unless `counts` is given explicitly (e.g. a later LOCO-driven top-up)."""
    if counts is None:
        counts = require_open(cfg, "starting_tile_count", "per_stratum")
    out = []
    for stratum, n in counts.items():
        pool = [t for t in frame["tiles"] if t["stratum"] == stratum]
        if n > len(pool):
            raise ValueError(f"{stratum}: asked for {n}, frame has {len(pool)}")
        out += sorted(pool, key=lambda t: t["rank_in_stratum"])[:n]
    return out


def qc_selection(tiles: list, cfg: dict, seed: int | None = None) -> list:
    """~15% of labelled tiles for blind re-labelling (§7), at least one."""
    frac = cfg["qc"]["blind_relabel_fraction"]
    n = max(1, round(frac * len(tiles))) if tiles else 0
    rng = np.random.default_rng(cfg["tiles"]["random_seed"] if seed is None else seed)
    ids = sorted(t["tile_id"] for t in tiles)
    return sorted(ids[i] for i in rng.choice(len(ids), size=n, replace=False))


__all__ = ["OpenNumberUnset", "build_frame", "select", "qc_selection", "tile_grid"]
