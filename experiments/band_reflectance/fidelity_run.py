"""
Fidelity run: Arm A, WITH the separation loss, one LOCO fold.

This run exists only to prove the reconstruction. It is not a comparison and
produces no claim about bands or reflectance.

WHAT IT REPRODUCES. Arm A is the production configuration -- RGB, per-tile
percentile stretch -- and the rebuilt patches come straight off
`tile_0_0.png`, which is already the stretched 8-bit product. So "Arm A on
production patches" is not an approximation of the notebook's pipeline; it is
that pipeline, re-executed from ported code. Everything below is cell 35's
`run_loco_fold` with its own hyperparameters:

    30 epochs, patience 8, batch 16
    AdamW, encoder lr 1e-5 / decoder lr 3e-4, weight_decay 1e-4
    CosineAnnealingLR(T_max=30, eta_min=1e-6)
    CombinedLoss: 0.5*CE(fold weights) + 0.5*Dice + 0.25*separation(margin 2.0)
    grad-norm clip 1.0, BN stats frozen in the encoder
    per-fold class weights recomputed on that fold's train split

The separation loss is IN here and OUT of the comparison runs, deliberately: it
targets the exact paved_road/dense_informal_roofing pair the 6-band arms test,
so leaving it in would mask the effect being measured. Separating the two runs
means fidelity and clean comparison do not trade against each other.

THE BAR. The checkpoint records loco_mean_miou 0.313, loco_std_miou 0.0564 over
11 folds. Per-fold values were not preserved -- Colab outputs were cleared
before download -- so a single fold can only be checked against the mean plus
that spread. Landing inside 0.313 +/- 0.0564 is consistent with the
reconstruction; it is not proof of it, and one fold is not a LOCO result.

The number this has to beat to mean anything at all: the broken probe's Arm A
scored 0.0221 on Accra with six of seven classes at exactly zero.

Usage:
    python experiments/band_reflectance/fidelity_run.py [--city accra] [--epochs 30]
"""
from __future__ import annotations

import argparse
import copy
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
import torch.nn.functional as F
import torchvision.transforms.functional as TF
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.band_reflectance.production_patches_v2 import (  # noqa: E402
    CATEGORIES, IGNORE_INDEX, NUM_CLASSES, build_all_patches,
)
from ingestion.resnet_model import GeoWatchResNetSeg  # noqa: E402

