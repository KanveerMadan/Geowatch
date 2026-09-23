# 11-fold LOCO — stopped deliberately, 8 of 44 folds

**Not a failure. Not a result either.** Stopped by instruction on 2026-09-14
after 8 of 44 folds, with the runner left in place.

## Why it was stopped

1. **Superseded in priority.** The learning-curve gate decides whether the
   annotation campaign happens at all. This run was refining a number whose
   practical implication is already known.
2. **It measures a taxonomy that is being replaced.** These folds score the
   current 7-class taxonomy; the expansion moves to 4 classes
   (impervious / vegetation / water / bare). Re-running against the taxonomy
   that ships measures something usable; this did not.

## What was salvaged, and what it is worth

`partial_results.json` holds 8 folds of **arm A only** (`rgb_stretch`), plus the
full console log in `partial_run.log`.

**Treat the salvaged numbers as provenance, not evidence**, for three reasons:

- **One arm of four.** No comparison is possible. The whole point of the run
  was paired per-class deltas between arms; with a single arm there is nothing
  to pair.
- **8 of 11 folds**, so even that arm's mean is over an unrepresentative subset
  — and the missing folds are capetown, guatemala and nusantara, which include
  both extremes of the existing set.
- **The only statistic that survived is the biased one.** Per-fold predictions
  under the three selection rules were held in memory and written only after an
  arm's 11 folds completed, so nothing was flushed. What the log preserves is
  `best=<miou>@<epoch>` — best epoch by held-out mIoU, which in LOCO is
  **selected on the test set** and optimistically biased. The unbiased
  final-epoch and last-5 readings are gone.

For the record, and not to be quoted as a LOCO number:

| | |
|---|---|
| folds completed | 8 of 11 (arm A only) |
| mean best-epoch mIoU **(selected on test)** | 0.3238 |
| sd | 0.0546 |

| fold | city | best mIoU (biased) | @epoch | final train loss |
|---|---|---|---|---|
| 0 | dharavi | 0.3406 | 15 | 0.0964 |
| 1 | accra | 0.4447 | 14 | 0.1149 |
| 2 | nairobi | 0.3322 | 16 | 0.1235 |
| 3 | jakarta | 0.3214 | 9 | 0.1335 |
| 4 | hcmc | 0.2738 | 4 | 0.1125 |
| 5 | kigali | 0.2866 | 12 | 0.1272 |
| 6 | dhaka | 0.2813 | 7 | 0.1259 |
| 7 | lagos | 0.3102 | 5 | 0.1328 |

That 0.3238 ± 0.0546 sits close to the checkpoint's recorded 0.313 ± 0.0564 —
which is unsurprising rather than confirmatory, since both are max-over-epochs
on the held-out city, i.e. the same biased statistic computed the same way.

One operational note: fold 3 (jakarta) took **23,338 s** against a ~650 s norm
for the other seven. That is machine contention from three jobs running at
once, not a property of the fold.

## What to do when this is re-run

`run_loco_full.py` is unchanged and deliberately kept. Against the 4-class
taxonomy it needs:

- `CATEGORIES` switched to the merged 4 classes, and the patch builders' label
  mapping with it;
- the power floor re-checked — `min_achievable_wilcoxon_p` matters much less
  once thin classes are merged, because the classes that were present in only
  5 and 8 of 11 folds disappear into `impervious` and `vegetation`;
- **no comparison against 0.313 or against the numbers above.** Collapsing
  classes raises mIoU by construction, so the 7-class and 4-class figures are
  not comparable in either direction. This is a standing working rule.
