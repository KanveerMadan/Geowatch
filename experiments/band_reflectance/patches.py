"""
Production patch construction, ported from the training notebook.

Recovered from `notebooks/archive/geowatch_segformer_finetune_UPDATED.ipynb` at
commit ecfe370 (the notebook ingestion/resnet_model.py cites for the
architecture). NOTE: the cell numbers in that copy differ from those quoted in
the brief -- the three builders are in cell 10, assembly in cell 12, class
weights in cell 16. Three sources, not five: `sam`, `osm`, `sliding_window`.

WHY THIS EXISTS. The earlier probe built patches by sliding a window over the
raster and pairing it with a sparse multi-class label canvas (~45% labelled,
several classes per patch, native resolution). Production does something
structurally different, and that difference is why the probe's Arm A could not
train:

  * SAM patches crop each annotated segment's BBOX and RESIZE it to 64x64, then
    fill the entire mask with that segment's single label. 100% labelled, ONE
    class per patch, scale normalised away by the resize.
  * OSM patches rasterise major-road centrelines and label ONLY pixels within
    2 px of the line; everything else is IGNORE. Sparse and single-class.
  * Sliding-window patches take a 64x64 crop and fill the whole mask with the
    label of the first annotated centroid inside it.

So every production patch is effectively single-class. The probe was asking the
model to solve dense multi-class segmentation from sparse supervision, which is
a harder problem than the one the 0.313 baseline was measured on.

Faithful to the original: PATCH_SIZE 64, road_buffer_px 2, PAVED_TYPES major
roads only, per-city stride max(20, aoi_km2*2), PAVED_ROAD_CAP_PER_CITY 180,
sliding stride 32, random.seed(42)/np.random.seed(42), and a final shuffle.

Paths are the local equivalents of the notebook's /content/data/{city}/:
  tile_0_0.png -> data/pipeline_runs/<run>/tiles/tile_0_0.png
  roads.geojson -> data/pipeline_runs/<run>/osm/roads.geojson
  result.json   -> data/pipeline_runs/<run>/result.json
"""
from __future__ import annotations

import glob
import json
import os
import random
from collections import Counter

import numpy as np
from PIL import Image

CATEGORIES = ["dense_informal_roofing", "sparse_informal_roofing", "paved_road",
              "standing_water", "vegetation_clearing", "active_construction",
              "dense_vegetation"]
CAT2IDX = {c: i for i, c in enumerate(CATEGORIES)}
NUM_CLASSES = len(CATEGORIES)
IGNORE_INDEX = 255
PATCH_SIZE = 64

PAVED_TYPES = {"primary", "secondary", "tertiary", "trunk", "motorway",
               "primary_link", "secondary_link", "tertiary_link"}
PAVED_ROAD_CAP_PER_CITY = 180


def run_dir(city: str) -> str | None:
    cands = [d for d in sorted(glob.glob(f"data/pipeline_runs/{city}_*"))
             if os.path.exists(os.path.join(d, "tiles", "tile_0_0.png"))
             and os.path.exists(os.path.join(d, "annotations.json"))]
    return cands[-1] if cands else None


def city_bbox(city: str):
    rd = run_dir(city)
    p = os.path.join(rd, "result.json")
    if not os.path.exists(p):
        return None
    aoi = json.load(open(p))["aoi"]
    return [aoi["west"], aoi["south"], aoi["east"], aoi["north"]]


def _annotations(rd):
    d = json.load(open(os.path.join(rd, "annotations.json")))
    return d if isinstance(d, list) else d.get("annotations", [])


