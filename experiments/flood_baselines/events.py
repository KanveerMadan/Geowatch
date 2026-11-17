"""
The development boxes for the baseline comparison: every event box already
cached by flood rounds 2-4, de-duplicated to one box per registry unit, and
gated on the flood-core registry (experiments/flood_core/registry).

Rules (no new data is read here):
  * Only registry units with role "dev" are returned. A "reserved" unit (the
    round-4b events) raises, wherever it appears, before any array is opened.
  * One box per unit: the latest round's box (round 4 > round 3 > round 2).
    Rounds 3 and 4 re-used each other's tuning boxes exactly, and round 4's
    boxes follow the latest box rule (centred on the reference's flood).
  * The reference (flooded, valid) and its evaluation block are the cached
    ones. Nothing about the reference is rebuilt or re-chosen.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np

from experiments.flood_core.registry import registry as REG
from experiments.flood_validation import references as R

ROUND_DIRS = (("round4", ("test", "tuning")), ("round3", ("",)), ("round2", ("",)))


class ReservedEventError(RuntimeError):
    """A reserved (unseen) event reached the baseline code."""


def _cached_files() -> list:
    """[(round, split, module, name, path)] for every cached event file."""
    out = []
    for rnd, splits in ROUND_DIRS:
        for split in splits:
            d = os.path.join(R.CACHE, rnd, split) if split else os.path.join(R.CACHE, rnd)
            for p in sorted(glob.glob(os.path.join(d, "*.npz"))):
                module, name = os.path.basename(p)[:-4].split("__", 1)
                out.append((rnd, split or None, module, name, p))
    return out


def gate(name: str, reg: dict) -> dict:
    """The registry unit for `name`. Raises unless it is a dev unit."""
    units = REG.units(reg)
    if name not in units:
        raise KeyError(f"{name}: not in the registry, so its role is unknown; refused")
    u = units[name]
    if u["role"] != "dev":
        raise ReservedEventError(f"{name}: registry role {u['role']!r}; only dev units are scored")
    return u


def _meta(path: str) -> dict:
    z = np.load(path, allow_pickle=False)
    return json.loads(str(z["meta"]))


def catalogue(reg: dict | None = None) -> list:
    """[{unit, round, split, modules, path, meta}] -- one box per dev unit.

    `modules` lists every module whose cached file in the chosen round has
    the same box (e.g. Valencia's pluvial and flash-flood files)."""
    reg = reg or REG.load()
    files = _cached_files()
    for _, _, _, name, _ in files:        # gate everything before reading any array
        gate(name, reg)
    chosen = {}
    for rnd, split, module, name, path in files:     # ROUND_DIRS order = priority
        m = _meta(path)
        if name not in chosen:
            chosen[name] = {"unit": name, "round": rnd, "split": split, "modules": [module],
                            "path": path, "meta": m, "uses": [(rnd, split, module)]}
            continue
        c = chosen[name]
        c["uses"].append((rnd, split, module))
        if rnd == c["round"] and m["bbox"] == c["meta"]["bbox"] and module not in c["modules"]:
            c["modules"].append(module)
    return [chosen[k] for k in sorted(chosen)]


def reference(entry: dict) -> dict:
    """The cached reference arrays and evaluation block of a catalogue entry."""
    z = np.load(entry["path"], allow_pickle=False)
    return {"flooded": z["flooded"].astype(bool), "valid": z["valid"].astype(bool),
            "block": int(entry["meta"].get("block", 1))}


def mechanism(entry: dict, reg: dict) -> list:
    """The modules this unit was used for in any round (its documented
    mechanism(s)), from the registry's `uses`, excluding r1 'site' rows."""
    u = REG.units(reg)[entry["unit"]]
    return sorted({x["module"] for x in u.get("uses", []) if x.get("role") != "site"})


def clusters(names: list, reg: dict) -> dict:
    """{name: cluster id}: connected components among `names` under ANY
    registry link (block or exception level). The registry README calls this
    the effective sample size; units in one cluster are not independent."""
    units = REG.units(reg)
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if REG.links(units[a], units[b]):
                parent[find(a)] = find(b)
    roots = {}
    return {n: roots.setdefault(find(n), len(roots)) for n in names}
