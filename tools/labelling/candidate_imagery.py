"""Candidate patches on the tile's own dated RGB image, including separate visual hints."""
from __future__ import annotations

import hashlib

import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.features import shapes
from rasterio.warp import reproject
from scipy import ndimage
from shapely.geometry import shape

from .candidate_sources import _suggest


def rgb_masks(channels, observed):
    """Visible colour contrasts. A deep shadow is never assigned a final surface."""
    r, g, b = channels.astype("float32")
    total = np.maximum(r + g + b, 1)
    brightness = (r + g + b) / 3
    # A conservative dark cap keeps dark roofs or water in the visual-hint stream.
    shadow = observed & (brightness <= 48) & (np.maximum.reduce([r, g, b]) <= 68)
    green = observed & ~shadow & ((2 * g - r - b) / total >= .13) & (g > r + 6) & (g > b + 6)
    # No NIR in these RGB mosaics. This flags smooth blue-green patches for inspection only.
    smooth = ndimage.maximum_filter(brightness, 5) - ndimage.minimum_filter(brightness, 5) <= 23
    blue = observed & ~shadow & ~green & smooth & (b > r + 8) & (g > r + 5) & (b >= .83*g)
    return {"vegetation_rgb":green, "hint_water_rgb":blue, "hint_shadow_rgb":shadow}


def imagery_candidates(src, imagery_version):
    if src.dtypes[:3] != ("uint8",) * 3 or not all(c in src.colorinterp for c in
            (ColorInterp.red, ColorInterp.green, ColorInterp.blue)):
        return [], {"status":"unavailable", "reason":"RGB candidate rules require identified 8-bit RGB bands"}
    ids = [src.colorinterp.index(c) + 1 for c in (ColorInterp.red, ColorInterp.green, ColorInterp.blue)]
    # The bounded preview averages camera noise while retaining sub-metre patches on 200 m tiles.
    ratio = min(1., 800/max(src.width, src.height))
    h, w = max(1,round(src.height*ratio)), max(1,round(src.width*ratio))
    rgb = src.read(ids, out_shape=(3,h,w), resampling=Resampling.average)
    mat = src.transform * rasterio.Affine.scale(src.width/w, src.height/h)
    valid = np.ones((h,w), dtype=bool)
    for band in ids:
        coverage = np.zeros((h,w), dtype="uint8")
        reproject(src.read_masks(band), coverage, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=mat, dst_crs=src.crs, resampling=Resampling.min, num_threads=1)
        valid &= coverage == 255
    pixel_area = abs(mat.a * mat.e)
    descriptions = {
        "vegetation_rgb":("vegetation", 4., "RGB excess-green patch. Check plants versus green roofing or turf."),
        "hint_water_rgb":("water", 8., "Smooth blue-green RGB patch. Water, shadows, roofs or pools can resemble one another."),
        "hint_shadow_rgb":("shadow_full", 4., "Darkness only. Identify the underlying surface when possible and add the partial-shadow flag.")
    }
    out = []
    for layer, mask in rgb_masks(rgb, valid).items():
        label, min_area, note = descriptions[layer]
        # Four-connected patches, conservative single-pixel opening and minimum suggestion area.
        smooth = ndimage.binary_opening(mask, structure=ndimage.generate_binary_structure(2, 1))
        connected, _ = ndimage.label(smooth)
        counts = np.bincount(connected.ravel())
        keep = counts * pixel_area >= min_area
        keep[0] = False
        mask = keep[connected] & valid
        for poly, _ in shapes(mask.astype("uint8"), mask=mask, transform=mat):
            g = shape(poly).simplify(min(abs(mat.a),abs(mat.e))/2, preserve_topology=True)
            if g.area < min_area:
                continue
            ident = hashlib.sha256(g.normalize().wkb).hexdigest()[:24]
            out.append(_suggest(layer,label,"tile_rgb",ident,imagery_version,g,note))
    return out, {"status":"available", "method":"visible-colour-v1","width":w, "height":h,
                 "sample_spacing_m":[mat.a, -mat.e], "mask_valid_cells":int(valid.sum())}
