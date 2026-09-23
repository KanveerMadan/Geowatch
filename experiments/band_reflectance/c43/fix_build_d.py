"""
Arm D: the same human-label correction as arm C, but the 63 corrected patches
are RE-CUT at native 64x64 instead of bbox-cropped and magnified.

Window = 64x64 centred on the bbox centroid, clamped into the tile. The mask is
the segment's real mask_rle read at native resolution inside that window,
painted with the builder's class, then corrected exactly as arm C corrects:
where the builder's class sits on a DIFFERENT non-IGNORE canvas class, the
canvas (human/SAM) class wins.

Nothing else moves. The other 1,351 patches, the patch count, the ordering and
the `label` strings (hence class weights) are identical to arms A and C.
READ-ONLY w.r.t. the repo.
"""

import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import sys, json
import numpy as np
from PIL import Image
from experiments.band_reflectance.production_patches_v2 import (
    build_all_patches, build_tile_label_canvas, CATEGORIES, CAT2IDX, IGNORE_INDEX,
    LOCO_CLEAN_CITIES, _city_file, decode_mask_rle)
from fix_build import aligned_canvas, TARGET_SOURCES

ANN_FILE = {"osm_generated": "osm_generated_annotations.json",
            "osm_generated_water": "osm_generated_annotations_water.json"}


def _ann_index(city):
    """(clipped_box, label, source) -> annotation, matching how the builder clips."""
    tw, th = Image.open(_city_file(city, "tile_0_0.png")).size
    out = {}
    for src, fn in ANN_FILE.items():
        p = _city_file(city, fn)
        if not p.is_file():
            continue
        for a in json.loads(p.read_text())["annotations"]:
            if a.get("skipped", False) or a.get("human_label") not in CAT2IDX:
                continue
            x, y, w, h = a["bbox"]
            box = (max(0, x), max(0, y), min(tw, x + w), min(th, y + h))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            out.setdefault((box, a["human_label"], src), []).append(a)
    return out, tw, th


def build_arm_d():
    """Returns (patches_D, masks_D, changed_idx). patches_D differs from the
    baseline only in `geom` for the 63 corrected patches."""
    base = build_all_patches(verbose=False)
    canv, anns, dims = {}, {}, {}
    for c in LOCO_CLEAN_CITIES:
        canv[c] = build_tile_label_canvas(c, verbose=False)[0]
        anns[c], tw, th = _ann_index(c)
        dims[c] = (tw, th)

    patches_D, masks_D, changed = [], [], []
    unmatched = 0
    for i, p in enumerate(base):
        m = p["mask"]
        if p["source"] not in TARGET_SOURCES:
            patches_D.append(p); masks_D.append(m); continue
        cv = canv.get(p["city"])
        sub = aligned_canvas(p, cv) if cv is not None else None
        own = CAT2IDX[p["label"]]
        if sub is None or not ((m == own) & (sub != IGNORE_INDEX) & (sub != own)).any():
            patches_D.append(p); masks_D.append(m); continue   # untouched by arm C

        key = (tuple(p["geom"]["box"]), p["label"], p["source"])
        cand = anns[p["city"]].get(key)
        if not cand:
            unmatched += 1
            patches_D.append(p); masks_D.append(m); continue
        ann = cand[0]

        tw, th = dims[p["city"]]
        x1, y1, x2, y2 = p["geom"]["box"]
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        x0 = int(np.clip(round(cx) - 32, 0, max(tw - 64, 0)))
        y0 = int(np.clip(round(cy) - 32, 0, max(th - 64, 0)))
        if tw < 64 or th < 64:
            patches_D.append(p); masks_D.append(m); continue

        full = decode_mask_rle(ann["mask_rle"])          # native resolution, no resize
        win = full[y0:y0 + 64, x0:x0 + 64]
        nm = np.full((64, 64), IGNORE_INDEX, dtype=np.uint8)
        nm[win] = own
        cw = cv[y0:y0 + 64, x0:x0 + 64]                  # canvas, native, aligned
        bad = (nm == own) & (cw != IGNORE_INDEX) & (cw != own)
        nm[bad] = cw[bad]

        q = dict(p); q["geom"] = {"kind": "window", "xy": (x0, y0)}
        patches_D.append(q); masks_D.append(nm); changed.append(i)
    if unmatched:
        print(f"  WARNING: {unmatched} corrected patches could not be matched to an annotation")
    return base, patches_D, masks_D, changed


if __name__ == "__main__":
    from fix_build import build_variants
    base, pD, mD, changed = build_arm_d()
    _, mB, mC, stat, *_ = build_variants()
    mA = [p["mask"] for p in base]
    print(f"arm D re-cuts {len(changed)} patches (arm C corrects {stat['patches_changed']})")
    MPP = {c: (lambda a, w: (a["east"] - a["west"]) * 111320 *
               np.cos(np.radians((a["north"] + a["south"]) / 2)) / w)(
           json.loads(_city_file(c, "result.json").read_text())["aoi"],
           Image.open(_city_file(c, "tile_0_0.png")).size[0]) for c in LOCO_CLEAN_CITIES}
    oldg = [np.sqrt((base[i]["geom"]["box"][2] - base[i]["geom"]["box"][0]) *
                    (base[i]["geom"]["box"][3] - base[i]["geom"]["box"][1])) for i in changed]
    print(f"  crop side before: med {np.median(oldg):.0f} px  ->  after: 64 px (native)")
    print(f"  magnification   : med {64/np.median(oldg):.1f}x  ->  1.0x")
    fp_old = [g * MPP[base[i]['city']] for g, i in zip(oldg, changed)]
    fp_new = [64 * MPP[base[i]['city']] for i in changed]
    print(f"  ground span     : med {np.median(fp_old):.0f} m -> {np.median(fp_new):.0f} m "
          f"(inference window range 576-1367 m)")
    print(f"  now inside the inference scale range: {100*np.mean([576<=f<=1367 for f in fp_new]):.0f}% "
          f"(was {100*np.mean([576<=f<=1367 for f in fp_old]):.0f}%)")
    sa = sum(int((m != IGNORE_INDEX).sum()) for m in mA)
    sc = sum(int((m != IGNORE_INDEX).sum()) for m in mC)
    sd = sum(int((m != IGNORE_INDEX).sum()) for m in mD)
    print(f"\n  supervised px   A {sa:,}   C {sc:,}   D {sd:,}  ({sd-sc:+,} vs C)")
    for cl in ["dense_informal_roofing", "dense_vegetation"]:
        k = CAT2IDX[cl]
        print(f"  {cl:<24} A {sum(int((m==k).sum()) for m in mA):>8,}"
              f"   C {sum(int((m==k).sum()) for m in mC):>8,}"
              f"   D {sum(int((m==k).sum()) for m in mD):>8,}")
