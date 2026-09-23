"""
Arm E LOCO probe: 4 cities x 2 seeds x 2 arms, 3200 steps (the main gate budget).

Each fold trains ONE model and scores it on TWO val sets built from the same
held-out city:
    val_base    baseline geometry + baseline masks  (the gate run's yardstick,
                so numbers are comparable to the 132-fold run)
    val_native  native geometry + canvas masks      (the harder, multi-class
                yardstick arm E is built for)
Both arms are scored on both, so neither arm is judged only on its own target.

Hyperparameters, loss, augmentation and determinism are learning_curve.run_fold's.
"""

import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import sys, json, time, argparse
from collections import Counter
from pathlib import Path
import numpy as np
import torch, torch.optim as optim
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader
from experiments.band_reflectance.arm_inputs import build_arm_images
from experiments.band_reflectance.fidelity_run import (
    CombinedLoss, compute_per_class_iou, freeze_bn_stats, pick_device, set_determinism)
from experiments.band_reflectance.production_patches_v2 import (
    CATEGORIES, IGNORE_INDEX, NUM_CLASSES, build_all_patches)
from experiments.band_reflectance.run_comparison import ArmDataset, ArmSeg
from fix_build_e import build_arm_e

BATCH, TAIL, MODE, IN_CHANS = 16, 5, "rgb_stretch", 3


def run_fold(patches, tr_imgs, tr_msks, valsets, held, device, seed, steps):
    tr = [i for i, p in enumerate(patches) if p["city"] != held]
    va = [i for i, p in enumerate(patches) if p["city"] == held]
    n_batches = max(1, len(tr) // BATCH)
    epochs = max(1, int(round(steps / n_batches)))

    counts = Counter(patches[i]["label"] for i in tr)
    arr = np.maximum(np.array([counts.get(c, 1) for c in CATEGORIES], dtype=np.float32), 1)
    w = 1.0 / arr
    w = torch.tensor(w / w.sum() * NUM_CLASSES, dtype=torch.float32).to(device)

    set_determinism(seed)
    train_loader = DataLoader(
        ArmDataset([tr_imgs[i] for i in tr], [tr_msks[i] for i in tr], augment=True),
        batch_size=BATCH, shuffle=True, num_workers=0, drop_last=True)
    vloaders = {k: DataLoader(ArmDataset([im[i] for i in va], [mk[i] for i in va], augment=False),
                              batch_size=BATCH, shuffle=False, num_workers=0)
                for k, (im, mk) in valsets.items()}

    model = ArmSeg(IN_CHANS).to(device)
    criterion = CombinedLoss(class_weights=w, ignore_index=IGNORE_INDEX, dice_weight=0.5,
                             separation_weight=0.0, separation_margin=2.0,
                             class_a_idx=None, class_b_idx=None)
    optimizer = optim.AdamW([{"params": model.encoder.parameters(), "lr": 1e-5},
                             {"params": model.decoder.parameters(), "lr": 3e-4}],
                            weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)

    curves = {k: [] for k in valsets}; pcs = {k: [] for k in valsets}; losses = []
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

        model.eval()
        with torch.no_grad():
            for k, vl in vloaders.items():
                lg, mk = [], []
                for imgs, msks in vl:
                    lg.append(model(imgs.to(device)).cpu()); mk.append(msks)
                pc = compute_per_class_iou(torch.cat(lg), torch.cat(mk), NUM_CLASSES, IGNORE_INDEX)
                pcs[k].append({CATEGORIES[c]: v for c, v in pc.items()})
                curves[k].append(float(np.mean([v for v in pc.values() if v is not None])))
    del model

    out = {"city": held, "n_train": len(tr), "n_val": len(va), "epochs": epochs,
           "steps": epochs * n_batches, "final_train_loss": losses[-1], "loss_curve": losses}
    t = min(TAIL, epochs)
    for k in valsets:
        cv = curves[k]
        out[f"final[{k}]"] = cv[-1]
        out[f"last5[{k}]"] = float(np.mean(cv[-t:]))
        out[f"best_ON_TEST[{k}]"] = max(cv)
        out[f"best_epoch[{k}]"] = int(np.argmax(cv)) + 1
        out[f"per_class_last5[{k}]"] = {
            c: (float(np.mean([h[c] for h in pcs[k][-t:] if h[c] is not None]))
                if any(h[c] is not None for h in pcs[k][-t:]) else None) for c in CATEGORIES}
        out[f"curve[{k}]"] = cv
    return out


ap = argparse.ArgumentParser()
ap.add_argument("--cities", default="dharavi,capetown,jakarta,hcmc")
ap.add_argument("--seeds", default="1337,7")
ap.add_argument("--steps", type=int, default=3200)
ap.add_argument("--out", default=str(RESULTS / "armE_raw.json"))
args = ap.parse_args()
cities = args.cities.split(","); seeds = [int(s) for s in args.seeds.split(",")]

device = pick_device()
base, pE, mE, touched = build_arm_e()
mA = [p["mask"] for p in base]
imgA = build_arm_images(base, MODE)
imgE = build_arm_images(pE, MODE)
valsets = {"val_base": (imgA, mA), "val_native": (imgE, mE)}
arms = {"A_baseline": (imgA, mA), "E_native_canvas": (imgE, mE)}
print(f"device {device} | {len(base)} patches | rebuilt {len(touched)} | steps {args.steps}")
print(f"cities {cities} | seeds {seeds} | {len(cities)*len(seeds)*len(arms)} folds\n", flush=True)

out_path = Path(args.out)
results = json.loads(out_path.read_text()) if out_path.exists() else []
done = {(r["arm"], r["city"], r["seed"]) for r in results}
for seed in seeds:
    for city in cities:
        for arm, (im, mk) in arms.items():
            if (arm, city, seed) in done:
                print(f"  s{seed} {city:<10}{arm:<17} cached", flush=True); continue
            t0 = time.time()
            r = run_fold(base, im, mk, valsets, city, device, seed, args.steps)
            r.update({"arm": arm, "seed": seed})
            results.append(r); out_path.write_text(json.dumps(results, indent=2))
            print(f"  s{seed} {city:<10}{arm:<17} ep={r['epochs']:>3} "
                  f"base[l5]={r['last5[val_base]']:.4f} nat[l5]={r['last5[val_native]']:.4f} "
                  f"base[best]={r['best_ON_TEST[val_base]']:.4f} loss={r['final_train_loss']:.4f} "
                  f"{time.time()-t0:.0f}s", flush=True)
print("\nDONE", flush=True)
