# Four arms, one fold, no separation loss — the means agree and the classes do not

Held-out Accra, seed 1337, production patch geometry, separation loss out of
every arm uniformly. Label masks verified byte-identical across arms by sha256
digest before any training ran.

## Headline

| arm | bands | scaling | mIoU | best epoch |
|---|---|---|---:|---:|
| A | RGB | stretch | 0.4068 | 24 |
| B | RGB | absolute | **0.4337** | 25 |
| C | 6 | stretch | 0.4193 | **4** |
| D | 6 | absolute | 0.4304 | **5** |

| factor | delta |
|---|---:|
| 6 bands at absolute reflectance | **D − B = −0.0033** |
| 6 bands under the stretch | C − A = +0.0125 |
| absolute vs stretch, RGB | B − A = +0.0269 |
| absolute vs stretch, 6 band | D − C = +0.0111 |

**Every effect is under 0.035**, which per the working rules is invisible
unpaired — SE on the mean is 0.017. Direction only. Nothing here is
significant, and nothing here is claimed to be.

## The one result worth carrying

**D − B = −0.0033.** Six bands add nothing over RGB at absolute reflectance.

That **replicates the broken probe's only surviving signal** — D 0.2299 vs B
0.2302, a delta of −0.0003 — on a control that now works and at roughly twice
the absolute mIoU. Two independent measurements, one of them from a run whose
control had collapsed, agree on the same near-zero difference.

If it holds at 11 paired folds, it is the consequential result of this whole
line of work: it points the bottleneck at **data volume**, not spectral
information, and it means the discarded NIR/SWIR1/SWIR2 bands (C41) are not the
missing ingredient they looked like.

## But the mean is hiding a real reshuffle

Per-class IoU, and this is why the working rules say never report the mean
alone:

| class | A rgb/str | B rgb/abs | C 6b/str | D 6b/abs | D − B |
|---|---:|---:|---:|---:|---:|
| standing_water | 0.4003 | 0.4649 | 0.5962 | **0.7324** | **+0.2675** |
| active_construction | 0.1793 | 0.2314 | 0.3136 | **0.3768** | **+0.1454** |
| dense_informal_roofing | 0.2620 | 0.1358 | 0.2353 | 0.2577 | +0.1219 |
| dense_vegetation | 0.4625 | **0.7317** | 0.7867 | 0.7708 | +0.0391 |
| sparse_informal_roofing | 0.2152 | 0.1563 | 0.0977 | 0.1491 | −0.0072 |
| paved_road | **0.6884** | 0.6291 | 0.5886 | 0.5455 | −0.0836 |
| vegetation_clearing | 0.6400 | **0.6869** | 0.3172 | 0.1804 | **−0.5065** |

Six bands **help** `standing_water` by +0.27 and `active_construction` by
+0.15, and **hurt** `vegetation_clearing` by −0.51 and `paved_road` by −0.08.
Those cancel almost exactly in the mean.

The water and construction gains are physically what you would predict from
adding NIR and SWIR — water absorbs strongly in both, and bare/disturbed
construction ground separates on SWIR. So the extra bands are carrying real
information; it is simply not information that raises a 7-class mean on this
fold. "Six bands add nothing" is true of the mean and false of the classes, and
the honest statement of the result has to say both.

`vegetation_clearing` collapsing under 6 bands is the loudest single number
here and is unexplained. It is a thin class (4,177 val px) and one fold, so it
may be noise — but it is the first thing the 11-fold run should be checked
against.

## A threat to validity that must be fixed before 11 folds

**The 6-band arms peaked at epochs 4 and 5 and early-stopped at 12–13; the RGB
arms peaked at 24 and 25 and ran the full 30.**

That is a bands-linked asymmetry, not a scaling one (B, at absolute
reflectance like D, ran to 25). The 6-band arms are therefore being compared at
a very different point on their training curve from the RGB arms, and
`patience=8` from a peak at epoch 4 stops them before the cosine schedule has
annealed. Whether they would recover and pass the RGB arms given the full
budget is untested.

Until that is resolved the comparison should be read as provisional. The fix is
cheap: give every arm the same fixed epoch budget with no early stop, or select
on a fixed epoch, so no arm's stopping point is a free variable. **Do this
before spending ~6–7 hours on 11 folds**, because the current protocol would
bake the asymmetry into all 44 runs.

One further artefact: epoch 13 of arm D took 319 s against a ~16 s norm. That
is machine contention, not a property of the arm, and it affects no result.

## What this run is

One fold, one seed, on Accra — which is not representative, and which the
fidelity run separately scored above the checkpoint's +1 sd band. A magnitude
probe that says an 11-fold paired run is worth its cost, and nothing stronger.
The paired per-fold Wilcoxon over 11 folds remains the standard and remains
unrun, as does the `experiments/harness/loco.py` validation run.

All four arms inherit C43: they are scored on production-style patches, 85.4%
single-class, not on the dense per-pixel task the pipeline runs.
