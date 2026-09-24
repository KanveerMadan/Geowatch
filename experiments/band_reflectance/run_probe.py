"""
One-fold, four-arm probe: does the classifier gain from 6 bands, from absolute
reflectance, or both? (C41)

Feasibility and MAGNITUDE probe, deliberately one fold -- not a LOCO result.
Every arm sees identical folds, identical patch coordinates, identical seeds and
identical hyperparameters; only the input pipeline and encoder differ, so any
difference attributes to the factor under test.

Usage:  python experiments/band_reflectance/run_probe.py [--folds N] [--epochs N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

sys.path.insert(0, ".")
from experiments.band_reflectance.arms import ALL_MOCO_INDICES, build_encoder, build_input
from experiments.harness.loco import (
    ArmResult, FoldResult, LOCO_CITIES, confusion, folds, iou_from_confusion,
    miou, per_city_table, per_class_table, set_determinism,
)
from ingestion.resnet_model import DeepLabDecoder
from recalibrate_caat import build_label_canvas, find_annotated_run_dir

PATCH = 64
IGNORE = 255
LR = 3e-4                # production hyperparameters, unchanged
BATCH = 16
MAX_PATCHES_PER_FOLD = 1200   # ~ the checkpoint's recorded n_train_patches=1272

CATEGORIES = ["dense_informal_roofing", "sparse_informal_roofing", "paved_road",
              "standing_water", "vegetation_clearing", "active_construction",
              "dense_vegetation"]

ARMS = {
    "A_rgb_stretch":   ("rgb_stretch",   3),
    "B_rgb_abs":       ("rgb_abs",       3),
    "C_6band_stretch": ("6band_stretch", 6),
    "D_6band_abs":     ("6band_abs",     6),
}


class ProbeSeg(nn.Module):
    """GeoWatchResNetSeg's shape, with a configurable input channel count."""

    def __init__(self, in_chans: int, num_classes: int = 7):
        super().__init__()
        self.encoder = build_encoder(in_chans)
        self._f = {}
        self.encoder.layer1.register_forward_hook(self._hook("low"))
        self.encoder.layer3.register_forward_hook(self._hook("high"))
        self.decoder = DeepLabDecoder(low_level_channels=256,
                                      high_level_channels=1024,
                                      num_classes=num_classes)

    def _hook(self, name):
        def fn(_m, _i, o):
            self._f[name] = o
        return fn

    def forward(self, x):
        size = x.shape[-2:]
        self.encoder.forward_features(x) if hasattr(self.encoder, "forward_features") \
            else self.encoder(x)
        return self.decoder(self._f["low"], self._f["high"], size)


def city_data(city, mode):
    """(C,H,W) input and (H,W) label canvas, aligned."""
    rd = find_annotated_run_dir(city)
    with Image.open(os.path.join(rd, "tiles", "tile_0_0.png")) as im:
        w, h = im.size
    canvas = build_label_canvas(rd, (h, w), CATEGORIES)
    return build_input(city, mode), canvas


