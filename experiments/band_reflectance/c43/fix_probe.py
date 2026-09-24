"""
C43-fix direction probe. Small slice: 3 cities x 1 seed x 3 arms.

Mirrors learning_curve.run_fold EXACTLY (same optimizer, LR, loss, schedule,
augmentation, class-weight formula, determinism) with one addition: each epoch
the logits are scored against BOTH yardsticks, so the arms can be compared on
the original targets and on the corrected ones without training twice.

Arms differ ONLY in osm_generated / osm_generated_water mask pixels.
set_determinism(seed) runs before model init and loader construction, and the
patch count is identical across arms, so init and batch order are identical
too -- the arms are paired fold-for-fold.
"""

import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import sys, json, time, argparse
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import torch, torch.optim as optim
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader

from experiments.band_reflectance.arm_inputs import build_arm_images
from experiments.band_reflectance.fidelity_run import (
    CombinedLoss, compute_per_class_iou, freeze_bn_stats, pick_device, set_determinism)
from experiments.band_reflectance.production_patches_v2 import (
    CATEGORIES, IGNORE_INDEX, NUM_CLASSES)
from experiments.band_reflectance.run_comparison import ArmDataset, ArmSeg
from fix_build import build_variants

BATCH, TAIL, MODE, IN_CHANS = 16, 5, "rgb_stretch", 3


def run_fold(images, patches, train_masks, yardsticks, held_city, device, seed, steps):
    """yardsticks: {name: mask_list}. Returns per-yardstick per-class curves."""
    tr = [i for i, p in enumerate(patches) if p["city"] != held_city]
    va = [i for i, p in enumerate(patches) if p["city"] == held_city]
    n_batches = max(1, len(tr) // BATCH)
    epochs = max(1, int(round(steps / n_batches)))

    counts = Counter(patches[i]["label"] for i in tr)
    arr = np.maximum(np.array([counts.get(c, 1) for c in CATEGORIES], dtype=np.float32), 1)
    w = 1.0 / arr
    w = torch.tensor(w / w.sum() * NUM_CLASSES, dtype=torch.float32).to(device)

    set_determinism(seed)
    train_loader = DataLoader(
        ArmDataset([images[i] for i in tr], [train_masks[i] for i in tr], augment=True),
        batch_size=BATCH, shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(
        ArmDataset([images[i] for i in va], [train_masks[i] for i in va], augment=False),
        batch_size=BATCH, shuffle=False, num_workers=0)
    val_targets = {k: torch.from_numpy(np.stack([v[i] for i in va])).long()
                   for k, v in yardsticks.items()}

    model = ArmSeg(IN_CHANS).to(device)
    criterion = CombinedLoss(class_weights=w, ignore_index=IGNORE_INDEX, dice_weight=0.5,
                             separation_weight=0.0, separation_margin=2.0,
                             class_a_idx=None, class_b_idx=None)
    optimizer = optim.AdamW([{"params": model.encoder.parameters(), "lr": 1e-5},
                             {"params": model.decoder.parameters(), "lr": 3e-4}],
                            weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)

    pcc = {k: [] for k in yardsticks}; mcc = {k: [] for k in yardsticks}; losses = []
    for epoch in range(1, epochs + 1):
        model.train(); freeze_bn_stats(model.encoder); ep = 0.0
        for imgs, msks in train_loader:
            imgs, msks = imgs.to(device), msks.to(device)
            optimizer.zero_grad()
            loss, _, _, _ = criterion(model(imgs), msks)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], max_norm=1.0)
            optimizer.step(); ep += loss.item()
        scheduler.step(); losses.append(ep / len(train_loader))

        model.eval(); lg = []
        with torch.no_grad():
            for imgs, _ in val_loader:
                lg.append(model(imgs.to(device)).cpu())
        lg = torch.cat(lg)
        for k, tgt in val_targets.items():
            pc = compute_per_class_iou(lg, tgt, NUM_CLASSES, IGNORE_INDEX)
            pcc[k].append({CATEGORIES[c]: v for c, v in pc.items()})
            mcc[k].append(float(np.mean([v for v in pc.values() if v is not None])))
    del model

    out = {"city": held_city, "n_train": len(tr), "n_val": len(va),
           "epochs": epochs, "steps": epochs * n_batches,
           "final_train_loss": losses[-1]}
    t = min(TAIL, epochs)
    for k in yardsticks:
        out[f"miou_last5[{k}]"] = float(np.mean(mcc[k][-t:]))
        pcl = {}
        for c in CATEGORIES:
            vals = [h[c] for h in pcc[k][-t:] if h[c] is not None]
            pcl[c] = float(np.mean(vals)) if vals else None
        out[f"per_class_last5[{k}]"] = pcl
        out[f"miou_curve[{k}]"] = mcc[k]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", default="capetown,dhaka,guatemala")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--steps", type=int, default=1600)
    ap.add_argument("--out", default=str(RESULTS / "fix_probe_raw.json"))
    args = ap.parse_args()
    cities = args.cities.split(",")

    device = pick_device()
    base, mB, mC, stat, *_ = build_variants()
    mA = [p["mask"] for p in base]
    images = build_arm_images(base, MODE)
    arms = {"A_baseline": mA, "B_ignore": mB, "C_human": mC}
    yard = {"orig": mA, "corrected": mC}
    print(f"device {device} | {len(base)} patches | seed {args.seed} | steps {args.steps}")
    print(f"changed: {stat['patches_changed']} patches / {stat['px_changed']:,} px\n", flush=True)

    out_path = Path(args.out)
    results = json.loads(out_path.read_text()) if out_path.exists() else []
    done = {(r["arm"], r["city"]) for r in results}
    for city in cities:
        for arm, tm in arms.items():
            if (arm, city) in done:
                print(f"  {city:<11}{arm:<12} cached", flush=True); continue
            t0 = time.time()
            r = run_fold(images, base, tm, yard, city, device, args.seed, args.steps)
            r.update({"arm": arm, "seed": args.seed})
            results.append(r); out_path.write_text(json.dumps(results, indent=2))
            print(f"  {city:<11}{arm:<12} ep={r['epochs']:>3} "
                  f"mIoU[orig]={r['miou_last5[orig]']:.4f} "
                  f"mIoU[corr]={r['miou_last5[corrected]']:.4f} "
                  f"loss={r['final_train_loss']:.4f}  {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
