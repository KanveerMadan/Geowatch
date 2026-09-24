"""
Production patch construction, ported from the notebook that actually trained
the deployed checkpoint.

Source: `notebooks/archive/geowatch_water_loco_with_diagnostics (2).ipynb` at
commit ecfe370, identified by `archive/AUDIT_FINDINGS.md:689` as the notebook
that produced `models/production/geowatch_production_model.pth`. Cell layout in
that copy: builders cell 11, assembly cell 13, class weights cell 18, production
training cell 39. 48 cells total.

This supersedes `patches.py`, which ported the THREE-builder
`geowatch_segformer_finetune_UPDATED.ipynb` -- the architecture source, not the
training source (C42). Five sources here, not three:

    build_sam_patches                    annotated segments, real mask_rle
    build_osm_patches                    major-road centrelines, thin-line masks
    build_osm_generated_patches          ALL road types, real buffered geometry
    build_osm_generated_water_patches    OSM water geometry -> standing_water
    build_sliding_window_patches         dominant-label windows off a label canvas

THE CAP IS THE DIFFERENCE THAT MATTERED. `patches.py` over-generated
`paved_road` by 2.75x, and the suspicion on record was `sample_stride =
max(20, aoi_km2 * 2)` interacting with tile size. That was wrong. The stride
expression is byte-identical between the two notebooks. What differs is one
constant:

    _UPDATED.ipynb                  PAVED_ROAD_CAP_PER_CITY = 180
    water_loco_with_diagnostics     PAVED_ROAD_CAP_PER_CITY = 25

11 cities x 180 = 1980 versus 11 x 25 = 275. The earlier rebuild measured 1563
OSM road patches; this one cannot exceed 275 from that source. Tile size never
entered into it.

Two further caps exist only in this notebook: `build_sliding_window_patches`
gains `min_labeled_pct=5.0` (>=204 of 4096 px, not the probe's >=32) and
`max_per_class_per_city=30`, and both OSM-generated builders cap at 25/city
with greedy farthest-point spatial spreading.

Faithful to the original: PATCH_SIZE 64, road_buffer_px 2, sliding stride 32,
`random.seed(42)` / `np.random.seed(42)` once at module import, builders called
per city in the order sam -> osm -> osm_generated -> osm_generated_water ->
sliding_window, cities in LOCO_CLEAN_CITIES order, and a final
`random.shuffle`. That ordering is load-bearing: `random.sample` and
`random.shuffle` draw from the global RNG, so a different call order gives a
different patch set from the same inputs.

Paths are the local equivalents of the notebook's `/content/data/{city}/`:
    tile_0_0.png                            -> <run>/tiles/tile_0_0.png
    annotations.json, result.json           -> <run>/
    roads.geojson                           -> <run>/osm/roads.geojson
    osm_generated_annotations.json          -> <run>/
    osm_generated_annotations_water.json    -> <run>/

Run ids are pinned from the notebook's own CITY_MAP (cell 4) rather than
globbed, so this reads the same runs the checkpoint was trained on.
"""
from __future__ import annotations

import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

# --- cell 9: category definitions -------------------------------------------

CATEGORIES = [
    "dense_informal_roofing",   # 0
    "sparse_informal_roofing",  # 1
    "paved_road",               # 2
    "standing_water",           # 3
    "vegetation_clearing",      # 4
    "active_construction",      # 5
    "dense_vegetation",         # 6
]
CAT2IDX = {c: i for i, c in enumerate(CATEGORIES)}
NUM_CLASSES = len(CATEGORIES)
IGNORE_INDEX = 255
PATCH_SIZE = 64

# --- cell 4: CITY_MAP, pinned ------------------------------------------------

CITY_MAP = {
    "dharavi":   "dharavi_20260702_163012",
    "nairobi":   "nairobi_20260702_164731",
    "jakarta":   "jakarta_20260702_163609",
    "hcmc":      "hcmc_20260702_163714",
    "kigali":    "kigali_20260702_163814",
    "accra":     "accra_20260702_163854",
    "dhaka":     "dhaka_20260702_163939",
    "lagos":     "lagos_20260702_165430",
    "capetown":  "capetown_20260702_164022",
    "guatemala": "guatemala_20260702_164206",
    "nusantara": "nusantara_20260702_165811",
}

