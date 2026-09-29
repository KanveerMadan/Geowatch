"""
SAM-assisted drafting for item 21 tracing -- NOT ADOPTED (decided
2026-09-29: workflow overhead, and SAM draws roof outlines where the Karachi
rule requires the building base). Kept, unused. Tracing is fully manual,
and so are the QC re-traces. Proposal of 2026-09-29, tested on the practice
tile PRACTICE_formal only.

Workflow (the labeller in QGIS, this script in the repo venv):
  1. In labels.gpkg, add points to the `sam_prompts` layer on hr.tif: a
     positive point on an object; optional extra positive / negative points
     for the same object share its `grp` number (a new point gets the next
     number by default). Save the layer edits.
  2. Run  python -m labelling.sam_draft <tile dir>
     Each new group becomes a candidate polygon in `sam_candidates`.
  3. The labeller copies the candidates they accept into `labels`, edits the
     vertices, and sets `label` by hand. SAM never writes to `labels` and
     never sets a label.

Model: the repo's segment-anything ViT-B checkpoint, verified against
ARTIFACT_HASHES.txt before every run. Prompting follows the
segment-anything README: a single point asks for 3 masks and the one with
the highest predicted IoU is kept; several points ask for one mask.

Speed: the image encoder is the slow part (~1.8 s per 1024 px window on
Apple MPS, measured 2026-09-29; the prompt decoder ~0.1 s). Each window is
encoded once, on first use, and cached in <tile>/sam_embeddings/ (not
tracked), so later clicks in that window only run the decoder.

Numbers, with their basis:
  window 1024   SAM's encoder input side (ResizeLongestSide(1024)); a window
                is encoded at the imagery's native resolution, no resampling
  stride 512    half a window: every point lies in the central half of some
                window; a group uses the window whose edges are furthest
                from all its points
  simplify      Douglas-Peucker at ONE imagery pixel: removes the pixel
                staircase of the vectorised mask, moves no edge by more
                than a pixel
  components    only the mask components that contain a positive point are
                kept (the click's intent; no area threshold)
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKPOINT = os.path.join(REPO, "models", "sam", "sam_vit_b.pth")
HASHES = os.path.join(REPO, "ARTIFACT_HASHES.txt")
SAM_INPUT_PX = 1024
PROMPTS, CANDIDATES = "sam_prompts", "sam_candidates"
PROMPT_FIELDS = ["grp", "positive"]
CANDIDATE_FIELDS = ["grp", "score", "n_points", "model_sha256", "drafted_utc"]


class SamDraftError(RuntimeError):
    pass


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def recorded_hash(rel: str = "models/sam/sam_vit_b.pth") -> str:
    with open(HASHES) as fh:
        for line in fh:
            h, _, p = line.strip().partition("  ")
            if os.path.normpath(p) == os.path.normpath(rel):
                return h
    raise SamDraftError(f"{rel} is not listed in ARTIFACT_HASHES.txt")


def verify_checkpoint(path: str = CHECKPOINT) -> str:
    got, want = sha256(path), recorded_hash()
    if got != want:
        raise SamDraftError(f"{path}: sha256 {got} does not match ARTIFACT_HASHES.txt ({want})")
    return got


# ── layers ───────────────────────────────────────────────────────────────────

def prompts_qml() -> str:
    """Points: green positive, red negative; `grp` defaults to max + 1."""
    sym = lambda name, rgb: f'''      <symbol type="marker" name="{name}" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option name="color" type="QString" value="{rgb},255"/>
            <Option name="name" type="QString" value="circle"/>
            <Option name="outline_color" type="QString" value="255,255,255,255"/>
            <Option name="size" type="QString" value="2.4"/>
          </Option>
        </layer>
      </symbol>'''
    return f'''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<!-- SAM prompt points (labelling/sam_draft.py). Generated; do not hand-edit. -->
<qgis version="3.28" styleCategories="Symbology|Fields|Forms">
  <renderer-v2 type="categorizedSymbol" attr="positive" symbollevels="0" enableorderby="0" forceraster="0">
    <categories>
      <category symbol="0" value="1" label="positive" render="true"/>
      <category symbol="1" value="0" label="negative" render="true"/>
    </categories>
    <symbols>
{sym("0", "0,200,0")}
{sym("1", "220,0,0")}
    </symbols>
  </renderer-v2>
  <fieldConfiguration>
    <field name="positive" configurationFlags="None">
      <editWidget type="CheckBox">
        <config><Option type="Map">
          <Option name="CheckedState" type="QString" value="1"/>
          <Option name="UncheckedState" type="QString" value="0"/>
        </Option></config>
      </editWidget>
    </field>
  </fieldConfiguration>
  <defaults>
    <default field="grp" expression="coalesce(maximum(&quot;grp&quot;), 0) + 1" applyOnUpdate="0"/>
    <default field="positive" expression="1" applyOnUpdate="0"/>
  </defaults>
</qgis>
'''


def candidates_qml() -> str:
    """Outline only (magenta dashed), so a candidate never looks like a label."""
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<!-- SAM candidate polygons (labelling/sam_draft.py). Generated; do not hand-edit.
     Candidates are NOT labels: copy the accepted ones into `labels`. -->
<qgis version="3.28" styleCategories="Symbology">
  <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">
    <symbols>
      <symbol type="fill" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleFill" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option name="color" type="QString" value="0,0,0,0"/>
            <Option name="outline_color" type="QString" value="255,0,255,255"/>
            <Option name="outline_style" type="QString" value="dash"/>
            <Option name="outline_width" type="QString" value="0.5"/>
            <Option name="style" type="QString" value="no"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
'''


def add_sam_layers(gpkg: str, crs: str) -> None:
    """Add the empty prompt and candidate layers to an existing labels.gpkg.
    Never touches the `labels` layer."""
    import geopandas as gpd
    import pandas as pd
    from labelling.gpkg_style import add_layer
    prompts = gpd.GeoDataFrame({"grp": pd.Series([], dtype="int32"), "positive": pd.Series([], dtype="int32")},
                               geometry=gpd.GeoSeries([], crs=crs), crs=crs)
    cands = gpd.GeoDataFrame({"grp": pd.Series([], dtype="int32"), "score": pd.Series([], dtype="float64"),
                              "n_points": pd.Series([], dtype="int32"),
                              "model_sha256": pd.Series([], dtype="object"),
                              "drafted_utc": pd.Series([], dtype="object")},
                             geometry=gpd.GeoSeries([], crs=crs), crs=crs)
    add_layer(gpkg, prompts, PROMPTS, prompts_qml(), geometry_type="Point")
    add_layer(gpkg, cands, CANDIDATES, candidates_qml(), geometry_type="Polygon")


# ── geometry ─────────────────────────────────────────────────────────────────

def window_starts(n: int, size: int = SAM_INPUT_PX) -> list:
    """Window origins along one axis: stride size/2, the last flush with the edge."""
    if n <= size:
        return [0]
    starts = list(range(0, n - size, size // 2))
    return starts + [n - size] if starts[-1] != n - size else starts


def pick_window(rows: np.ndarray, cols: np.ndarray, shape: tuple, size: int = SAM_INPUT_PX) -> tuple:
    """(r0, c0, h, w) of the grid window holding every point with the largest
    margin to its edges."""
    h, w = min(size, shape[0]), min(size, shape[1])
    best, key = None, None
    for r0 in window_starts(shape[0], size):
        for c0 in window_starts(shape[1], size):
            margin = min((rows - r0).min(), (r0 + h - 1 - rows).min(),
                         (cols - c0).min(), (c0 + w - 1 - cols).min())
            if margin >= 0 and (key is None or margin > key):
                best, key = (r0, c0, h, w), margin
    if best is None:
        raise SamDraftError("the points of one group do not fit in one SAM window; "
                            "use points closer together")
    return best


def mask_to_polygons(mask: np.ndarray, transform, positive_xy: list, res: float) -> list:
    """Vectorise, keep only components containing a positive point, simplify
    at one pixel."""
    from rasterio.features import shapes
    from shapely.geometry import Point, shape
    keep = []
    for geom, v in shapes(mask.astype(np.uint8), mask=mask.astype(bool), transform=transform):
        if v != 1:
            continue
        g = shape(geom)
        if any(g.contains(Point(x, y)) for x, y in positive_xy):
            keep.append(g.simplify(res, preserve_topology=True))
    return keep


# ── drafting ─────────────────────────────────────────────────────────────────

def _device() -> str:
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def load_predictor():
    from segment_anything import SamPredictor, sam_model_registry
    verify_checkpoint()
    sam = sam_model_registry["vit_b"](checkpoint=CHECKPOINT)
    sam.to(device=_device())
    return SamPredictor(sam)


def set_window(predictor, src, win_rc: tuple, cache_dir: str) -> None:
    """Encode the window (or restore its cached encoding) into `predictor`.
    Restoring sets the same attributes SamPredictor.set_image sets
    (segment-anything 1.0)."""
    import torch
    from rasterio.windows import Window
    r0, c0, h, w = win_rc
    p = os.path.join(cache_dir, f"r{r0}_c{c0}_{h}x{w}.pt")
    if os.path.exists(p):
        z = torch.load(p, map_location=predictor.device)
        predictor.reset_image()
        predictor.features = z["features"]
        predictor.original_size, predictor.input_size = z["original_size"], z["input_size"]
        predictor.is_image_set = True
        return
    img = np.moveaxis(src.read([1, 2, 3], window=Window(c0, r0, w, h)), 0, -1)
    predictor.set_image(np.ascontiguousarray(img))
    os.makedirs(cache_dir, exist_ok=True)
    torch.save({"features": predictor.features.cpu(), "original_size": predictor.original_size,
                "input_size": predictor.input_size, "model_sha256": recorded_hash()}, p)


def draft(tile_dir: str, predictor=None) -> dict:
    """Draft a candidate for every prompt group that has none yet."""
    import pyogrio
    import rasterio
    from rasterio.transform import rowcol
    from rasterio.windows import Window
    cache_dir = os.path.join(tile_dir, "sam_embeddings")
    gpkg = os.path.join(tile_dir, "labels.gpkg")
    layers = {row[0] for row in pyogrio.list_layers(gpkg)}
    if not {PROMPTS, CANDIDATES} <= layers:
        raise SamDraftError(f"{gpkg}: no {PROMPTS}/{CANDIDATES} layers; run with --setup first")
    prompts = pyogrio.read_dataframe(gpkg, layer=PROMPTS)
    done = set(pyogrio.read_dataframe(gpkg, layer=CANDIDATES, read_geometry=False)["grp"].tolist())
    todo = sorted(set(prompts["grp"].dropna().astype(int)) - done)
    if not todo:
        return {"drafted": [], "failed": [], "polygons": 0}
    if prompts["grp"].isna().any():
        raise SamDraftError(f"{gpkg}: a prompt point has no grp")
    model_sha = recorded_hash()
    predictor = predictor or load_predictor()
    import geopandas as gpd
    out, failed, stamp = [], [], datetime.now(timezone.utc).isoformat(timespec="seconds")
    with rasterio.open(os.path.join(tile_dir, "hr.tif")) as src:
        res = src.res[0]
        for grp in todo:
            pts = prompts[prompts["grp"] == grp]
            xs, ys = pts.geometry.x.to_numpy(), pts.geometry.y.to_numpy()
            rows, cols = rowcol(src.transform, xs, ys)
            rows, cols = np.asarray(rows), np.asarray(cols)
            if ((rows < 0) | (cols < 0) | (rows >= src.height) | (cols >= src.width)).any():
                raise SamDraftError(f"group {grp}: a point lies outside hr.tif")
            r0, c0, h, w = pick_window(rows, cols, (src.height, src.width))
            win = Window(c0, r0, w, h)
            set_window(predictor, src, (r0, c0, h, w), cache_dir)
            coords = np.stack([cols - c0, rows - r0], axis=1).astype(float)   # SAM wants (x, y)
            labels = np.array(pts["positive"].astype(int).to_numpy(), copy=True)
            if labels.sum() == 0:
                raise SamDraftError(f"group {grp}: no positive point")
            masks, scores, _ = predictor.predict(point_coords=coords, point_labels=labels,
                                                 multimask_output=len(pts) == 1)
            best = int(np.argmax(scores))
            pos = [(x, y) for x, y, l in zip(xs, ys, labels) if l == 1]
            polys = mask_to_polygons(masks[best], src.window_transform(win), pos, res)
            if not polys:                       # the mask missed the click: nothing written,
                failed.append(int(grp))         # so the group is retried on the next run
                continue
            for g in polys:
                out.append({"grp": int(grp), "score": float(scores[best]), "n_points": int(len(pts)),
                            "model_sha256": model_sha, "drafted_utc": stamp, "geometry": g})
        crs = src.crs.to_string()
    drafted = sorted({r["grp"] for r in out})
    if out:
        pyogrio.write_dataframe(gpd.GeoDataFrame(out, crs=crs), gpkg, layer=CANDIDATES, append=True)
        record_use(tile_dir, model_sha, len(drafted))
    return {"drafted": drafted, "failed": failed, "polygons": len(out)}


def record_use(tile_dir: str, model_sha: str, n_groups: int) -> None:
    """Per-tile method record in metadata.json (the proposal's 'method
    recorded per tile')."""
    p = os.path.join(tile_dir, "metadata.json")
    with open(p) as fh:
        meta = json.load(fh)
    s = meta.setdefault("sam_assist", {"model": "segment-anything vit_b", "model_sha256": model_sha,
                                       "script": "labelling/sam_draft.py", "groups_drafted": 0})
    s["groups_drafted"] += n_groups
    meta["tracing_method"] = "sam_assisted"
    with open(p, "w") as fh:
        json.dump(meta, fh, indent=1)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tile_dir")
    ap.add_argument("--setup", action="store_true", help="add the empty sam_prompts / sam_candidates layers")
    a = ap.parse_args(argv)
    if a.setup:
        import pyogrio
        crs = pyogrio.read_info(os.path.join(a.tile_dir, "labels.gpkg"), layer="labels")["crs"]
        add_sam_layers(os.path.join(a.tile_dir, "labels.gpkg"), crs)
        print(f"added {PROMPTS} and {CANDIDATES} to {a.tile_dir}/labels.gpkg")
        return
    r = draft(a.tile_dir)
    print(json.dumps(r))
    for g in r["failed"]:
        print(f"group {g}: SAM's mask did not contain the click -- move the point(s) and run again")


if __name__ == "__main__":
    sys.path.insert(0, REPO)
    main()
