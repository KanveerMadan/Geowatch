"""
Render contact sheets of candidate label patches for visual class assignment.

Every patch on every sheet is assigned by LOOKING at it. This module only picks
candidate locations and draws them; it never assigns a class.

Why patches are drawn WITH CONTEXT. The Accra run inspected bare 5 m crops and
its first labelling pass was wrong because of it: at 1x zoom, flat roofs with
seams read as bare ground and water with floating rubbish read as bare. Both
mistakes are obvious once the surrounding 30 m is visible. So each tile here
shows a CONTEXT_M surround, upscaled, with the scored PATCH_M region boxed in
red -- the class assigned is the class of the BOXED AREA, judged in situ.

Targeted sampling is supported (`hint`) because random sampling under-hits rare
classes -- water is ~1% of the Nairobi extent. A hint only PROPOSES locations;
acceptance is still a human decision made on the rendered imagery, and rejects
are recorded. That is the same protocol the Accra sheet 4 used.
"""

import json
import os

import numpy as np
import rasterio
from PIL import Image, ImageDraw

TILE_PX = 300          # rendered size of one tile
CONTEXT_M = 30.0       # surround shown around each patch
GRID = 5               # GRID x GRID tiles per sheet
PAD = 26               # room for the index label


def sample_patches(path, n, seed, hint=None, exclude=None, patch_m=6.0):
    """Pick n candidate patch origins (native px) inside valid imagery.

    hint(rgb_lowres, transform) -> boolean mask at low res, marking where to
    concentrate candidates. Used only to PROPOSE; every proposal is still
    judged by eye.
    """
    rng = np.random.default_rng(seed)
    with rasterio.open(path) as src:
        px = src.transform[0]
        pn = int(round(patch_m / px))
        ctx = int(round(CONTEXT_M / px))
        H, W = src.height, src.width
        # low-res overview for validity + hint
        DS = 32
        lo = src.read(out_shape=(3, H // DS, W // DS)).astype(np.float32)
        lo = np.transpose(lo, (1, 2, 0))
        valid = lo.sum(2) > 0
        weight = valid.astype(float)
        if hint is not None:
            m = hint(lo)
            weight = weight * m.astype(float)
        if exclude is not None:
            for (r, c) in exclude:
                weight[max(0, r // DS - 1):r // DS + 2,
                       max(0, c // DS - 1):c // DS + 2] = 0.0
        if weight.sum() == 0:
            raise RuntimeError("hint selected nothing")
        idx = np.flatnonzero(weight.reshape(-1))
        p = weight.reshape(-1)[idx]
        p = p / p.sum()
        out, tries = [], 0
        while len(out) < n and tries < n * 200:
            tries += 1
            k = rng.choice(idx, p=p)
            lr, lc = divmod(int(k), lo.shape[1])
            r = int(lr * DS + rng.integers(0, DS))
            c = int(lc * DS + rng.integers(0, DS))
            if r < ctx or c < ctx or r + ctx >= H or c + ctx >= W:
                continue
            out.append({"i": len(out), "r": r, "c": c, "pn": pn, "ctx": ctx})
    return out


def render_sheet(path, patches, out_png, out_json, patch_m=6.0):
    with rasterio.open(path) as src:
        px = src.transform[0]
        pn = int(round(patch_m / px))
        ctx = int(round(CONTEXT_M / px))
        n = len(patches)
        rows = int(np.ceil(n / GRID))
        sheet = Image.new("RGB", (GRID * TILE_PX, rows * (TILE_PX + PAD)),
                          (18, 18, 18))
        drw = ImageDraw.Draw(sheet)
        kept = []
        for j, m in enumerate(patches):
            r, c = m["r"], m["c"]
            win = rasterio.windows.Window(c - ctx // 2, r - ctx // 2, ctx, ctx)
            a = src.read(window=win, boundless=True, fill_value=0)
            rgb = np.transpose(a, (1, 2, 0))
            if (rgb.sum(2) == 0).mean() > 0.02:
                continue
            im = Image.fromarray(rgb).resize((TILE_PX, TILE_PX),
                                             Image.LANCZOS)
            d = ImageDraw.Draw(im)
            half = int(TILE_PX * (pn / ctx) / 2)
            mid = TILE_PX // 2
            d.rectangle([mid - half, mid - half, mid + half, mid + half],
                        outline=(255, 0, 0), width=3)
            gx = (len(kept) % GRID) * TILE_PX
            gy = (len(kept) // GRID) * (TILE_PX + PAD)
            sheet.paste(im, (gx, gy + PAD))
            drw.text((gx + 6, gy + 6), f"#{len(kept)}", fill=(255, 230, 90))
            # `r`,`c` are written as the TOP-LEFT of the scored patch, which
            # is what `build_vhr_impervious_label.read_patch` expects. The
            # sampled point is the patch CENTRE, kept separately as `rc`,`cc`
            # so the tile can be re-rendered identically.
            m2 = dict(m)
            m2["i"] = len(kept)
            m2["rc"], m2["cc"] = r, c
            m2["r"], m2["c"] = r - pn // 2, c - pn // 2
            kept.append(m2)
        sheet.save(out_png)
        json.dump(kept, open(out_json, "w"))
    print(f"  {out_png}: {len(kept)} tiles ({patch_m} m patch, "
          f"{CONTEXT_M} m context)")
    return kept