# --- cell 7: LOCO city order. The assembly loop iterates THIS, not CITY_MAP. --

LOCO_CLEAN_CITIES = [
    "dharavi", "accra", "nairobi", "jakarta", "hcmc", "kigali",
    "dhaka", "lagos", "capetown", "guatemala", "nusantara",
]

PAVED_TYPES = {"primary", "secondary", "tertiary", "trunk", "motorway",
               "primary_link", "secondary_link", "tertiary_link"}

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = REPO_ROOT / "data" / "pipeline_runs"

random.seed(42)
np.random.seed(42)


def reseed() -> None:
    """Restore the notebook's cell-11 seed state before a rebuild."""
    random.seed(42)
    np.random.seed(42)


def _run_dir(city: str) -> Path:
    return RUNS_ROOT / CITY_MAP[city]


def _city_file(city: str, name: str) -> Path:
    """Resolve one of the notebook's /content/data/{city}/<name> paths."""
    run = _run_dir(city)
    if name == "tile_0_0.png":
        for sub in ("tile_0_0.png", "tiles/tile_0_0.png"):   # cell 4 TILE_SUBPATHS
            if (run / sub).is_file():
                return run / sub
        return run / "tiles" / "tile_0_0.png"
    if name in ("roads.geojson", "waterways.geojson"):
        return run / "osm" / name
    return run / name


def city_bboxes() -> dict:
    """Cell 7: bboxes come from result.json, never hardcoded."""
    out = {}
    for city in LOCO_CLEAN_CITIES:
        rp = _city_file(city, "result.json")
        if rp.is_file():
            aoi = json.loads(rp.read_text())["aoi"]
            out[city] = [aoi["west"], aoi["south"], aoi["east"], aoi["north"]]
    return out


CITY_BBOXES = city_bboxes()


def decode_mask_rle(rle: dict) -> np.ndarray:
    """Matches ingestion/segmentation.py's encoder -- keep in sync."""
    h, w = rle["size"]
    counts = rle["counts"]
    flat = np.zeros(h * w, dtype=bool)
    idx = 0
    val = False
    for c in counts:
        if val:
            flat[idx:idx + c] = True
        idx += c
        val = not val
    return flat.reshape(w, h).T


# --- source 1: SAM patches ---------------------------------------------------

def build_sam_patches(city: str, patch_size: int = 64, verbose: bool = True) -> list:
    """Annotated segments, bbox-cropped and resized, real mask_rle painted."""
    ann_path = _city_file(city, "annotations.json")
    tile_path = _city_file(city, "tile_0_0.png")

    if not ann_path.exists() or not tile_path.exists():
        if verbose:
            print(f"  [{city}] missing annotations.json or tile, skipping.")
        return []

    ann_data = json.loads(ann_path.read_text())
    tile_img = Image.open(tile_path).convert("RGB")
    tile_w, tile_h = tile_img.size

    patches_out = []
    skipped, unknown, excluded, no_mask = 0, 0, 0, 0

    for ann in ann_data["annotations"]:
        if ann.get("skipped", False) or ann.get("human_label") is None:
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
        x2, y2 = min(tile_w, x + w), min(tile_h, y + h)
        if x2 <= x1 or y2 <= y1:
            continue

        crop = tile_img.crop((x1, y1, x2, y2)).resize((patch_size, patch_size), Image.BILINEAR)
        crop_arr = np.array(crop, dtype=np.uint8)
        label_idx = CAT2IDX[ann["human_label"]]

        mask_rle = ann.get("mask_rle")
        if mask_rle is not None:
            full_mask = decode_mask_rle(mask_rle)
            local_mask = full_mask[y1:y2, x1:x2]
            local_mask_img = Image.fromarray(local_mask.astype(np.uint8) * 255)
            local_mask_resized = local_mask_img.resize((patch_size, patch_size), Image.NEAREST)
            local_mask_arr = np.array(local_mask_resized) > 127

            label_mask = np.full((patch_size, patch_size), IGNORE_INDEX, dtype=np.uint8)
            label_mask[local_mask_arr] = label_idx
        else:
            no_mask += 1
            label_mask = np.full((patch_size, patch_size), label_idx, dtype=np.uint8)

        patches_out.append({
            "image": crop_arr, "mask": label_mask, "city": city,
            "source": "sam", "label": ann["human_label"],
            "geom": {"kind": "resize", "box": (int(x1), int(y1), int(x2), int(y2))},
        })

    if verbose:
        print(f"  [{city}] SAM patches: {len(patches_out)} usable | {skipped} skipped | "
              f"{unknown} unknown excluded | {excluded} OSM-only-category excluded | "
              f"{no_mask} used bbox fallback (no mask_rle)")
    return patches_out


