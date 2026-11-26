"""Dated, locally licensed survey footprints with an explicit observation boundary at BOTH dates.

Each GeoJSON FeatureCollection contains features with properties.role = coverage or surface.
Coverage is the independently surveyed area; gaps in a footprint file cannot establish absence.
The optional manifest is a JSON list of {name,source,license,before:{date,file},after:{date,file}}.
EPSG:4326 coordinates. Each pair measures one named physical surface in its recorded time interval.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union


def _polygon(geometry):
    geom = shape(geometry)
    if geom.geom_type not in ("Polygon", "MultiPolygon") or not geom.is_valid or geom.is_empty:
        raise ValueError("survey coverage and surfaces require valid nonempty polygons")
    return geom


def _epoch(root, spec):
    interval = spec.get("interval")
    if interval is None:
        interval = [spec["date"], spec["date"]]
    if len(interval) != 2:
        raise ValueError("survey epoch interval needs a first and last acquisition date")
    first, last = [date.fromisoformat(d).isoformat() for d in interval]
    if first > last:
        raise ValueError("survey epoch interval is reversed")
    raw = (root / spec["file"]).read_bytes()
    fc = json.loads(raw)
    if fc.get("type") != "FeatureCollection":
        raise ValueError("survey epoch must be a GeoJSON FeatureCollection")
    areas = {"coverage": [], "surface": []}
    for feature in fc["features"]:
        role = feature["properties"]["role"]
        if role not in areas:
            raise ValueError("unknown survey feature role")
        areas[role].append(_polygon(feature["geometry"]))
    if not areas["coverage"]:
        raise ValueError("survey epoch needs a mapped coverage boundary")
    return ((first, last), unary_union(areas["coverage"]), unary_union(areas["surface"]),
            hashlib.sha256(raw).hexdigest())


class SurveyPairs:
    def __init__(self, path):
        self.pairs = []
        self.provenance = []
        self._projected = {}
        path = Path(path)
        for row in json.loads(path.read_text()):
            info = {k: row[k] for k in ("name", "source", "license")}
            if row.get("url"):
                info["url"] = row["url"]
            if not all(isinstance(v, str) and v.strip() for v in info.values()):
                raise ValueError("survey pairs need a surface name, source and license")
            if any(p["name"] == info["name"] for p in self.provenance):
                raise ValueError("use a unique name for each survey pair")
            a, b = (_epoch(path.parent, row[k]) for k in ("before", "after"))
            if a[0][1] >= b[0][0]:
                raise ValueError("survey dates are out of order")
            self.provenance.append({**info, "before_interval": a[0], "after_interval": b[0],
                                    "hashes": [a[3], b[3]]})
            joint = a[1].intersection(b[1])
            first, last = a[2].intersection(joint), b[2].intersection(joint)
            self.pairs.append((a[0], b[0], info["name"], joint, last.difference(first), first.difference(last)))

    def projected_pairs(self, geometry, crs, start, end):
        key = str(crs)
        if key not in self._projected:
            self._projected[key] = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform, {}
        project, projected = self._projected[key]
        cell_ll = shape(geometry)
        for a, b, name, joint_ll, gain_ll, loss_ll in self.pairs:
            # Exact survey-to-survey change; it cannot date the transition more tightly.
            if a[0] < start or b[1] >= end or not cell_ll.intersects(joint_ll):
                continue
            if name not in projected:
                projected[name] = tuple(transform(project, g) for g in (joint_ll, gain_ll, loss_ll))
            yield a, b, name, projected[name]

    def measure(self, geometry, crs, start, end):
        out = {}
        cell = None
        for a, b, name, geoms in self.projected_pairs(geometry, crs, start, end):
            if cell is None:
                project, _ = self._projected[str(crs)]
                cell = transform(project, shape(geometry))
            measured = measure_geometry(cell, geoms)
            if measured:
                out[name] = {**measured, "before_interval": a, "after_interval": b}
        return out


def measure_geometry(zone, geoms):
    joint, gain, loss = geoms
    area = zone.intersection(joint).area
    if area <= 0:
        return None
    plus, minus = zone.intersection(gain).area, zone.intersection(loss).area
    return {"gain_m2": plus, "loss_m2": minus, "net_m2": plus - minus, "joint_area_m2": area,
            "uncertainty_status": "delineation_and_registration_error_unmeasured"}


def configured_surveys():
    path = os.environ.get("GEOWATCH_CHANGE_SURVEYS")
    return SurveyPairs(path) if path else None
