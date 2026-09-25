"""
Configuration for the item 21 Phase A surface-fraction pipeline.

Every threshold lives in configs/fractions.yaml, never in code. See that
file's header for the CITED / MEASURED / UNSET rule.
"""

from __future__ import annotations

import os

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(REPO_ROOT, "configs", "fractions.yaml")


def load_config(path: str | None = None) -> dict:
    with open(path or DEFAULT_CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


def aoi_config(cfg: dict, name: str) -> dict:
    try:
        aoi = dict(cfg["aois"][name])
    except KeyError:
        raise KeyError(f"AOI {name!r} is not in configs/fractions.yaml "
                       f"(known: {sorted(cfg['aois'])})") from None
    aoi["name"] = name
    return aoi