def sample_coords(canvas, rng, per_city):
    """Patch top-lefts whose window contains labelled pixels."""
    h, w = canvas.shape
    if h < PATCH or w < PATCH:
        return []
    ys, xs = np.where(canvas != IGNORE)
    if len(ys) == 0:
        return []
    picks = rng.choice(len(ys), min(per_city * 4, len(ys)), replace=False)
    out = []
    for p in picks:
        y = int(np.clip(ys[p] - PATCH // 2, 0, h - PATCH))
        x = int(np.clip(xs[p] - PATCH // 2, 0, w - PATCH))
        if (canvas[y:y + PATCH, x:x + PATCH] != IGNORE).sum() >= 32:
            out.append((y, x))
        if len(out) >= per_city:
            break
    return out


def train_and_eval(mode, in_chans, held, train_cities, device, epochs, seed):
    rng = np.random.default_rng(seed)
    per_city = max(1, MAX_PATCHES_PER_FOLD // len(train_cities))

    X, Y = [], []
    for c in train_cities:
        img, canvas = city_data(c, mode)
        for (y, x) in sample_coords(canvas, rng, per_city):
            X.append(img[:, y:y + PATCH, x:x + PATCH])
            Y.append(canvas[y:y + PATCH, x:x + PATCH])
    X = torch.from_numpy(np.stack(X)).float()
    Y = torch.from_numpy(np.stack(Y)).long()

    model = ProbeSeg(in_chans).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    lossf = nn.CrossEntropyLoss(ignore_index=IGNORE)

    model.train()
    n = len(X)
    for _ in range(epochs):
        order = torch.randperm(n)
        for i in range(0, n, BATCH):
            b = order[i:i + BATCH]
            xb, yb = X[b].to(device), Y[b].to(device)
            opt.zero_grad()
            lossf(model(xb), yb).backward()
            opt.step()

    # Evaluate on the held-out city, sliding window at the production stride.
    model.eval()
    img, canvas = city_data(held, mode)
    C, H, W = img.shape
    acc = np.zeros((len(CATEGORIES), H, W), dtype=np.float32)
    cnt = np.zeros((H, W), dtype=np.float32)
    stride = PATCH // 2
    t = torch.from_numpy(img).float().unsqueeze(0)
    with torch.no_grad():
        for y in range(0, max(H - PATCH, 0) + 1, stride):
            for x in range(0, max(W - PATCH, 0) + 1, stride):
                patch = t[:, :, y:y + PATCH, x:x + PATCH].to(device)
                if patch.shape[-2:] != (PATCH, PATCH):
                    continue
                p = F.softmax(model(patch), dim=1)[0].cpu().numpy()
                acc[:, y:y + PATCH, x:x + PATCH] += p
                cnt[y:y + PATCH, x:x + PATCH] += 1
    cnt[cnt == 0] = 1
    pred = (acc / cnt).argmax(0)
    return pred, canvas, len(X)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=1)
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--out", default="experiments/band_reflectance/results")
    args = ap.parse_args()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device={device}  folds={args.folds}  epochs={args.epochs}  seed={args.seed}")
    print(f"6-band channel selection (verified): {ALL_MOCO_INDICES}\n")

    results = {}
    for arm_name, (mode, in_chans) in ARMS.items():
        arm = ArmResult(arm_name, args.seed, list(CATEGORIES),
                        meta={"mode": mode, "in_chans": in_chans,
                              "epochs": args.epochs, "device": device,
                              "channel_indices": ALL_MOCO_INDICES if in_chans == 6 else None})
        for i, held, train in folds():
            if i >= args.folds:
                break
            set_determinism(args.seed + i)
            t0 = time.time()
            pred, target, n_patches = train_and_eval(
                mode, in_chans, held, train, device, args.epochs, args.seed + i)
            cm = confusion(pred, target, len(CATEGORIES))
            iou = iou_from_confusion(cm)
            arm.folds.append(FoldResult(
                fold=i, city=held, miou=miou(iou),
                per_class_iou={c: (None if np.isnan(v) else float(v))
                               for c, v in zip(CATEGORIES, iou)},
                n_labeled_px=int((target != IGNORE).sum()),
                seconds=time.time() - t0, n_train_patches=n_patches))
            print(f"  {arm_name:<16} fold {i} ({held:<10}) "
                  f"mIoU={arm.folds[-1].miou:.4f}  "
                  f"{arm.folds[-1].seconds/60:.1f} min  patches={n_patches}")
        arm.meta["complete"] = args.folds >= len(LOCO_CITIES)
        arm.meta["n_folds_run"] = len(arm.folds)
        arm.save(os.path.join(args.out, f"{arm_name}.json"))
        results[arm_name] = arm

    arms = list(results.values())
    print("\n" + "=" * 74)
    print("PER-CITY mIoU" + ("" if arms[0].meta["complete"]
                             else "   *** PARTIAL — not a LOCO result ***"))
    print(per_city_table(arms))
    print("\nPER-CLASS IoU (mean over folds run)")
    print(per_class_table(arms))


if __name__ == "__main__":
    main()
