"""
Per-pixel flood-likelihood maps.

    python -m experiments.flood_learned.maps

  * MAPS/<event>__lco_full_lgbm.tif  the held-out (leave-cluster-out) map of
    every event: the model that produced it never saw that event's cluster.
  * MAPS/model_full_29.txt            LightGBM fitted on all 29 events (the
    model a GeoWatch run would use; it has no held-out score of its own --
    its expected skill is the cross-validated one).
  * results/figures/maps.png          reference vs held-out map vs HAND for
    a few events.
Values are the model's output in [0, 1]. Whether it may be called a
probability is decided by evaluate.calibration (REPORT.md); the GeoTIFF band
is named accordingly.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

from experiments.flood_learned import events as LE
from experiments.flood_learned import features as FT
from experiments.flood_learned import model as M

MAPS = os.path.expanduser(os.environ.get("GEOWATCH_LEARNED_MAPS",
                                         "~/.cache/geowatch/flood_learned/maps"))
HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "results", "figures", "maps.png")
FIG_EVENTS = ("hanoi", "kolonnawa", "valencia_2024", "dubai_2024", "sylhet_2022", "thai_binh")


def write_tif(path, arr, grid, band_name):
    import rasterio
    from affine import Affine
    t = Affine(*grid["transform"][:6])
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype="float32", crs=grid["crs"], transform=t, nodata=np.nan,
                       compress="deflate") as ds:
        ds.write(arr.astype(np.float32), 1)
        ds.set_band_description(1, band_name)


def main():
    names = [c["unit"] for c in LE.batch0() if os.path.exists(FT.path(c["unit"]))]
    tables = M.load_tables(names)
    preds, _ = M.load_preds("lco__full__lgbm")
    res = json.load(open(os.path.join(HERE, "results", "learned.json")))
    call = res["calibration"]["lco__full__lgbm"]["call_it"]
    band = f"flood_likelihood_{call}"
    os.makedirs(MAPS, exist_ok=True)
    for n in names:
        shp = tuple(tables[n]["meta"]["shape"])
        write_tif(os.path.join(MAPS, f"{n}__lco_full_lgbm.tif"), preds[n].reshape(shp),
                  tables[n]["meta"]["grid"], band)
    cols = M.columns("full")
    X, y, w = M.training_rows(tables, names, cols)
    m = M.fit_lgbm(X, y, w)
    m.booster_.save_model(os.path.join(MAPS, "model_full_29.txt"))
    print("wrote", len(names), "maps and the 29-event model to", MAPS)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ev = [e for e in FIG_EVENTS if e in names]
    fig, ax = plt.subplots(len(ev), 3, figsize=(9, 3 * len(ev)))
    hi = FT.COMPARATORS.index("hand")
    for i, n in enumerate(ev):
        t = tables[n]
        shp = tuple(t["meta"]["shape"])
        lab = t["y"].reshape(shp).astype(float)
        lab[lab < 0] = np.nan
        ax[i, 0].imshow(lab, cmap="Blues", vmin=0, vmax=1, interpolation="nearest")
        ax[i, 0].set_title(f"{n}: reference (white = unobserved)", fontsize=8)
        a = res["per_event"][n]["auc"]
        ax[i, 1].imshow(preds[n].reshape(shp), cmap="viridis", vmin=0, vmax=1)
        ax[i, 1].set_title(f"held-out model {call}, AUC {a['lco__full__lgbm']:.2f}", fontsize=8)
        ax[i, 2].imshow(t["C"][:, hi].reshape(shp), cmap="viridis")
        ax[i, 2].set_title(f"-HAND, AUC {a['hand']:.2f}", fontsize=8)
        for a_ in ax[i]:
            a_.set_axis_off()
    fig.tight_layout()
    os.makedirs(os.path.dirname(FIG), exist_ok=True)
    fig.savefig(FIG, dpi=80)
    print("wrote", FIG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