# --- source 2: OSM major-road centrelines ------------------------------------

PAVED_ROAD_CAP_PER_CITY = 25    # 180 in _UPDATED.ipynb -- this is the difference


def build_osm_patches(city: str, patch_size: int = 64, road_buffer_px: int = 2,
                      verbose: bool = True) -> list:
    """Major roads only, thin-line masks, everything else IGNORE."""
    tile_path = _city_file(city, "tile_0_0.png")
    roads_path = _city_file(city, "roads.geojson")

    if not tile_path.exists():
        return []
    if city not in CITY_BBOXES:
        if verbose:
            print(f"  [{city}] no result.json bbox -- OSM patches skipped")
        return []

    import geopandas as gpd
    from shapely.geometry import LineString, MultiLineString

    tile_img = Image.open(tile_path).convert("RGB")
    tile_w, tile_h = tile_img.size
    tile_arr = np.array(tile_img, dtype=np.uint8)

    west, south, east, north = CITY_BBOXES[city]
    lon_per_px = (east - west) / tile_w
    lat_per_px = (north - south) / tile_h

    aoi_km2 = (east - west) * 111 * (north - south) * 111
    sample_stride = max(20, int(aoi_km2 * 2))
    if verbose:
        print(f"  [{city}] AOI ~{aoi_km2:.1f} km^2 -> road_stride={sample_stride}")

    def lon_to_px(lon):
        return (lon - west) / lon_per_px

    def lat_to_py(lat):
        return (north - lat) / lat_per_px

    patches_out = []
    half = patch_size // 2

    def rasterize_lines(gdf, label_idx, label_name, stride):
        road_pixels = []
        all_road_pixels_global = []
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            if isinstance(geom, MultiLineString):
                line_list = list(geom.geoms)
            elif isinstance(geom, LineString):
                line_list = [geom]
            else:
                continue

            for line in line_list:
                try:
                    coords = list(line.coords)
                except Exception:
                    continue
                for i in range(len(coords) - 1):
                    x0 = lon_to_px(coords[i][0])
                    y0 = lat_to_py(coords[i][1])
                    x1 = lon_to_px(coords[i + 1][0])
                    y1 = lat_to_py(coords[i + 1][1])
                    n = max(int(np.hypot(x1 - x0, y1 - y0)) * 2, 2)
                    xs = np.linspace(x0, x1, n)
                    ys = np.linspace(y0, y1, n)
                    for x, y in zip(xs, ys):
                        xi, yi = int(round(x)), int(round(y))
                        all_road_pixels_global.append((xi, yi))
                        if half <= xi < tile_w - half and half <= yi < tile_h - half:
                            road_pixels.append((xi, yi))

        if not road_pixels:
            return []

        road_pixel_set = set(all_road_pixels_global)
        # Same membership test as the notebook's per-patch scan over
        # road_pixel_set, evaluated with numpy. Every painted block writes the
        # same label_idx, so paint order cannot change the result.
        if road_pixel_set:
            rp = np.fromiter((v for p in road_pixel_set for v in p), dtype=np.int64,
                             count=2 * len(road_pixel_set)).reshape(-1, 2)
        else:
            rp = np.empty((0, 2), dtype=np.int64)

        sampled = road_pixels[::stride]
        result = []
        for cx, cy in sampled:
            crop_arr = tile_arr[cy - half:cy + half, cx - half:cx + half]
            if crop_arr.shape[:2] != (patch_size, patch_size):
                continue

            label_mask = np.full((patch_size, patch_size), IGNORE_INDEX, dtype=np.uint8)
            sel = ((rp[:, 0] >= cx - half - road_buffer_px) &
                   (rp[:, 0] <= cx + half + road_buffer_px) &
                   (rp[:, 1] >= cy - half - road_buffer_px) &
                   (rp[:, 1] <= cy + half + road_buffer_px))
            for rx, ry in rp[sel]:
                local_x = rx - (cx - half)
                local_y = ry - (cy - half)
                x_lo = max(0, local_x - road_buffer_px)
                x_hi = min(patch_size, local_x + road_buffer_px + 1)
                y_lo = max(0, local_y - road_buffer_px)
                y_hi = min(patch_size, local_y + road_buffer_px + 1)
                if x_hi > x_lo and y_hi > y_lo:
                    label_mask[y_lo:y_hi, x_lo:x_hi] = label_idx

            if not (label_mask == label_idx).any():
                continue

            result.append({
                "image": crop_arr, "mask": label_mask, "city": city,
                "source": "osm", "label": label_name,
                "geom": {"kind": "window", "xy": (int(cx - half), int(cy - half))},
            })
        return result

    if roads_path.exists():
        try:
            roads_gdf = gpd.read_file(roads_path)
            hw_col = "highway" if "highway" in roads_gdf.columns else None
            if hw_col:
                paved = roads_gdf[roads_gdf[hw_col].isin(PAVED_TYPES)]
                if not paved.empty:
                    p = rasterize_lines(paved, CAT2IDX["paved_road"], "paved_road", sample_stride)
                    if len(p) > PAVED_ROAD_CAP_PER_CITY:
                        p = random.sample(p, PAVED_ROAD_CAP_PER_CITY)
                    patches_out.extend(p)
                    if verbose:
                        print(f"  [{city}] OSM paved road patches: {len(p)} "
                              f"(thin-line masks, buffer={road_buffer_px}px, "
                              f"capped at {PAVED_ROAD_CAP_PER_CITY})")
            elif verbose:
                print(f"  [{city}] roads.geojson has no highway column")
        except Exception as e:
            print(f"  [{city}] roads.geojson error: {e}")
    elif verbose:
        print(f"  [{city}] roads.geojson not found")

    if not patches_out and verbose:
        print(f"  [{city}] No OSM patches generated")

    return patches_out