CKPT_LOCO_MEAN = 0.313
CKPT_LOCO_STD = 0.0564
BROKEN_PROBE_ARM_A = 0.0221
SEED = 1337


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def set_determinism(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# --- cell 21 / 24: the dataset actually used ---------------------------------

class GeoWatchDatasetResNet(Dataset):
    """
    Cell 24's class: /255.0 only, no ImageNet mean/std. Cell 21's
    GeoWatchDataset applies mean/std and is the superseded SegFormer-era
    version; cell 39 builds both its loaders from THIS one.
    """

    def __init__(self, patches: list, augment: bool = True):
        self.patches = patches
        self.augment = augment

    def __len__(self) -> int:
        return len(self.patches)

    def __getitem__(self, idx):
        item = self.patches[idx]
        image = torch.from_numpy(item["image"]).permute(2, 0, 1).float() / 255.0
        mask = torch.from_numpy(item["mask"]).long()

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
                image = TF.adjust_brightness(image, random.uniform(0.8, 1.2))
                image = TF.adjust_contrast(image, random.uniform(0.8, 1.2))
                image = image.clamp(0, 1)

        return image, mask


# --- cell 26: the loss -------------------------------------------------------

class DiceLoss(nn.Module):
    def __init__(self, num_classes: int, ignore_index: int = 255, smooth: float = 1.0):
        super().__init__()
        self.num_classes = num_classes
        self.ignore_index = ignore_index
        self.smooth = smooth

    def forward(self, logits, targets):
        probs = F.softmax(logits, dim=1)
        _, C, _, _ = probs.shape
        valid_mask = targets != self.ignore_index
        targets_clamped = targets.clone()
        targets_clamped[~valid_mask] = 0
        one_hot = F.one_hot(targets_clamped, num_classes=C).permute(0, 3, 1, 2).float()
        m = valid_mask.unsqueeze(1).float()
        probs = probs * m
        one_hot = one_hot * m

        dice_per_class = []
        for c in range(C):
            p = probs[:, c].reshape(-1)
            t = one_hot[:, c].reshape(-1)
            inter = (p * t).sum()
            dice = (2.0 * inter + self.smooth) / (p.sum() + t.sum() + self.smooth)
            dice_per_class.append(1.0 - dice)
        return torch.stack(dice_per_class).mean()


class CombinedLoss(nn.Module):
    """0.5*CE(weighted) + 0.5*Dice + separation_weight*separation."""

    def __init__(self, class_weights, ignore_index=255, dice_weight=0.5,
                 separation_weight=0.25, separation_margin=2.0,
                 class_a_idx=None, class_b_idx=None):
        super().__init__()
        self.ce = nn.CrossEntropyLoss(weight=class_weights, ignore_index=ignore_index)
        self.dice = DiceLoss(num_classes=len(class_weights), ignore_index=ignore_index)
        self.dice_weight = dice_weight
        self.ignore_index = ignore_index
        self.separation_weight = separation_weight
        self.separation_margin = separation_margin
        self.class_a_idx = class_a_idx
        self.class_b_idx = class_b_idx

    def separation_loss(self, logits, targets):
        if self.class_a_idx is None or self.class_b_idx is None:
            return torch.tensor(0.0, device=logits.device)
        valid = targets != self.ignore_index
        logit_a = logits[:, self.class_a_idx, :, :]
        logit_b = logits[:, self.class_b_idx, :, :]
        is_a = valid & (targets == self.class_a_idx)
        is_b = valid & (targets == self.class_b_idx)

        loss = torch.tensor(0.0, device=logits.device)
        n_terms = 0
        if is_a.any():
            loss = loss + F.relu(self.separation_margin - (logit_a[is_a] - logit_b[is_a])).mean()
            n_terms += 1
        if is_b.any():
            loss = loss + F.relu(self.separation_margin - (logit_b[is_b] - logit_a[is_b])).mean()
            n_terms += 1
        return loss / n_terms if n_terms else torch.tensor(0.0, device=logits.device)

    def forward(self, logits, targets):
        ce_loss = self.ce(logits, targets)
        dice_loss = self.dice(logits, targets)
        sep_loss = self.separation_loss(logits, targets)
        total = ((1 - self.dice_weight) * ce_loss
                 + self.dice_weight * dice_loss
                 + self.separation_weight * sep_loss)
        return total, ce_loss, dice_loss, sep_loss


# --- cell 32: metrics --------------------------------------------------------

def freeze_bn_stats(module: nn.Module) -> None:
    for m in module.modules():
        if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)):
            m.eval()


def compute_per_class_iou(logits, targets, num_classes, ignore_index=255) -> dict:
    preds = logits.argmax(dim=1)
    valid = targets != ignore_index
    ious = {}
    for c in range(num_classes):
        pred_c = (preds == c) & valid
        true_c = (targets == c) & valid
        inter = (pred_c & true_c).sum().item()
        union = (pred_c | true_c).sum().item()
        ious[c] = (inter / union) if union > 0 else None
    return ious


def compute_miou(logits, targets, num_classes, ignore_index=255) -> float:
    ious = [v for v in compute_per_class_iou(logits, targets, num_classes, ignore_index).values()
            if v is not None]
    return float(np.mean(ious)) if ious else 0.0


# --- cell 35: the fold -------------------------------------------------------

