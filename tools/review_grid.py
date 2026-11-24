"""Recreate the outlined optical evidence window from a manifest cell and its source TIFF."""
import numpy as np
import rasterio
from affine import Affine
from PIL import Image, ImageDraw
from rasterio.enums import ColorInterp, Resampling
from rasterio.vrt import WarpedVRT


def render_cell(path, epsg, col, row, *, bands=(1, 2, 3)):
    """Render the 30 m cell with one cell of context on all sides.

    col and row are the eastward and northward 30 m lattice indices in review.json.
    Returns (PIL RGB image, full_rgb_coverage). The outline is outside the cell.
    Pass source RGB band order explicitly for multispectral products.
    """
    transform = Affine(.5, 0, col * 30 - 30, 0, -.5, row * 30 + 60)
    with rasterio.open(path) as source, WarpedVRT(
        source, crs=f'EPSG:{epsg}', transform=transform, width=180, height=180,
        resampling=Resampling.nearest,
    ) as view:
        rgb = np.moveaxis(view.read(bands), 0, 2)
        if ColorInterp.alpha in view.colorinterp:
            mask = view.read(view.colorinterp.index(ColorInterp.alpha) + 1) > 0
        else:
            mask = view.dataset_mask() > 0
    coverage = rgb.max(axis=2) > 0
    if coverage.any():
        low, high = np.percentile(rgb[coverage], [1, 99])
        rgb = np.uint8(np.clip((rgb.astype(float) - low) / max(1, high - low), 0, 1) * 255)
    image = Image.fromarray(rgb)
    ImageDraw.Draw(image).rectangle((59, 59, 120, 120), outline='#32f9dc')
    return image, bool((mask & coverage)[60:120, 60:120].all())