def build_sam_patches(city, patch_size=PATCH_SIZE, verbose=True):
    """Source 1: segment bbox crops, resized, mask filled with the single label."""
    rd = run_dir(city)
    if rd is None:
        return []
    tile = Image.open(os.path.join(rd, "tiles", "tile_0_0.png")).convert("RGB")
    tw, th = tile.size
    out, skipped, unknown, excluded = [], 0, 0, 0
    for ann in _annotations(rd):
        if ann.get("skipped") or ann.get("human_label") is None:
            skipped += 1
            continue
        if ann["human_label"] == "unknown":
            unknown += 1
            continue
        if ann["human_label"] not in CAT2IDX:
            excluded += 1
            continue
        x, y, w, h = ann["bbox"]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(tw, x + w), min(th, y + h)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = tile.crop((x1, y1, x2, y2)).resize((patch_size, patch_size), Image.BILINEAR)
        idx = CAT2IDX[ann["human_label"]]
        out.append({"image": np.array(crop, dtype=np.uint8),
                    "mask": np.full((patch_size, patch_size), idx, dtype=np.uint8),
                    "city": city, "source": "sam", "label": ann["human_label"],
                    "bbox": [x1, y1, x2, y2]})
    if verbose:
        print(f"  [{city}] SAM patches: {len(out)} usable | {skipped} skipped | "
              f"{unknown} unknown excluded | {excluded} OSM-only-category excluded")
    return out


def build_osm_patches(city, patch_size=PATCH_SIZE, road_buffer_px=2, verbose=True):
    """Source 2: major-road centrelines, thin-line masks, everything else IGNORE."""
    import geopandas as gpd
    from shapely.geometry import LineString, MultiLineString

    rd = run_dir(city)
    if rd is None:
        return []
    roads_path = os.path.join(rd, "osm", "roads.geojson")
    bbox = city_bbox(city)
    if not os.path.exists(roads_path) or bbox is None:
        if verbose:
            print(f"  [{city}] roads.geojson not found")
        return []

    tile = Image.open(os.path.join(rd, "tiles", "tile_0_0.png")).convert("RGB")
    tw, th = tile.size
    tile_arr = np.array(tile, dtype=np.uint8)
    west, south, east, north = bbox
    lon_per_px, lat_per_px = (east - west) / tw, (north - south) / th
    aoi_km2 = (east - west) * 111 * (north - south) * 111
    stride = max(20, int(aoi_km2 * 2))
    if verbose:
        print(f"  [{city}] AOI ~{aoi_km2:.1f} km^2 -> road_stride={stride}")
    half = patch_size // 2

    gdf = gpd.read_file(roads_path)
    hw = "highway" if "highway" in gdf.columns else None
    if hw is None:
        if verbose:
            print(f"  [{city}] roads.geojson has no highway column -- {list(gdf.columns)}")
        return []
    paved = gdf[gdf[hw].isin(PAVED_TYPES)]
    if paved.empty:
        if verbose:
            print(f"  [{city}] no major-road types present")
        return []

    centres, all_px = [], []
    for _, row in paved.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        lines = list(geom.geoms) if isinstance(geom, MultiLineString) else \
            ([geom] if isinstance(geom, LineString) else [])
        for line in lines:
            try:
                coords = list(line.coords)
            except Exception:
                continue
            for i in range(len(coords) - 1):
                x0 = (coords[i][0] - west) / lon_per_px
                y0 = (north - coords[i][1]) / lat_per_px
                x1 = (coords[i + 1][0] - west) / lon_per_px
                y1 = (north - coords[i + 1][1]) / lat_per_px
                n = max(int(np.hypot(x1 - x0, y1 - y0)) * 2, 2)
                for x, y in zip(np.linspace(x0, x1, n), np.linspace(y0, y1, n)):
                    xi, yi = int(round(x)), int(round(y))
                    all_px.append((xi, yi))
                    if half <= xi < tw - half and half <= yi < th - half:
                        centres.append((xi, yi))
    if not centres:
        return []

    road_set = set(all_px)
    idx = CAT2IDX["paved_road"]
    out = []
    for cx, cy in centres[::stride]:
        crop = tile_arr[cy - half:cy + half, cx - half:cx + half]
        if crop.shape[:2] != (patch_size, patch_size):
            continue
        mask = np.full((patch_size, patch_size), IGNORE_INDEX, dtype=np.uint8)
        for rx, ry in road_set:
            if (cx - half - road_buffer_px) <= rx <= (cx + half + road_buffer_px) and \
               (cy - half - road_buffer_px) <= ry <= (cy + half + road_buffer_px):
                lx, ly = rx - (cx - half), ry - (cy - half)
                x_lo, x_hi = max(0, lx - road_buffer_px), min(patch_size, lx + road_buffer_px + 1)
                y_lo, y_hi = max(0, ly - road_buffer_px), min(patch_size, ly + road_buffer_px + 1)
                if x_hi > x_lo and y_hi > y_lo:
                    mask[y_lo:y_hi, x_lo:x_hi] = idx
        if not (mask == idx).any():
            continue
        out.append({"image": crop, "mask": mask, "city": city,
                    "source": "osm", "label": "paved_road",
                    "centre": [cx, cy]})
    if len(out) > PAVED_ROAD_CAP_PER_CITY:
        out = random.sample(out, PAVED_ROAD_CAP_PER_CITY)
    if verbose:
        print(f"  [{city}] OSM paved road patches: {len(out)} "
              f"(thin-line masks, buffer={road_buffer_px}px, capped at {PAVED_ROAD_CAP_PER_CITY})")
    return out


