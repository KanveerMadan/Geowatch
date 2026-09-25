"""
Per-tile metadata record, versioned label store, sealed validation batches
(LABELLING_GUIDE.md §6, §8).

  - Every §8 field is mandatory; a record missing one is refused.
  - Labels are never overwritten: each save is a new version with its
    reason; old versions stay.
  - A dropped tile is never relabelled (§6).
  - Validation labels (Makoko, Kibera, Rocinha) live in a separate tree, in
    batch 1 or batch 2, and are read only through `unseal`, which requires
    a batch and a stated purpose and appends to an access log. They are
    never to be used to modify thresholds, architecture, preprocessing or
    labelling rules (§8, item 21 firewall).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timezone

from labelling.common import require_open


class RecordError(ValueError):
    pass


class SealedError(PermissionError):
    pass


def _has(v) -> bool:
    return v is not None and not (isinstance(v, str) and not v.strip())


@dataclass
class TileRecord:
    site: str
    tile_id: str
    imagery_source: str
    imagery_acquisition_date: str
    imagery_acquisition_time: str | None   # time of day: shadow geometry (§5);
                                           # None ONLY with measured sun geometry (v1.2)
    imagery_resolution_m: float
    imagery_licence: str
    s2_composite_window: dict          # {"start", "end"}
    date_gap_days: int
    change_test_result: str
    labeller: str
    labelling_date: str
    guide_version: str
    pct_unsure: float
    pct_shadow_full: float
    qc_status: str
    # v1.2 (§5/§8): stand-in where the publisher gives no acquisition time.
    sun_azimuth_deg: float | None = None
    sun_elevation_deg: float | None = None
    sun_geometry_method: str | None = None
    sun_geometry_n_buildings: int | None = None

    SUN_FIELDS = ("sun_azimuth_deg", "sun_elevation_deg", "sun_geometry_method",
                  "sun_geometry_n_buildings")

    def validate(self, cfg: dict) -> None:
        for f in fields(self):
            if f.name in self.SUN_FIELDS or f.name == "imagery_acquisition_time":
                continue
            v = getattr(self, f.name)
            if v is None or (isinstance(v, str) and not v.strip()):
                raise RecordError(f"{self.tile_id}: mandatory field {f.name!r} is empty (§8)")
        self._validate_time_or_sun(cfg)
        if set(self.s2_composite_window) != {"start", "end"}:
            raise RecordError(f"{self.tile_id}: s2_composite_window needs start and end")
        if self.guide_version != cfg["guide_version"]:
            raise RecordError(f"{self.tile_id}: guide version {self.guide_version} "
                              f"!= current {cfg['guide_version']} (§7: recheck)")

    def _validate_time_or_sun(self, cfg: dict) -> None:
        """§5/§8 v1.2: an acquisition time, OR sun azimuth + elevation measured
        from the shadows of >= min_buildings buildings with the method recorded."""
        sun = {k: getattr(self, k) for k in self.SUN_FIELDS}
        if _has(self.imagery_acquisition_time):
            return
        missing = [k for k, v in sun.items() if not _has(v)]
        if missing:
            raise RecordError(f"{self.tile_id}: no acquisition time, and the sun-geometry "
                              f"stand-in is incomplete: missing {missing} (§5/§8 v1.2)")
        n_min = cfg["sun_geometry"]["min_buildings"]
        if int(sun["sun_geometry_n_buildings"]) < n_min:
            raise RecordError(f"{self.tile_id}: sun geometry measured from "
                              f"{sun['sun_geometry_n_buildings']} building(s); needs >= {n_min}")
        if not 0 <= float(sun["sun_azimuth_deg"]) < 360:
            raise RecordError(f"{self.tile_id}: sun azimuth outside [0, 360)")
        if not 0 < float(sun["sun_elevation_deg"]) <= 90:
            raise RecordError(f"{self.tile_id}: sun elevation outside (0, 90]")


def time_gap_decision(site: str, gap_days: int, change_detected: bool | None, cfg: dict) -> str:
    """§6: beyond the site's max gap -> drop regardless; within it -> keep
    unless the change test detects change. Needs §9.1 and §9.2."""
    max_gap = require_open(cfg, "max_date_gap_days", "per_site")[site]
    if gap_days > max_gap:
        return "drop"
    require_open(cfg, "change_test")
    if change_detected is None:
        raise RecordError(f"{site}: within max gap; the change test must be run")
    return "drop" if change_detected else "keep"


def site_role(site: str, cfg: dict) -> str:
    for role in ("training", "validation"):
        if site in cfg["sites"][role]:
            return role
    raise RecordError(f"{site!r} is not in the item 21 site list")


class LabelStore:
    """On-disk store. Layout:
        <root>/training/<site>/<tile_id>/v<N>.json
        <root>/validation/<site>/batch_<B>/<tile_id>/v<N>.json
        <root>/dropped.jsonl, <root>/unseal_log.jsonl
    """

    def __init__(self, root: str, cfg: dict):
        self.root, self.cfg = root, cfg

    def _tile_dir(self, site, tile_id, batch=None):
        role = site_role(site, self.cfg)
        if role == "validation":
            if batch not in (1, 2):
                raise SealedError(f"{site} is a validation site: batch 1 or 2 required")
            return os.path.join(self.root, role, site, f"batch_{batch}", tile_id)
        if batch is not None:
            raise RecordError(f"{site} is a training site: no batch")
        return os.path.join(self.root, role, site, tile_id)

    def _log(self, name, entry):
        os.makedirs(self.root, exist_ok=True)
        with open(os.path.join(self.root, name), "a") as fh:
            fh.write(json.dumps(entry) + "\n")

    def dropped(self) -> set:
        p = os.path.join(self.root, "dropped.jsonl")
        if not os.path.exists(p):
            return set()
        with open(p) as fh:
            return {(e["site"], e["tile_id"]) for e in map(json.loads, fh)}

    def drop(self, site, tile_id, reason):
        self._log("dropped.jsonl", {"site": site, "tile_id": tile_id, "reason": reason,
                                    "at": datetime.now(timezone.utc).isoformat()})

    def save(self, record: TileRecord, features: list, reason: str, batch=None) -> str:
        """Save a new version. Never overwrites; reason mandatory after v1."""
        record.validate(self.cfg)
        if (record.site, record.tile_id) in self.dropped():
            raise RecordError(f"{record.tile_id} was dropped; dropped tiles are never "
                              f"relabelled (§6)")
        d = self._tile_dir(record.site, record.tile_id, batch)
        os.makedirs(d, exist_ok=True)
        n = 1 + max([int(f[1:-5]) for f in os.listdir(d) if f.startswith("v")] or [0])
        if n > 1 and not reason.strip():
            raise RecordError("a correction needs its reason recorded (§8)")
        path = os.path.join(d, f"v{n}.json")
        with open(path, "x") as fh:          # "x": refuse to overwrite, ever
            json.dump({"version": n, "reason": reason, "record": asdict(record),
                       "features": features,
                       "saved_at": datetime.now(timezone.utc).isoformat()}, fh)
        return path

    def load_training(self, site, tile_id, version=None) -> dict:
        if site_role(site, self.cfg) != "training":
            raise SealedError(f"{site} is a validation site; use unseal()")
        return self._load(self._tile_dir(site, tile_id), version)

    def unseal(self, site, tile_id, batch: int, purpose: str, version=None) -> dict:
        if site_role(site, self.cfg) != "validation":
            raise RecordError(f"{site} is not a validation site")
        if not purpose.strip():
            raise SealedError("unsealing validation labels requires a stated purpose")
        self._log("unseal_log.jsonl", {"site": site, "tile_id": tile_id, "batch": batch,
                                       "purpose": purpose,
                                       "at": datetime.now(timezone.utc).isoformat()})
        return self._load(self._tile_dir(site, tile_id, batch), version)

    @staticmethod
    def _load(d, version):
        vs = sorted(int(f[1:-5]) for f in os.listdir(d) if f.startswith("v"))
        with open(os.path.join(d, f"v{version or vs[-1]}.json")) as fh:
            return json.load(fh)


def relabel_gap_ok(first: TileRecord, second: TileRecord, cfg: dict) -> bool:
    """§7: the same labeller must wait at least a week before a blind re-label."""
    if first.labeller != second.labeller:
        return True
    gap = (date.fromisoformat(second.labelling_date)
           - date.fromisoformat(first.labelling_date)).days
    return gap >= cfg["qc"]["same_labeller_min_gap_days"]
