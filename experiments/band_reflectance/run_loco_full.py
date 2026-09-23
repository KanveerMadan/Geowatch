"""
The 11-fold paired LOCO run: four arms, per-class paired deltas.

THE QUESTION THIS ANSWERS IS PER-CLASS, NOT MEAN. The one-fold Accra run had
the 7-class mean move by −0.0033 between D and B while `standing_water` moved
+0.27 and `vegetation_clearing` −0.51. The mean was the least informative
number in the table. What matters to the project is whether NIR and SWIR help
**water and impervious specifically, consistently, across cities** — those are
what the flood model consumes — and that is a per-class question that a 7-class
unweighted mIoU is structurally unable to answer.

SELECTION RULE: FINAL EPOCH AT A FIXED BUDGET. No early stopping, no
best-epoch selection.

This is not only about the stopping asymmetry. **In LOCO the held-out city is
both the validation set and the test set.** Selecting the best epoch by mIoU on
the held-out city is selecting on the test set, which is optimistically biased
— and biased more for arms or folds that run more epochs, because a max over a
noisy trajectory grows with the number of draws. The training notebook does
exactly this (`run_loco_fold` tracks `best_miou` on the held-out fold and early
stops on it), so **0.313 is itself a max-over-epochs-on-test number.** That is
worth knowing when comparing against it, and it is not a reason to repeat it.

So every fold here trains a fixed number of epochs and reports the final one.
A second, noise-reduced read is computed alongside — the softmax averaged over
the last N epochs, then argmaxed — which involves no selection either, only
averaging. If the two disagree, that is reported rather than resolved silently.

COST. 4 arms x 11 folds x EPOCHS. At ~16 s/epoch and 40 epochs that is roughly
8 hours. `--limit-folds` runs a subset; the harness marks any partial result as
incomplete so it can never be mistaken for a LOCO number.

Usage:
    python experiments/band_reflectance/run_loco_full.py [--epochs 40] [--limit-folds N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.optim as optim
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.band_reflectance.arm_inputs import build_arm_images  # noqa: E402
from experiments.band_reflectance.fidelity_run import (  # noqa: E402
    CombinedLoss, freeze_bn_stats, pick_device, set_determinism,
)
from experiments.band_reflectance.production_patches_v2 import (  # noqa: E402
    CATEGORIES, IGNORE_INDEX, NUM_CLASSES, LOCO_CLEAN_CITIES, build_all_patches,
)
from experiments.band_reflectance.run_comparison import (  # noqa: E402
    ARMS, ArmDataset, ArmSeg, mask_digest,
)
from experiments.harness.loco import (  # noqa: E402
    ArmResult, FoldResult, confusion, format_comparison,
    format_per_class_comparison, iou_from_confusion, miou as _miou,
    paired_compare, paired_compare_per_class, per_city_table, per_class_table,
    run_arm,
)

SEED = 1337
TAIL = 5            # epochs averaged for the secondary read

PAIRS = [
    ("B_rgb_abs", "D_6band_abs", "6 bands at absolute reflectance"),
    ("A_rgb_stretch", "C_6band_stretch", "6 bands under the stretch"),
    ("A_rgb_stretch", "B_rgb_abs", "absolute vs stretch, RGB"),
    ("C_6band_stretch", "D_6band_abs", "absolute vs stretch, 6 band"),
]


def train_one_fold(images, patches, held_city, in_chans, device, epochs):
    """Train a fixed budget; return final-epoch and last-TAIL-averaged predictions."""
    masks = [p["mask"] for p in patches]
    tr = [i for i, p in enumerate(patches) if p["city"] != held_city]
    va = [i for i, p in enumerate(patches) if p["city"] == held_city]

    counts = Counter(patches[i]["label"] for i in tr)
    arr = np.maximum(np.array([counts.get(c, 1) for c in CATEGORIES], dtype=np.float32), 1)
    w = 1.0 / arr
    w = torch.tensor(w / w.sum() * NUM_CLASSES, dtype=torch.float32).to(device)

    train_loader = DataLoader(
        ArmDataset([images[i] for i in tr], [masks[i] for i in tr], augment=True),
        batch_size=16, shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(
        ArmDataset([images[i] for i in va], [masks[i] for i in va], augment=False),
        batch_size=16, shuffle=False, num_workers=0)

    model = ArmSeg(in_chans).to(device)
    criterion = CombinedLoss(class_weights=w, ignore_index=IGNORE_INDEX,
                             dice_weight=0.5, separation_weight=0.0,
                             separation_margin=2.0, class_a_idx=None, class_b_idx=None)
    optimizer = optim.AdamW([
        {"params": model.encoder.parameters(), "lr": 1e-5},
        {"params": model.decoder.parameters(), "lr": 3e-4},
    ], weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)

    tail_probs, target, losses = [], None, []
    best_miou, best_epoch, best_pred = -1.0, 0, None
    val_curve = []
    for epoch in range(1, epochs + 1):
        model.train()
        freeze_bn_stats(model.encoder)
        ep = 0.0
        for imgs, msks in train_loader:
            imgs, msks = imgs.to(device), msks.to(device)
            optimizer.zero_grad()
            loss, _, _, _ = criterion(model(imgs), msks)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], max_norm=1.0)
            optimizer.step()
            ep += loss.item()
        scheduler.step()
        losses.append(ep / len(train_loader))

        # Evaluated EVERY epoch, because the arms overfit at different rates and
        # the conclusion turns out to depend on where you stop. Accra, seed 1337:
        # D peaks at ~0.43 by epoch 5 and decays to ~0.30 by 40 while its train
        # loss keeps falling, while B holds its peak. So "6 bands vs RGB" reads
        # +0.0002 at peak and -0.1120 at epoch 40 -- the same runs, two rules.
        # Both are recorded; neither is quietly chosen.
        model.eval()
        lg, mk = [], []
        with torch.no_grad():
            for imgs, msks in val_loader:
                lg.append(torch.softmax(model(imgs.to(device)), dim=1).cpu())
                mk.append(msks)
        probs = torch.cat(lg).numpy()
        target = torch.cat(mk).numpy()

        cm = confusion(probs.argmax(axis=1).ravel(), target.ravel(), NUM_CLASSES)
        m = _miou(iou_from_confusion(cm))
        val_curve.append(m)
        if m > best_miou:
            best_miou, best_epoch = m, epoch
            best_pred = probs.argmax(axis=1).ravel()

        if epoch > epochs - TAIL:
            tail_probs.append(probs)

    del model
    final_pred = tail_probs[-1].argmax(axis=1)
    avg_pred = np.mean(tail_probs, axis=0).argmax(axis=1)
    return {"final_pred": final_pred.ravel(), "avg_pred": avg_pred.ravel(),
            "best_pred": best_pred, "best_epoch": best_epoch, "best_miou": best_miou,
            "val_curve": val_curve,
            "target": target.ravel(), "n_train_patches": len(tr),
            "final_loss": losses[-1]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--limit-folds", type=int, default=None)
    ap.add_argument("--tag", default="loco11")
    args = ap.parse_args()

    device = pick_device()
    print("=" * 78)
    print("11-FOLD PAIRED LOCO -- four arms, no separation loss, fixed budget")
    print(f"device {device} | seed {SEED} | {args.epochs} epochs, final-epoch selection")
    if args.limit_folds:
        print(f"*** PARTIAL: only {args.limit_folds} folds ***")
    print("=" * 78)

    set_determinism(SEED)
    patches = build_all_patches(verbose=False)
    ref_digest = mask_digest(patches)
    print(f"{len(patches)} patches | reference label digest {ref_digest[:16]}")

    arm_images = {}
    for name, (mode, ch) in ARMS.items():
        arm_images[name] = build_arm_images(patches, mode)
        print(f"  {name}: {len(arm_images[name])} x {arm_images[name][0].shape}", flush=True)

    outdir = Path(__file__).resolve().parent / "results" / args.tag
    outdir.mkdir(parents=True, exist_ok=True)

    results_final, results_avg, results_best = {}, {}, {}
    cache: dict = {}

    for name, (mode, ch) in ARMS.items():
        if mask_digest(patches) != ref_digest:
            raise AssertionError(f"{name}: labels changed -- arms not comparable")

        def fold_fn(i, held, train, _name=name, _ch=ch):
            t0 = time.time()
            out = train_one_fold(arm_images[_name], patches, held, _ch, device, args.epochs)
            cache[(_name, held)] = out
            print(f"  [{_name}] fold {i} {held:<11} loss={out['final_loss']:.4f} "
                  f"best={out['best_miou']:.4f}@{out['best_epoch']} "
                  f"{time.time() - t0:.0f}s", flush=True)
            return {"pred": out["final_pred"], "target": out["target"],
                    "n_classes": NUM_CLASSES, "n_train_patches": out["n_train_patches"]}

        print(f"\n--- {name} ---", flush=True)
        res = run_arm(name, fold_fn, cities=LOCO_CLEAN_CITIES, seed=SEED,
                      class_names=CATEGORIES,
                      meta={"mode": mode, "in_chans": ch, "epochs": args.epochs,
                            "selection": "final epoch, fixed budget, no early stop",
                            "separation_loss": False},
                      limit_folds=args.limit_folds)
        results_final[name] = res
        res.save(str(outdir / f"{name}_final.json"))

        # Same folds, re-scored under the other two selection rules. No extra
        # training -- only the choice of which epoch's predictions to score.
        for key, sel, store in (
                ("avg_pred", f"softmax averaged over last {TAIL} epochs", results_avg),
                ("best_pred", "best epoch by held-out mIoU -- SELECTED ON TEST, biased",
                 results_best)):
            alt = ArmResult(name=f"{name}_{'avg' if key == 'avg_pred' else 'best'}",
                            seed=SEED, class_names=CATEGORIES,
                            meta=dict(res.meta, selection=sel))
            for f in res.folds:
                o = cache[(name, f.city)]
                iou = iou_from_confusion(confusion(o[key], o["target"], NUM_CLASSES))
                alt.folds.append(FoldResult(
                    fold=f.fold, city=f.city, miou=_miou(iou),
                    per_class_iou={c: (None if np.isnan(v) else float(v))
                                   for c, v in zip(CATEGORIES, iou)},
                    n_labeled_px=f.n_labeled_px, seconds=0.0,
                    n_train_patches=f.n_train_patches))
            store[name] = alt
            alt.save(str(outdir / f"{name}_{'avg' if key == 'avg_pred' else 'best'}.json"))

    # --- reporting -----------------------------------------------------------
    for label, results in (
            ("FINAL EPOCH, fixed budget (primary -- no selection)", results_final),
            (f"LAST-{TAIL} AVERAGED SOFTMAX (secondary -- no selection)", results_avg),
            ("BEST EPOCH (comparison only -- SELECTED ON TEST, optimistically biased)",
             results_best)):
        arms = list(results.values())
        print("\n" + "=" * 78)
        print(f"{label}")
        print("=" * 78)
        print("\nPer-city mIoU:")
        print(per_city_table(arms))
        print("\nPer-class IoU, averaged over folds:")
        print(per_class_table(arms))

        for a_name, b_name, desc in PAIRS:
            a, b = results[a_name], results[b_name]
            print(f"\n{'-' * 78}\n{desc}:  {b.name} vs {a.name}\n{'-' * 78}")
            print(format_comparison(paired_compare(a, b)))
            print()
            print(format_per_class_comparison(paired_compare_per_class(a, b)))

    summary = {
        "epochs": args.epochs, "seed": SEED, "device": device,
        "limit_folds": args.limit_folds,
        "selection_primary": "final epoch, fixed budget, no early stop",
        "selection_secondary": f"softmax averaged over last {TAIL} epochs",
        "selection_third": "best epoch by held-out mIoU -- selected on test, biased",
        "val_curves": {f"{a}|{c}": cache[(a, c)]["val_curve"] for a, c in cache},
        "pairs": {},
    }
    for a_name, b_name, desc in PAIRS:
        summary["pairs"][f"{b_name}_vs_{a_name}"] = {
            "description": desc,
            "final": {
                "miou": paired_compare(results_final[a_name], results_final[b_name]),
                "per_class": paired_compare_per_class(results_final[a_name],
                                                      results_final[b_name]),
            },
            "avg": {
                "miou": paired_compare(results_avg[a_name], results_avg[b_name]),
                "per_class": paired_compare_per_class(results_avg[a_name],
                                                      results_avg[b_name]),
            },
            "best_selected_on_test": {
                "miou": paired_compare(results_best[a_name], results_best[b_name]),
                "per_class": paired_compare_per_class(results_best[a_name],
                                                      results_best[b_name]),
            },
        }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