# --- sources 4 and 5: OSM-generated geometry ---------------------------------

def _build_osm_generated(city: str, ann_filename: str, source_tag: str, kind: str,
                         patch_size: int = 64, max_per_city: int = 25,
                         verbose: bool = True) -> list:
    """
    Shared body of build_osm_generated_patches and
    build_osm_generated_water_patches. The notebook has these as two functions
    with byte-identical bodies apart from the annotation filename, the source
    tag and the log line; folding them keeps the two from drifting.
    """
    ann_path = _city_file(city, ann_filename)
    tile_path = _city_file(city, "tile_0_0.png")

    if not ann_path.exists() or not tile_path.exists():
        if verbose:
            print(f"  [{city}] no {ann_filename}, skipping.")
        return []

    ann_data = json.loads(ann_path.read_text())
    anns = [a for a in ann_data["annotations"]
            if not a.get("skipped", False) and a.get("human_label") in CAT2IDX]

    if not anns:
        if verbose:
            print(f"  [{city}] no usable OSM-generated {kind} segments.")
        return []

    def centroid(ann):
        x, y, w, h = ann["bbox"]
        return (x + w / 2, y + h / 2)

    # Greedy farthest-point spread -- 25 crops of one long road would teach the
    # model that road's specific look, not roads in general.
    if len(anns) > max_per_city:
        random.shuffle(anns)
        selected = [anns.pop()]
        while len(selected) < max_per_city and anns:
            sel_centroids = [centroid(a) for a in selected]
            best_idx, best_dist = 0, -1
            for i, a in enumerate(anns):
                cx, cy = centroid(a)
                min_dist = min((cx - sx) ** 2 + (cy - sy) ** 2 for sx, sy in sel_centroids)
                if min_dist > best_dist:
                    best_dist, best_idx = min_dist, i
            selected.append(anns.pop(best_idx))
        anns = selected

    tile_img = Image.open(tile_path).convert("RGB")
    tile_w, tile_h = tile_img.size

    patches_out = []
    for ann in anns:
        x, y, w, h = ann["bbox"]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(tile_w, x + w), min(tile_h, y + h)
        if x2 <= x1 or y2 <= y1:
            continue

        crop = tile_img.crop((x1, y1, x2, y2)).resize((patch_size, patch_size), Image.BILINEAR)
        crop_arr = np.array(crop, dtype=np.uint8)
        label_idx = CAT2IDX[ann["human_label"]]

        full_mask = decode_mask_rle(ann["mask_rle"])
        local_mask = full_mask[y1:y2, x1:x2]
        local_mask_img = Image.fromarray(local_mask.astype(np.uint8) * 255)
        local_mask_resized = local_mask_img.resize((patch_size, patch_size), Image.NEAREST)
        local_mask_arr = np.array(local_mask_resized) > 127

        label_mask = np.full((patch_size, patch_size), IGNORE_INDEX, dtype=np.uint8)
        label_mask[local_mask_arr] = label_idx

        patches_out.append({
            "image": crop_arr, "mask": label_mask, "city": city,
            "source": source_tag, "label": ann["human_label"],
            "geom": {"kind": "resize", "box": (int(x1), int(y1), int(x2), int(y2))},
        })

    if verbose:
        print(f"  [{city}] OSM-generated {kind} patches: {len(patches_out)} "
              f"(spatially-spread sample, capped at {max_per_city})")
    return patches_out