def build_sliding_window_patches(city, patch_size=PATCH_SIZE, stride=32, verbose=True):
    """Source 3: 64x64 crops labelled by the first annotated centroid inside."""
    rd = run_dir(city)
    if rd is None:
        return []
    tile = Image.open(os.path.join(rd, "tiles", "tile_0_0.png")).convert("RGB")
    tw, th = tile.size
    tile_arr = np.array(tile, dtype=np.uint8)
    cents = []
    for ann in _annotations(rd):
        if ann.get("skipped") or ann.get("human_label") is None:
            continue
        if ann["human_label"] == "unknown" or ann["human_label"] not in CAT2IDX:
            continue
        x, y, w, h = ann["bbox"]
        cents.append((x + w / 2, y + h / 2, CAT2IDX[ann["human_label"]], ann["human_label"]))

    out = []
    for ys in range(0, th - patch_size, stride):
        for xs in range(0, tw - patch_size, stride):
            matching = [(i, n) for cx, cy, i, n in cents
                        if xs <= cx < xs + patch_size and ys <= cy < ys + patch_size]
            if not matching:
                continue
            idx, name = matching[0]
            out.append({"image": tile_arr[ys:ys + patch_size, xs:xs + patch_size],
                        "mask": np.full((patch_size, patch_size), idx, dtype=np.uint8),
                        "city": city, "source": "sliding_window", "label": name,
                        "origin": [xs, ys]})
    if verbose:
        print(f"  [{city}] Sliding window patches: {len(out)}")
    return out


def build_all(cities, seed=42, verbose=True):
    """Cell 12's assembly: three sources per city, then shuffle. No oversampling."""
    random.seed(seed)
    np.random.seed(seed)
    out = []
    for city in cities:
        if verbose:
            print(f"\n--- {city.upper()} ---")
        out += build_sam_patches(city, verbose=verbose)
        out += build_osm_patches(city, verbose=verbose)
        out += build_sliding_window_patches(city, verbose=verbose)
    random.shuffle(out)
    return out


def class_weights_from_patches(patches):
    """
    Cell 16's formula, computed from the BUILT dataset.

    The notebook is emphatic that computing weights from annotation counts
    instead caused a real bug -- paved_road was both 77% of the data and given
    the highest loss weight, collapsing the model onto it. Matching the
    checkpoint's stored weights is therefore a strong signal the patch rebuild
    is correct.
    """
    counts = Counter(p["label"] for p in patches)
    c = np.maximum(np.array([counts.get(k, 1) for k in CATEGORIES], dtype=np.float32), 1)
    w = 1.0 / c
    return w / w.sum() * NUM_CLASSES, c
