"""
Comparison runs: all four arms, one LOCO fold, WITHOUT the separation loss.

The separation loss is out of these runs deliberately and uniformly. It targets
the paved_road / dense_informal_roofing pair at margin 2.0 -- exactly the pair
the 6-band arms are meant to help with -- so leaving it in would push those two
apart by direct supervision and mask whatever the extra bands do or do not
contribute. It stays in the fidelity run, which is a separate run for this
reason: fidelity and clean comparison do not have to trade against each other.

WHAT IS HELD FIXED. The patch set (the 5-builder production rebuild), the fold,
the patch geometry, the label masks, the seed, the augmentation stream, the
optimiser, the schedule, the epoch count, the early-stopping rule, and the
per-fold class weights. The ONLY things that vary are the pixels under each
patch and, for the 6-band arms, the encoder stem.

  A  rgb_stretch     RGB + per-tile stretch     SENTINEL2_RGB_MOCO
  B  rgb_abs         RGB + absolute reflectance SENTINEL2_RGB_MOCO
  C  6band_stretch   6 bands + stretch          SENTINEL2_ALL_MOCO, stem selected
  D  6band_abs       6 bands + absolute         SENTINEL2_ALL_MOCO, stem selected

Label tensors are asserted byte-identical across arms before any training runs.
That check is cheap and it is the one that would have caught a whole class of
attribution error in the previous probe.

WHAT THIS CAN AND CANNOT SAY. One fold, one seed. Per the working rules, a
paired per-fold comparison over 11 folds with a Wilcoxon on the deltas is the
standard; SE on the mean is 0.017, so anything under ~0.035 is invisible
unpaired. This run is a magnitude probe that says whether an 11-fold run is
worth its cost, and nothing stronger.

Usage:
    python experiments/band_reflectance/run_comparison.py [--city accra] [--epochs 30]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms.functional as TF
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.band_reflectance.arm_inputs import MODES, build_arm_images  # noqa: E402
from experiments.band_reflectance.arms import build_encoder  # noqa: E402
from experiments.band_reflectance.fidelity_run import (  # noqa: E402
    CombinedLoss, compute_miou, compute_per_class_iou, freeze_bn_stats,
    pick_device, set_determinism,
)
from experiments.band_reflectance.production_patches_v2 import (  # noqa: E402
    CATEGORIES, IGNORE_INDEX, NUM_CLASSES, build_all_patches,
)
from ingestion.resnet_model import DeepLabDecoder  # noqa: E402

SEED = 1337
ARMS = {
    "A_rgb_stretch":   ("rgb_stretch", 3),
    "B_rgb_abs":       ("rgb_abs", 3),
    "C_6band_stretch": ("6band_stretch", 6),
    "D_6band_abs":     ("6band_abs", 6),
}


class ArmSeg(nn.Module):
    """Same decoder and hook points as GeoWatchResNetSeg, 3- or 6-channel stem."""

    def __init__(self, in_chans: int, num_classes: int = NUM_CLASSES):
        super().__init__()
        self.encoder = build_encoder(in_chans)
        self._features = {}
        self.encoder.layer1.register_forward_hook(self._hook("low"))
        self.encoder.layer3.register_forward_hook(self._hook("high"))
        self.decoder = DeepLabDecoder(low_level_channels=256,
                                      high_level_channels=1024,
                                      num_classes=num_classes)

    def _hook(self, name):
        def fn(module, inp, out):
            self._features[name] = out
        return fn

    def forward(self, x):
        target_size = x.shape[-2:]
        self.encoder.forward_features(x) if hasattr(self.encoder, "forward_features") \
            else self.encoder(x)
        return self.decoder(self._features["low"], self._features["high"], target_size)


class ArmDataset(Dataset):
    """
    Images come pre-extracted as float32 in [0, 1]; no /255 here.

    Augmentation is the notebook's, with one change forced by the 6-band arms:
    brightness/contrast are applied as explicit affine operations rather than
    through torchvision's 3-channel-only helpers, so all four arms get the same
    jitter rather than the 6-band arms silently skipping it.
    """

    def __init__(self, images, masks, augment: bool):
        self.images = images
        self.masks = masks
        self.augment = augment

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        image = torch.from_numpy(self.images[idx]).permute(2, 0, 1).float()
        mask = torch.from_numpy(self.masks[idx]).long()

        if self.augment:
            if random.random() > 0.5:
                image = TF.hflip(image)
                mask = TF.hflip(mask.unsqueeze(0)).squeeze(0)
            if random.random() > 0.5:
                image = TF.vflip(image)
                mask = TF.vflip(mask.unsqueeze(0)).squeeze(0)
            k = random.randint(0, 3)
            if k > 0:
                image = torch.rot90(image, k, dims=[1, 2])
                mask = torch.rot90(mask, k, dims=[0, 1])
            if random.random() > 0.5:
                brightness = random.uniform(0.8, 1.2)
                contrast = random.uniform(0.8, 1.2)
                image = image * brightness
                mean = image.mean(dim=(1, 2), keepdim=True)
                image = (image - mean) * contrast + mean
                image = image.clamp(0, 1)

        return image, mask


def mask_digest(patches: list) -> str:
    h = hashlib.sha256()
    for p in patches:
        h.update(p["mask"].tobytes())
    return h.hexdigest()


def run_arm(name: str, mode: str, in_chans: int, patches: list, val_city: str,
            device: str, epochs: int, ref_digest: str, seed: int,
            images: list, patience: int = 0) -> dict:
    """
    One arm, one seed, FIXED epoch budget.

    patience <= 0 disables early stopping, which is the point: in the first
    comparison the 6-band arms peaked on an epoch-4/5 spike and patience=8
    terminated them at 12-13 with train loss still at 0.41-0.46, while the RGB
    arms ran all 30 down to 0.16-0.18. The stopping rule was a free variable
    correlated with the factor under test.

    `best_miou` is also biased by epoch count -- it is a max over a noisy
    trajectory, so an arm that runs 30 epochs draws 30 samples and an arm that
    runs 12 draws 12. The primary statistic here is therefore the MEAN OF THE
    LAST 5 EPOCHS: a plateau estimate that does not reward extra draws. best
    and final are reported alongside for continuity, not for inference.
    """
    print(f"\n{'=' * 70}\nARM {name}  ({mode}, {in_chans} channels)  seed {seed}\n{'=' * 70}")

    got = mask_digest(patches)
    if got != ref_digest:
        raise AssertionError(
            f"arm {name}: label masks changed (digest {got[:16]} != {ref_digest[:16]}) "
            "-- the arms would not be comparable")
    shapes = {img.shape for img in images}
    if shapes != {(64, 64, in_chans)}:
        raise AssertionError(f"arm {name}: unexpected image shapes {shapes}")

    masks = [p["mask"] for p in patches]
    tr_idx = [i for i, p in enumerate(patches) if p["city"] != val_city]
    va_idx = [i for i, p in enumerate(patches) if p["city"] == val_city]

    fold_counts = Counter(patches[i]["label"] for i in tr_idx)
    counts_arr = np.maximum(
        np.array([fold_counts.get(c, 1) for c in CATEGORIES], dtype=np.float32), 1)
    fold_weights = 1.0 / counts_arr
    fold_weights = fold_weights / fold_weights.sum() * NUM_CLASSES
    fold_class_weights = torch.tensor(fold_weights, dtype=torch.float32).to(device)

    set_determinism(seed)
    train_loader = DataLoader(
        ArmDataset([images[i] for i in tr_idx], [masks[i] for i in tr_idx], augment=True),
        batch_size=16, shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(
        ArmDataset([images[i] for i in va_idx], [masks[i] for i in va_idx], augment=False),
        batch_size=16, shuffle=False, num_workers=0)

    model = ArmSeg(in_chans).to(device)
    criterion = CombinedLoss(
        class_weights=fold_class_weights, ignore_index=IGNORE_INDEX,
        dice_weight=0.5,
        separation_weight=0.0,          # OUT, uniformly, for every arm
        separation_margin=2.0, class_a_idx=None, class_b_idx=None,
    )
    optimizer = optim.AdamW([
        {"params": model.encoder.parameters(), "lr": 1e-5},
        {"params": model.decoder.parameters(), "lr": 3e-4},
    ], weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)

    history = {"train_loss": [], "val_miou": [], "per_class": []}
    best_miou, best_epoch = 0.0, 0

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        model.train()
        freeze_bn_stats(model.encoder)
        ep_loss = 0.0
        for imgs, msks in train_loader:
            imgs, msks = imgs.to(device), msks.to(device)
            optimizer.zero_grad()
            loss, _, _, _ = criterion(model(imgs), msks)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], max_norm=1.0)
            optimizer.step()
            ep_loss += loss.item()
        scheduler.step()
        n = len(train_loader)
        history["train_loss"].append(ep_loss / n)

        model.eval()
        lg, mk = [], []
        with torch.no_grad():
            for imgs, msks in val_loader:
                lg.append(model(imgs.to(device)).cpu())
                mk.append(msks.cpu())
        logits_cat, masks_cat = torch.cat(lg), torch.cat(mk)
        pc = compute_per_class_iou(logits_cat, masks_cat, NUM_CLASSES, IGNORE_INDEX)
        val_miou = float(np.mean([v for v in pc.values() if v is not None]))
        history["val_miou"].append(val_miou)
        history["per_class"].append({CATEGORIES[c]: v for c, v in pc.items()})

        if val_miou > best_miou:
            best_miou, best_epoch = val_miou, epoch

        print(f"  epoch {epoch:3d}/{epochs} | loss={ep_loss / n:.4f} | "
              f"val_mIoU={val_miou:.4f}{' best' if epoch == best_epoch else ''} "
              f"| {time.time() - t0:.1f}s", flush=True)

        if patience > 0 and epoch - best_epoch >= patience:
            print(f"  Early stop at epoch {epoch}")
            break

    tail = min(5, len(history["val_miou"]))
    plateau_miou = float(np.mean(history["val_miou"][-tail:]))
    plateau_per_class = {}
    for cls in CATEGORIES:
        vals = [h[cls] for h in history["per_class"][-tail:] if h[cls] is not None]
        plateau_per_class[cls] = float(np.mean(vals)) if vals else None

    del model
    return {"arm": name, "mode": mode, "in_chans": in_chans, "seed": seed,
            "epochs_run": len(history["val_miou"]), "tail": tail,
            "plateau_miou": plateau_miou, "plateau_per_class": plateau_per_class,
            "best_miou": best_miou, "best_epoch": best_epoch,
            "final_miou": history["val_miou"][-1],
            "final_train_loss": history["train_loss"][-1],
            "n_train": len(tr_idx), "n_val": len(va_idx),
            "history": history}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="accra")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--seeds", default="1337,7,2024")
    ap.add_argument("--patience", type=int, default=0,
                    help="0 disables early stopping (the fixed-budget protocol)")
    ap.add_argument("--tag", default="fixed")
    args = ap.parse_args()

    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    device = pick_device()
    print("=" * 70)
    print("COMPARISON -- four arms, one fold, NO separation loss, FIXED budget")
    print(f"device {device} | held-out {args.city} | epochs {args.epochs} "
          f"(patience {args.patience or 'disabled'}) | seeds {seeds}")
    print("=" * 70)

    set_determinism(seeds[0])
    patches = build_all_patches(verbose=False)
    print(f"rebuilt {len(patches)} patches")

    ref_digest = mask_digest(patches)
    print(f"reference label digest {ref_digest[:16]} over {len(patches)} masks")

    # Arm images depend only on the mode, so build each once and reuse across
    # seeds. This also guarantees every seed of an arm sees identical pixels.
    print("building arm images once per mode ...", flush=True)
    arm_images = {}
    for name, (mode, ch) in ARMS.items():
        arm_images[name] = build_arm_images(patches, mode)
        print(f"  {name}: {len(arm_images[name])} x {arm_images[name][0].shape}", flush=True)

    runs = []
    for seed in seeds:
        for name, (mode, ch) in ARMS.items():
            runs.append(run_arm(name, mode, ch, patches, args.city, device,
                                args.epochs, ref_digest, seed, arm_images[name],
                                patience=args.patience))

    # --- aggregate -----------------------------------------------------------
    by_arm = {name: [r for r in runs if r["arm"] == name] for name in ARMS}

    def agg(name, key):
        return np.array([r[key] for r in by_arm[name]], dtype=float)

    print("\n" + "=" * 70)
    print(f"RESULTS -- held-out {args.city}, {args.epochs} epochs fixed, "
          f"{len(seeds)} seeds, no separation loss")
    print("=" * 70)
    print(f"  {'arm':<18}{'plateau (last5)':>18}{'best':>16}{'final loss':>13}")
    for name in ARMS:
        pl, bt = agg(name, "plateau_miou"), agg(name, "best_miou")
        fl = agg(name, "final_train_loss")
        print(f"  {name:<18}{pl.mean():>11.4f} +/-{pl.std(ddof=1) if len(pl) > 1 else 0:.4f}"
              f"{bt.mean():>11.4f} +/-{bt.std(ddof=1) if len(bt) > 1 else 0:.4f}"
              f"{fl.mean():>13.4f}")

    print("\n  Per-seed plateau mIoU:")
    print(f"    {'arm':<18}" + "".join(f"{s:>10}" for s in seeds))
    for name in ARMS:
        row = {r["seed"]: r["plateau_miou"] for r in by_arm[name]}
        print(f"    {name:<18}" + "".join(f"{row.get(s, float('nan')):>10.4f}" for s in seeds))

    print("\n  Factor effects on the plateau statistic, paired within seed:")
    for label, a, b in (("6 bands at absolute reflectance  D - B", "D_6band_abs", "B_rgb_abs"),
                        ("6 bands under the stretch        C - A", "C_6band_stretch", "A_rgb_stretch"),
                        ("absolute vs stretch, RGB         B - A", "B_rgb_abs", "A_rgb_stretch"),
                        ("absolute vs stretch, 6 band      D - C", "D_6band_abs", "C_6band_stretch")):
        da = {r["seed"]: r["plateau_miou"] for r in by_arm[a]}
        db = {r["seed"]: r["plateau_miou"] for r in by_arm[b]}
        d = np.array([da[s] - db[s] for s in seeds if s in da and s in db])
        print(f"    {label} = {d.mean():+.4f} "
              f"(per seed: {', '.join(f'{x:+.4f}' for x in d)})")

    print("\n  Per-class plateau IoU, mean over seeds (sd in brackets):")
    print(f"    {'class':<26}" + "".join(f"{n.split('_')[0]:>18}" for n in ARMS))
    for cls in CATEGORIES:
        cells = []
        for name in ARMS:
            v = np.array([r["plateau_per_class"][cls] for r in by_arm[name]
                          if r["plateau_per_class"][cls] is not None], dtype=float)
            cells.append(f"{v.mean():>11.4f}[{v.std(ddof=1) if len(v) > 1 else 0:.3f}]"
                         if len(v) else f"{'n/a':>18}")
        print(f"    {cls:<26}" + "".join(cells))

    print("\n  One fold on a city that is not representative. Seeds bound the")
    print("  noise, not the city effect. The 11-fold paired run is still the")
    print("  standard and is still unrun.")
    print("=" * 70)

    out = Path(__file__).resolve().parent / "results" / f"comparison_{args.city}_{args.tag}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "val_city": args.city, "device": device, "seeds": seeds,
        "epochs": args.epochs, "patience": args.patience,
        "separation_loss": False, "n_all_patches": len(patches),
        "primary_statistic": "mean val mIoU over the last 5 epochs",
        "runs": runs,
    }, indent=2))
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