def run_loco_fold(val_city: str, all_patches: list, device: str, num_epochs: int = 30,
                  patience: int = 8, batch_size: int = 16,
                  lr_encoder: float = 1e-5, lr_decoder: float = 3e-4) -> dict:
    train_patches = [p for p in all_patches if p["city"] != val_city]
    val_patches = [p for p in all_patches if p["city"] == val_city]
    if not val_patches:
        raise SystemExit(f"no patches for held-out city {val_city}")

    train_cities = sorted(set(p["city"] for p in train_patches))
    print(f"\n{'=' * 64}")
    print(f"LOCO FOLD: held-out = {val_city}")
    print(f"  Train: {len(train_patches)} patches from {len(train_cities)} cities")
    print(f"  Val:   {len(val_patches)} patches ({val_city})")

    fold_counts = Counter(p["label"] for p in train_patches)
    counts_arr = np.maximum(
        np.array([fold_counts.get(c, 1) for c in CATEGORIES], dtype=np.float32), 1)
    fold_weights = 1.0 / counts_arr
    fold_weights = fold_weights / fold_weights.sum() * NUM_CLASSES
    fold_class_weights = torch.tensor(fold_weights, dtype=torch.float32).to(device)
    print("  fold class weights: "
          + ", ".join(f"{c}={w:.4f}" for c, w in zip(CATEGORIES, fold_weights)))

    train_loader = DataLoader(GeoWatchDatasetResNet(train_patches, augment=True),
                              batch_size=batch_size, shuffle=True, num_workers=0,
                              drop_last=True)
    val_loader = DataLoader(GeoWatchDatasetResNet(val_patches, augment=False),
                            batch_size=batch_size, shuffle=False, num_workers=0)

    model = GeoWatchResNetSeg(num_classes=NUM_CLASSES, freeze_encoder=False).to(device)
    criterion = CombinedLoss(
        class_weights=fold_class_weights, ignore_index=IGNORE_INDEX,
        dice_weight=0.5, separation_weight=0.25, separation_margin=2.0,
        class_a_idx=CATEGORIES.index("paved_road"),
        class_b_idx=CATEGORIES.index("dense_informal_roofing"),
    )
    optimizer = optim.AdamW([
        {"params": model.encoder.parameters(), "lr": lr_encoder},
        {"params": model.decoder.parameters(), "lr": lr_decoder},
    ], weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=num_epochs, eta_min=1e-6)

    best_miou, best_epoch, best_state = 0.0, 0, None
    epochs_since_improve = 0
    history = {"train_loss": [], "val_miou": [], "ce": [], "dice": [], "sep": []}

    for epoch in range(1, num_epochs + 1):
        t0 = time.time()
        model.train()
        freeze_bn_stats(model.encoder)
        ep_loss = ep_ce = ep_dice = ep_sep = 0.0
        for images, masks in train_loader:
            images, masks = images.to(device), masks.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss, ce, dice, sep = criterion(logits, masks)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], max_norm=1.0)
            optimizer.step()
            ep_loss += loss.item()
            ep_ce += ce.item()
            ep_dice += dice.item()
            ep_sep += float(sep)
        scheduler.step()
        n = len(train_loader)
        history["train_loss"].append(ep_loss / n)
        history["ce"].append(ep_ce / n)
        history["dice"].append(ep_dice / n)
        history["sep"].append(ep_sep / n)

        model.eval()
        logits_all, masks_all = [], []
        with torch.no_grad():
            for images, masks in val_loader:
                logits_all.append(model(images.to(device)).cpu())
                masks_all.append(masks.cpu())
        val_miou = compute_miou(torch.cat(logits_all), torch.cat(masks_all),
                                NUM_CLASSES, IGNORE_INDEX)
        history["val_miou"].append(val_miou)

        if val_miou > best_miou:
            best_miou, best_epoch = val_miou, epoch
            best_state = copy.deepcopy(model.state_dict())
            epochs_since_improve = 0
        else:
            epochs_since_improve += 1

        print(f"  epoch {epoch:3d}/{num_epochs} | loss={ep_loss / n:.4f} "
              f"(ce={ep_ce / n:.4f} dice={ep_dice / n:.4f} sep={ep_sep / n:.4f}) | "
              f"val_mIoU={val_miou:.4f}{' best' if epoch == best_epoch else ''} "
              f"| {time.time() - t0:.1f}s")

        if epochs_since_improve >= patience:
            print(f"  Early stop at epoch {epoch} (no improvement for {patience} epochs)")
            break

    model.load_state_dict(best_state)
    model.eval()
    logits_all, masks_all = [], []
    with torch.no_grad():
        for images, masks in val_loader:
            logits_all.append(model(images.to(device)).cpu())
            masks_all.append(masks)
    logits_cat, masks_cat = torch.cat(logits_all), torch.cat(masks_all)

    per_class_iou = {CATEGORIES[c]: v for c, v in
                     compute_per_class_iou(logits_cat, masks_cat, NUM_CLASSES,
                                           IGNORE_INDEX).items()}
    probs = torch.softmax(logits_cat, dim=1)
    max_probs, _ = probs.max(dim=1)
    valid_mask = masks_cat != IGNORE_INDEX
    unconfident_pct = float((max_probs[valid_mask] < 0.5).float().mean().item() * 100)

    val_px = Counter()
    tgt = masks_cat[valid_mask].numpy()
    for c in range(NUM_CLASSES):
        val_px[CATEGORIES[c]] = int((tgt == c).sum())

    return {
        "val_city": val_city,
        "best_miou": best_miou,
        "best_epoch": best_epoch,
        "n_train": len(train_patches),
        "n_val": len(val_patches),
        "train_cities": train_cities,
        "per_class_iou": per_class_iou,
        "val_pixels_per_class": dict(val_px),
        "unconfident_pct_proxy": unconfident_pct,
        "fold_class_weights": dict(zip(CATEGORIES, fold_weights.tolist())),
        "history": history,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="accra",
                    help="held-out city (accra keeps continuity with the broken probe)")
    ap.add_argument("--epochs", type=int, default=30)
    args = ap.parse_args()

    device = pick_device()
    print("=" * 64)
    print("FIDELITY RUN -- Arm A + separation loss, one fold")
    print(f"device {device} | seed {SEED} | held-out {args.city}")
    print("=" * 64)

    set_determinism()
    patches = build_all_patches(verbose=False)
    print(f"rebuilt {len(patches)} patches "
          f"({Counter(p['source'] for p in patches)})")

    set_determinism()
    res = run_loco_fold(args.city, patches, device, num_epochs=args.epochs)

    lo, hi = CKPT_LOCO_MEAN - CKPT_LOCO_STD, CKPT_LOCO_MEAN + CKPT_LOCO_STD
    inside = lo <= res["best_miou"] <= hi

    print("\n" + "=" * 64)
    print(f"  fold mIoU              {res['best_miou']:.4f} @ epoch {res['best_epoch']}")
    print(f"  checkpoint LOCO        {CKPT_LOCO_MEAN:.4f} +/- {CKPT_LOCO_STD:.4f} "
          f"[{lo:.4f}, {hi:.4f}] over 11 folds")
    print(f"  broken probe's Arm A   {BROKEN_PROBE_ARM_A:.4f} (6 of 7 classes at zero)")
    print("\n  per-class IoU:")
    for k, v in res["per_class_iou"].items():
        px = res["val_pixels_per_class"].get(k, 0)
        print(f"    {k:<26} {'n/a (absent)' if v is None else f'{v:.4f}'}"
              f"   val px {px:>8}")
    nonzero = sum(1 for v in res["per_class_iou"].values() if v not in (None, 0.0))
    present = sum(1 for v in res["per_class_iou"].values() if v is not None)
    print(f"\n  classes with non-zero IoU: {nonzero} of {present} present")
    print(f"  {'INSIDE' if inside else 'OUTSIDE'} the checkpoint's +/-1 sd band")
    print("=" * 64)
    print("  One fold, one seed. Not a LOCO result and not a band/reflectance claim.")

    out = Path(__file__).resolve().parent / "results" / f"fidelity_{args.city}.json"
    out.parent.mkdir(exist_ok=True)
    payload = dict(res)
    payload.update({
        "arm": "A_rgb_stretch",
        "separation_loss": True,
        "separation_weight": 0.25,
        "device": device,
        "seed": SEED,
        "n_all_patches": len(patches),
        "ckpt_loco_mean": CKPT_LOCO_MEAN,
        "ckpt_loco_std": CKPT_LOCO_STD,
        "inside_1sd": bool(inside),
    })
    out.write_text(json.dumps(payload, indent=2))
    print(f"  wrote {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