def build_osm_generated_patches(city: str, patch_size: int = 64,
                                max_per_city: int = 25, verbose: bool = True) -> list:
    """Source 4: ALL road types, real buffered geometry. Capped 25/city."""
    return _build_osm_generated(city, "osm_generated_annotations.json",
                                "osm_generated", "road", patch_size, max_per_city, verbose)


def build_osm_generated_water_patches(city: str, patch_size: int = 64,
                                      max_per_city: int = 25, verbose: bool = True) -> list:
    """Source 5: OSM water geometry -> standing_water. Capped 25/city."""
    return _build_osm_generated(city, "osm_generated_annotations_water.json",
                                "osm_generated_water", "water", patch_size, max_per_city, verbose)


# --- source 3: sliding windows over a real label canvas ----------------------

def build_tile_label_canvas(city: str, verbose: bool = True) -> tuple:
    """Every annotated segment's real mask, painted largest-area-first."""
    ann_path = _city_file(city, "annotations.json")
    tile_path = _city_file(city, "tile_0_0.png")

    if not ann_path.exists() or not tile_path.exists():
        return None, 0, 0

    ann_data = json.loads(ann_path.read_text())
    tile_img = Image.open(tile_path).convert("RGB")
    tile_w, tile_h = tile_img.size

    canvas = np.full((tile_h, tile_w), IGNORE_INDEX, dtype=np.uint8)

    usable = []
    for ann in ann_data["annotations"]:
        if ann.get("skipped", False) or ann.get("human_label") is None:
            continue
        if ann["human_label"] == "unknown":
            continue
        if ann["human_label"] not in CAT2IDX:
            continue
        usable.append(ann)

    usable.sort(key=lambda a: a.get("area", 0), reverse=True)

    n_real_mask, n_bbox_fallback = 0, 0
    for ann in usable:
        label_idx = CAT2IDX[ann["human_label"]]
        x, y, w, h = ann["bbox"]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(tile_w, x + w), min(tile_h, y + h)
        if x2 <= x1 or y2 <= y1:
            continue

        mask_rle = ann.get("mask_rle")
        if mask_rle is not None:
            full_mask = decode_mask_rle(mask_rle)
            canvas[full_mask] = label_idx
            n_real_mask += 1
        else:
            canvas[y1:y2, x1:x2] = label_idx
            n_bbox_fallback += 1

    if verbose:
        print(f"  [{city}] Label canvas built: {n_real_mask} real masks, "
              f"{n_bbox_fallback} bbox fallback, {len(usable)} total segments painted")

    return canvas, tile_w, tile_h


