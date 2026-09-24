"""
Input pipelines and encoders for the band/reflectance probe.

Four arms, two factors crossed, so each change attributes independently:

    A  RGB    + per-tile stretch     (current production config)
    B  RGB    + absolute reflectance
    C  6-band + per-tile stretch
    D  6-band + absolute reflectance

FACTOR 1 — BANDS. Production loads SENTINEL2_RGB_MOCO (in_chans=3,
bands ['B4','B3','B2']); NIR/SWIR1/SWIR2 are exported and discarded (C41).
The 6-band arms load the 13-band SENTINEL2_ALL_MOCO and select channels.

  VERIFIED CHANNEL SELECTION. That checkpoint's band order is
  ['B1','B2','B3','B4','B5','B6','B7','B8','B8a','B9','B10','B11','B12'] --
  13 entries with B10 PRESENT, so there is no 12-band shift. Our six map to:
      Blue  B2 -> 1     NIR   B8  ->  7
      Green B3 -> 2     SWIR1 B11 -> 11
      Red   B4 -> 3     SWIR2 B12 -> 12
  i.e. [1, 2, 3, 7, 11, 12], checked against the enum at import rather than
  hardcoded on faith. Getting this wrong would feed SWIR into filters
  pretrained on cirrus, silently -- the exact failure the Task 1 verification
  was looking for.

FACTOR 2 — SCALING. The checkpoints' own transform is
Normalize(mean=[0], std=[10000]): Sentinel-2 DN / 10,000, absolute surface
reflectance. raw.tif is ALREADY on that scale. Production instead feeds a
per-tile 2nd/98th percentile stretch / 255, which lands in the same [0,1] range
but is tile-relative -- measured inflation 1.1x (Jakarta) to 3.1x (Accra), so
identical ground gives different input depending on its tile (C41).

models/production/ is never read or written here.
"""
from __future__ import annotations

import glob
import os

import numpy as np
import rasterio
import torch
import torch.nn as nn
from PIL import Image
from rasterio.windows import Window
from torchgeo.models import ResNet50_Weights, resnet50

from ingestion.sentinel2 import S2_BAND_NAMES   # ["Blue","Green","Red","NIR","SWIR1","SWIR2"]

S2_NAME_TO_ID = {"Blue": "B2", "Green": "B3", "Red": "B4",
                 "NIR": "B8", "SWIR1": "B11", "SWIR2": "B12"}


def all_moco_channel_indices() -> list[int]:
    """
    Indices into SENTINEL2_ALL_MOCO's 13 channels for our six bands.

    Derived from the enum's own band list, never hardcoded -- if torchgeo
    reorders or drops a band, this moves with it or raises.
    """
    bands = list(ResNet50_Weights.SENTINEL2_ALL_MOCO.meta["bands"])
    idx = []
    for name in S2_BAND_NAMES:
        bid = S2_NAME_TO_ID[name]
        if bid not in bands:
            raise ValueError(
                f"{bid} ({name}) is absent from SENTINEL2_ALL_MOCO's band list "
                f"{bands} -- the channel selection cannot be built."
            )
        idx.append(bands.index(bid))
    if len(set(idx)) != len(idx):
        raise ValueError(f"duplicate channel indices {idx}")
    return idx


ALL_MOCO_INDICES = all_moco_channel_indices()   # verified: [1, 2, 3, 7, 11, 12]


# ── Inputs ───────────────────────────────────────────────────────────────────

def _run_dir(city: str) -> str:
    cands = [d for d in sorted(glob.glob(f"data/pipeline_runs/{city}_*"))
             if os.path.exists(os.path.join(d, "tiles", "tile_0_0.png"))
             and os.path.exists(os.path.join(d, "annotations.json"))
             and os.path.exists(os.path.join(d, "masks.json"))]
    if not cands:
        raise FileNotFoundError(f"no qualifying run dir for {city}")
    return cands[-1]


def _stretch(a: np.ndarray) -> np.ndarray:
    """
    The production per-tile 2nd/98th percentile stretch, per band.

    Applied per band rather than jointly, matching generate_rgb_preview_tiles'
    behaviour of stretching the stacked RGB array as a whole only because it
    stacks first; for 6 bands, per-band is the faithful generalisation.
    """
    out = np.empty_like(a, dtype=np.float32)
    for c in range(a.shape[0]):
        p2, p98 = np.percentile(a[c], (2, 98))
        out[c] = np.clip((a[c] - p2) / (p98 - p2), 0, 1) if p98 > p2 else 0.0
    return out


def build_input(city: str, mode: str) -> np.ndarray:
    """
    (C, H, W) float32 in [0, 1], aligned to the label canvas.

    The PNG tile is a top-left crop of raw.tif when the raster exceeds the tile
    size (3 of 11 cities), so raw.tif is read through the same window -- without
    that, labels would be paired with the wrong pixels for those cities.
    """
    rd = _run_dir(city)
    png = os.path.join(rd, "tiles", "tile_0_0.png")
    with Image.open(png) as im:
        w, h = im.size
        rgb_png = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0

    if mode == "rgb_stretch":
        return np.transpose(rgb_png, (2, 0, 1))            # production path

    with rasterio.open(os.path.join(rd, "raw.tif")) as src:
        raw = src.read(window=Window(0, 0, w, h)).astype(np.float32)

    if mode == "rgb_abs":
        # raw.tif band order is S2_BAND_NAMES; take Red, Green, Blue to match
        # the checkpoint's ['B4','B3','B2'].
        order = [S2_BAND_NAMES.index(b) for b in ("Red", "Green", "Blue")]
        return np.clip(raw[order], 0.0, 1.0)
    if mode == "6band_abs":
        return np.clip(raw, 0.0, 1.0)
    if mode == "6band_stretch":
        return _stretch(raw)
    raise ValueError(f"unknown mode {mode!r}")


# ── Encoders ─────────────────────────────────────────────────────────────────

def build_encoder(in_chans: int):
    """
    ResNet50 encoder for 3 or 6 input channels.

    For 6, SENTINEL2_ALL_MOCO's conv1 is SELECTED down (not averaged, not
    re-initialised) so each band keeps the filter it was pretrained with. The
    selection is the verified index list, and it is asserted here rather than
    trusted.
    """
    if in_chans == 3:
        enc = resnet50(weights=ResNet50_Weights.SENTINEL2_RGB_MOCO)
        assert enc.conv1.weight.shape[1] == 3
        return enc

    if in_chans != 6:
        raise ValueError("only 3 or 6 input channels are supported")

    enc = resnet50(weights=ResNet50_Weights.SENTINEL2_ALL_MOCO)
    w13 = enc.conv1.weight.data
    assert w13.shape[1] == 13, f"expected a 13-band conv1, got {tuple(w13.shape)}"

    idx = ALL_MOCO_INDICES
    new = nn.Conv2d(6, w13.shape[0], kernel_size=enc.conv1.kernel_size,
                    stride=enc.conv1.stride, padding=enc.conv1.padding, bias=False)
    new.weight.data = w13[:, idx, :, :].clone()
    assert new.weight.shape[1] == 6
    enc.conv1 = new
    return enc
