"""
Held-out firewall (build item 27).

A subset of the labels never touches training: it exists solely to validate.
This is the only independent signal the project has, so it is enforced here,
in code, not by convention.

THE SPLIT. `configs/heldout_split.json` lists the held-out records by path and
ID pattern, held out by validation site: the hand-traced fraction tiles of
Makoko, Kibera and Rocinha (sealed batches 1 and 2), and anything naming their
host cities (the item 21 firewall is city-level). The validation set is drawn
from the full raster, never from annotated segments -- see the split's notes.
Its SHA256 is recorded in ARTIFACT_HASHES.txt, and `load_split` refuses a file
whose hash does not match, so the split cannot be edited quietly.

THE GUARD. Training takes hand tiles in through `training_tiles`, which checks
the whole set before anything is read; one held-out tile refuses all of it.
Any other training read calls `assert_trainable` (one record) or
`assert_training_set` (many) before it opens anything. A held-out record
raises HeldOutError. There is no override: validation reads do not go through
the training path.

A record is a path (str or PathLike) or a mapping with any of the keys
`path`, `site`, `city`, `tile_id`.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from fnmatch import fnmatchcase
from pathlib import Path, PurePath

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLIT_PATH = REPO_ROOT / "configs" / "heldout_split.json"
HASHES_PATH = REPO_ROOT / "ARTIFACT_HASHES.txt"
SPLIT_NAME = "configs/heldout_split.json"     # its key in ARTIFACT_HASHES.txt


class HeldOutError(PermissionError):
    """A training read reached a held-out record."""


class SplitHashError(RuntimeError):
    """The split file does not match the hash recorded for it."""


def recorded_hash(name: str = SPLIT_NAME, hashes_path: str | os.PathLike = HASHES_PATH) -> str:
    """The SHA256 recorded for `name`. Entries are `<sha>  <path>`; the
    existing ones write `data//...`, so slashes are collapsed before comparing."""
    for line in Path(hashes_path).read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and os.path.normpath(parts[1]) == os.path.normpath(name):
            return parts[0]
    raise SplitHashError(f"{name} has no entry in {hashes_path}")


def load_split(path: str | os.PathLike = SPLIT_PATH,
               hashes_path: str | os.PathLike = HASHES_PATH) -> dict:
    """The split, after checking its bytes against the recorded hash."""
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    expected = recorded_hash(SPLIT_NAME, hashes_path)
    if actual != expected:
        raise SplitHashError(f"{path}: sha256 {actual} != {expected} recorded in "
                             f"{hashes_path}. The held-out split is fixed; a change is "
                             f"a decision, recorded with its new hash.")
    return json.loads(raw)


def _parts(p) -> list:
    return [c.lower() for c in PurePath(os.fspath(p)).as_posix().split("/") if c not in ("", ".")]


def _path_match(parts: list, pattern: str) -> bool:
    """True if a contiguous run of path components matches `pattern`
    component by component (`*` never crosses a `/`)."""
    pat = pattern.lower().split("/")
    k = len(pat)
    return any(all(fnmatchcase(c, q) for c, q in zip(parts[i:i + k], pat))
               for i in range(len(parts) - k + 1))


def held_out_reason(record, split: dict | None = None) -> str | None:
    """Why `record` is held out, or None if it may be trained on."""
    split = split if split is not None else load_split()
    fields = dict(record) if isinstance(record, Mapping) else {"path": record}
    sites = {s.lower() for s in split["sites"]}
    cities = {v["city"].lower() for v in split["sites"].values()}
    id_patterns = [q.lower() for q in split["tile_id_patterns"]]

    if fields.get("site") is not None and str(fields["site"]).lower() in sites:
        return f"site {fields['site']!r} is a validation site"
    if fields.get("city") is not None and str(fields["city"]).lower() in cities:
        return f"city {fields['city']!r} contains a validation site"
    if fields.get("tile_id") is not None:
        tid = str(fields["tile_id"]).lower()
        for q in id_patterns:
            if fnmatchcase(tid, q):
                return f"tile_id {fields['tile_id']!r} matches held-out pattern {q!r}"
    if fields.get("path") is not None:
        parts = _parts(fields["path"])
        for q in split["path_patterns"]:
            if _path_match(parts, q):
                return f"path {os.fspath(fields['path'])!r} matches held-out pattern {q!r}"
        for c in parts:
            for q in id_patterns:
                if fnmatchcase(c, q):
                    return f"path {os.fspath(fields['path'])!r} holds tile ID {c!r} ({q!r})"
    return None


def assert_trainable(record, split: dict | None = None) -> None:
    """Raise HeldOutError if `record` is held out."""
    reason = held_out_reason(record, split)
    if reason is not None:
        raise HeldOutError(f"held-out record refused by the training path: {reason} "
                           f"(item 27, {SPLIT_NAME})")


def assert_training_set(records, split: dict | None = None) -> None:
    """Raise HeldOutError if ANY record in `records` is held out."""
    split = split if split is not None else load_split()
    for r in records:
        assert_trainable(r, split)


def training_tiles(tile_dirs, split: dict | None = None) -> list:
    """The training path's way in for hand-traced fraction tiles.

    tile_dirs: tile directories in the Stage 1 layout, <...>/<site>/<tile_id>/
    -> [{"site", "tile_id", "path", "labels"}], `labels` the tile's labels.gpkg.
    Nothing is opened here; the caller reads `labels`."""
    split = split if split is not None else load_split()
    records = [{"site": Path(d).parent.name, "tile_id": Path(d).name, "path": Path(d)}
               for d in tile_dirs]
    assert_training_set(records, split)      # the whole set, before any file is touched
    for r in records:
        r["labels"] = r["path"] / "labels.gpkg"
        if not r["labels"].is_file():
            raise FileNotFoundError(f"{r['labels']}: a training tile needs its labels")
    return records
