"""Shared config access for the labelling tools."""

from __future__ import annotations

import os

import yaml

from surface_fractions.config import REPO_ROOT

DEFAULT_CONFIG_PATH = os.path.join(REPO_ROOT, "configs", "labelling.yaml")


class OpenNumberUnset(RuntimeError):
    """A LABELLING_GUIDE.md §9 open number is needed but has not been set."""


def load_config(path: str | None = None) -> dict:
    with open(path or DEFAULT_CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


def require_open(cfg: dict, key: str, sub: str | None = None):
    """Return an open number's value, or raise if it is still UNSET."""
    entry = cfg["open"][key]
    if entry.get("status") == "UNSET":
        raise OpenNumberUnset(
            f"LABELLING_GUIDE.md §9 open number {key!r} is UNSET. It must be "
            f"set (before labelling starts, never after results) in "
            f"configs/labelling.yaml.")
    if sub is not None:
        return entry[sub]
    return entry.get("value", entry)
