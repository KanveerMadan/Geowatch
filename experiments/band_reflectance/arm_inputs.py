"""
The four arms, re-extracted onto PRODUCTION patch geometry.

The broken probe built its own patches -- native-resolution sliding windows over
sparse multi-class canvases -- and its control never trained. This module keeps
the patch set fixed (the 5-builder production rebuild) and varies only the
pixels underneath it:

    A  rgb_stretch     RGB, per-tile percentile stretch   (production)
    B  rgb_abs         RGB, absolute surface reflectance
    C  6band_stretch   6 bands, per-tile percentile stretch
    D  6band_abs       6 bands, absolute surface reflectance

WHERE THE PIXELS COME FROM. `tiles/tile_0_0.npy` is the 6-band float32
reflectance array, and it is pixel-aligned with `tiles/tile_0_0.png` -- same
height and width, verified per city at load. So a patch's geometry (a window
origin, or a bbox that gets resized) indexes both identically, and every arm
sees the same ground.

Channel order in the .npy is `ingestion.sentinel2.S2_BAND_NAMES` --
[Blue, Green, Red, NIR, SWIR1, SWIR2]. The PNG stacks [Red, Green, Blue] to
match the checkpoint's ['B4','B3','B2'] (C41), so the RGB arms select [2, 1, 0].

THE STRETCH IS JOINT, NOT PER-BAND. `tiler.py:517` computes ONE p2/p98 pair
over the whole stacked RGB array, not one pair per band. So the faithful 6-band
generalisation is a single pair over the stacked 6-band array, which is what
`_stretch` does here. This deliberately differs from `arms.py::_stretch`, which
took per-band percentiles -- that module belongs to the broken probe, and
per-band would give arm C a per-channel normalisation production never applies.

ONE RESIZE PATH FOR ALL FOUR ARMS. Production resizes a bbox crop with PIL
BILINEAR on uint8; arms B, C and D have no uint8 stage. Rather than let arm A
use one resize and the others a different one, every arm here resizes float32
per channel through PIL's 'F' mode. That makes arm A differ from the exact
production patch by resize rounding -- which is fine, and is precisely why the
fidelity run is a separate run: it establishes production fidelity on the exact
production patches, so the comparison runs are free to optimise for being
identical to EACH OTHER instead.

Masks are never rebuilt. Every arm reuses the patch's own label mask, so the
label tensors are byte-identical across arms by construction, not by luck.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.band_reflectance.production_patches_v2 import (  # noqa: E402
    PATCH_SIZE, _city_file, _run_dir,
)
from ingestion.sentinel2 import S2_BAND_NAMES  # noqa: E402

MODES = ("rgb_stretch", "rgb_abs", "6band_stretch", "6band_abs")
RGB_ORDER = [S2_BAND_NAMES.index(b) for b in ("Red", "Green", "Blue")]   # [2, 1, 0]


def _stretch(a: np.ndarray) -> np.ndarray:
    """
    Production's per-tile 2nd/98th percentile stretch: ONE pair of percentiles
    over the whole stacked array (tiler.py:517), not one pair per band.
    """
    p2, p98 = np.percentile(a, (2, 98))
    if p98 <= p2:
        return np.clip(a, 0.0, 1.0).astype(np.float32)
    return np.clip((a - p2) / (p98 - p2), 0.0, 1.0).astype(np.float32)


def load_city_source(city: str, mode: str) -> np.ndarray:
    """(H, W, C) float32 in [0, 1] for one city under one arm."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")

    png_path = _city_file(city, "tile_0_0.png")
    with Image.open(png_path) as im:
        png_w, png_h = im.size

    npy_path = _run_dir(city) / "tiles" / "tile_0_0.npy"
    if not npy_path.is_file():
        raise FileNotFoundError(f"{city}: no {npy_path}")
    raw = np.load(npy_path).astype(np.float32)          # (H, W, 6), reflectance

    if raw.shape[:2] != (png_h, png_w):
        raise ValueError(
            f"{city}: .npy is {raw.shape[:2]} but the PNG is {(png_h, png_w)}. "
            "Patch geometry indexes both, so they must align."
        )

    if mode == "rgb_stretch":
        with Image.open(png_path) as im:
            return np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    if mode == "rgb_abs":
        return np.clip(raw[:, :, RGB_ORDER], 0.0, 1.0)
    if mode == "6band_abs":
        return np.clip(raw, 0.0, 1.0)
    return _stretch(raw)                                 # 6band_stretch


def _resize_f32(crop: np.ndarray, size: int = PATCH_SIZE) -> np.ndarray:
    """Bilinear resize of an (h, w, C) float array, per channel, via PIL 'F'."""
    h, w, c = crop.shape
    if (h, w) == (size, size):
        return crop.astype(np.float32, copy=True)
    out = np.empty((size, size, c), dtype=np.float32)
    for k in range(c):
        out[:, :, k] = np.asarray(
            Image.fromarray(crop[:, :, k].astype(np.float32), mode="F")
                 .resize((size, size), Image.BILINEAR),
            dtype=np.float32)
    return out


def extract(source: np.ndarray, geom: dict, size: int = PATCH_SIZE) -> np.ndarray:
    """Re-cut one patch out of a city source array, using its recorded geometry."""
    kind = geom["kind"]
    if kind == "window":
        x, y = geom["xy"]
        crop = source[y:y + size, x:x + size, :]
        if crop.shape[:2] != (size, size):
            raise ValueError(f"window {geom} fell outside {source.shape}")
        return crop.astype(np.float32, copy=True)
    if kind == "resize":
        x1, y1, x2, y2 = geom["box"]
        return _resize_f32(source[y1:y2, x1:x2, :], size)
    raise ValueError(f"unknown geometry kind {kind!r}")


def build_arm_images(patches: list, mode: str) -> list:
    """
    Per-patch (64, 64, C) float32 arrays for one arm, in the patch list's order.

    Sources are loaded once per city, not once per patch.
    """
    cache: dict = {}
    out = []
    for p in patches:
        city = p["city"]
        if city not in cache:
            cache[city] = load_city_source(city, mode)
        out.append(extract(cache[city], p["geom"]))
    return out