def build_sliding_window_patches(city: str, patch_size: int = 64, stride: int = 32,
                                 min_labeled_pct: float = 5.0,
                                 max_per_class_per_city: int = 30,
                                 verbose: bool = True) -> list:
    """
    Windows off the label canvas, keyed by DOMINANT label.

    min_labeled_pct=5.0 means >=204 of 4096 px labelled. The broken probe used
    >=32 px (~0.8%), which is where the "0.8% supervision density" figure in
    arm_a_diagnosis.md came from -- that was the threshold, never a measurement.
    """
    canvas, tile_w, tile_h = build_tile_label_canvas(city, verbose=verbose)
    if canvas is None:
        return []

    tile_path = _city_file(city, "tile_0_0.png")
    tile_img = Image.open(tile_path).convert("RGB")
    tile_arr = np.array(tile_img, dtype=np.uint8)

    candidates_by_label = defaultdict(list)
    min_labeled_px = int(patch_size * patch_size * min_labeled_pct / 100.0)

    for y_start in range(0, tile_h - patch_size, stride):
        for x_start in range(0, tile_w - patch_size, stride):
            x_end = x_start + patch_size
            y_end = y_start + patch_size

            label_mask = canvas[y_start:y_end, x_start:x_end]
            n_labeled = (label_mask != IGNORE_INDEX).sum()
            if n_labeled < min_labeled_px:
                continue

            crop_arr = tile_arr[y_start:y_end, x_start:x_end]

            vals, counts = np.unique(label_mask[label_mask != IGNORE_INDEX], return_counts=True)
            dominant_idx = int(vals[np.argmax(counts)]) if len(vals) else IGNORE_INDEX
            dominant_label = CATEGORIES[dominant_idx] if dominant_idx != IGNORE_INDEX else "unknown"

            candidates_by_label[dominant_label].append({
                "image": crop_arr, "mask": label_mask.copy(), "city": city,
                "source": "sliding_window", "label": dominant_label,
                "geom": {"kind": "window", "xy": (int(x_start), int(y_start))},
            })

    patches_out = []
    capped_summary = []
    for label, items in candidates_by_label.items():
        if len(items) > max_per_class_per_city:
            kept = random.sample(items, max_per_class_per_city)
            capped_summary.append(f"{label}: {len(items)}->{max_per_class_per_city}")
        else:
            kept = items
        patches_out.extend(kept)

    if verbose:
        cap_note = f' | capped: {", ".join(capped_summary)}' if capped_summary else ""
        print(f"  [{city}] Sliding window patches: {len(patches_out)} "
              f"(min {min_labeled_pct}% coverage, max {max_per_class_per_city}/class){cap_note}")
    return patches_out


# --- cell 13: assembly -------------------------------------------------------

def build_all_patches(cities=None, verbose: bool = True) -> list:
    """
    Cell 13, in its exact builder order. `reseed()` first so a rebuild starts
    from the notebook's cell-11 RNG state regardless of what ran before.
    """
    reseed()
    cities = list(cities) if cities is not None else list(LOCO_CLEAN_CITIES)

    all_patches = []
    if verbose:
        print("Building dataset from all cities...")
    for city in cities:
        if verbose:
            print(f"\n--- {city.upper()} ---")
        all_patches.extend(build_sam_patches(city, verbose=verbose))
        all_patches.extend(build_osm_patches(city, verbose=verbose))
        all_patches.extend(build_osm_generated_patches(city, verbose=verbose))
        all_patches.extend(build_osm_generated_water_patches(city, verbose=verbose))
        all_patches.extend(build_sliding_window_patches(city, verbose=verbose))

    if verbose:
        print(f"\nRaw total: {len(all_patches)} patches")

    random.shuffle(all_patches)     # no oversampling -- see cell 13's note
    return all_patches


# --- cells 18 / 39: the class-weight formula ---------------------------------

def class_weights_from(patches) -> np.ndarray:
    """
    Inverse patch-frequency, normalised to sum to NUM_CLASSES.

    Cell 18 applies this to `all_patches`; cell 39 -- the production cell that
    wrote the checkpoint -- applies it to `train_patches`, the 90% split. The
    deployed weights are the cell 39 ones.
    """
    actual_counts = Counter(p["label"] for p in patches)
    counts = np.array([actual_counts.get(c, 1) for c in CATEGORIES], dtype=np.float32)
    counts = np.maximum(counts, 1)
    weights = 1.0 / counts
    return weights / weights.sum() * NUM_CLASSES


def implied_counts(weights, total: int) -> np.ndarray:
    """
    Invert the formula: counts are proportional to 1/weight, so a weight vector
    plus a total recovers the per-class patch counts it was computed from.
    """
    inv = 1.0 / np.asarray(weights, dtype=np.float64)
    return total * inv / inv.sum()
