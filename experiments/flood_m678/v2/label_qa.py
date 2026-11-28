"""
M6–M8 v2 step 2: DEV label QA, part A (local files only: no Earth Engine, no prediction, no terrain).

    python -m experiments.flood_m678.v2.label_qa      # -> label_qa.json, funnel.csv

Blind to prediction: reads only the label rasters (state, sensor family, scene, offset, union) and lead metadata.
No model score, physics score, HAND or elevation is loaded, so no label can be kept or dropped by agreement
with a method. Flags are REPORTED; they never remove a label.

Per label:
- phase disagreement: share of scored cells (flooded or dry in the merge) that the all-scene union calls
  flooded while the nearest-to-crest merge calls them dry. A large share means the flood moved between scenes.
- sensor mix: optical share of scored cells; radar-only labels are listed (they need the part-B visual check).
- flooded share of scored cells: flagged below 0.5 % (a few speckle cells) or above 60 % (few true dry controls).
- M7 only: flooded cells within 5 km of the dam or breach anchor. Amendment 6 / decisions: a small-dam label is
  M7 evidence only if at least 50 flooded cells lie within 5 km of the dam; otherwise its flood is likely the
  storm's, and it is reported as such.
Funnel: leads labelled -> no flooded cell -> below the 50/50 floor -> usable, by submode, country, crest precision
and lag to crest.

Part B (needs Earth Engine; queued behind the corridor): optical-vs-radar kappa where both observe a cell
(PREREGISTRATION), and a seeded random visual sample of usable labels (true colour with the label drawn on top,
no prediction), 4 per submode.
"""
from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.expanduser("~/.cache/geowatch/m678v2/dev/labels")
NEAR_KM = 5.0


def _cells_lonlat(meta, mask):
    from pyproj import Transformer
    g = meta["grid"]
    a, _, c, _, e, f = g["transform"]
    rr, cc = np.nonzero(mask)
    x, y = c + (cc + 0.5) * a, f + (rr + 0.5) * e
    lon, lat = Transformer.from_crs(g["crs"], "EPSG:4326", always_xy=True).transform(x, y)
    return np.asarray(lat), np.asarray(lon)


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    h = (np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * np.arcsin(np.minimum(1.0, np.sqrt(h)))


def lag_bin(h):
    if h in ("", None):
        return "none"
    h = abs(float(h))
    return "0 h (in crest window)" if h == 0 else "<= 24 h" if h <= 24 else "<= 48 h" if h <= 48 else "> 48 h"


def main():
    leads = {r["lead_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "leads.csv")))}
    prov = list(csv.DictReader(open(os.path.join(HERE, "provenance.csv"))))
    strata = {}
    for f in sorted(os.listdir(HERE)):
        if f.startswith("m7_strata_") and f.endswith(".json"):
            for cid, c in json.load(open(os.path.join(HERE, f)))["components"].items():
                strata[cid] = c["stratum"]
    per, funnel = [], defaultdict(Counter)
    for p in prov:
        lid = p["lead"]
        L = leads.get(lid, {})
        stage = ("no flooded cell" if p["dropout"] else "usable" if p["usable"] == "True" else "below 50/50 floor")
        for key in (("submode", p["submode"]), ("country", L.get("country") or "?"),
                    ("crest precision", L.get("crest_kind") or "?"), ("lag to crest", lag_bin(p["min_abs_offset_h"]))):
            funnel[f"{p['type']}/{key[0]}={key[1]}"][stage] += 1
        if p["dropout"] or not p["flooded"]:
            continue
        z = np.load(os.path.join(LABELS, lid.replace(":", "__") + ".npz"), allow_pickle=False)
        y, fam, uni = z["y"], z["family"], z["union"]
        meta = json.loads(str(z["meta"]))
        scored = np.isin(y, (0, 1))
        n = int(scored.sum())
        r = {"lead": lid, "type": p["type"], "submode": p["submode"], "usable": p["usable"] == "True",
             "flooded": int((y == 1).sum()), "dry": int((y == 0).sum()),
             "phase_disagreement": round(float(((uni == 1) & (y == 0)).sum() / n), 4) if n else None,
             "optical_share": round(float((fam[scored] == 1).mean()), 3) if n else None,
             "flooded_share": round(float((y == 1).sum() / n), 4) if n else None}
        flags = []
        if r["optical_share"] == 0:
            flags.append("radar_only")
        if r["flooded_share"] is not None and r["flooded_share"] < 0.005:
            flags.append("flooded_share_below_0.5pct")
        if r["flooded_share"] is not None and r["flooded_share"] > 0.60:
            flags.append("flooded_share_above_60pct")
        if r["phase_disagreement"] is not None and r["phase_disagreement"] > 0.10:
            flags.append("phase_disagreement_above_10pct")
        if p["type"] == "M7":
            lat, lon = _cells_lonlat(meta, y == 1)
            d = _km(lat, lon, float(L["lat"]), float(L["lon"]))
            r["flooded_within_5km_of_anchor"] = int((d <= NEAR_KM).sum())
            r["stratum"] = strata.get(p["component"], "?")
            if r["stratum"] == "small_dam":
                r["m7_evidence"] = bool(r["usable"] and r["flooded_within_5km_of_anchor"] >= 50)
                if r["usable"] and not r["m7_evidence"]:
                    flags.append("small_dam_flood_not_near_dam")
        r["flags"] = flags
        per.append(r)
    use = [r for r in per if r["usable"]]
    summary = {
        "labels": len(prov), "with_flooded_cells": len(per), "usable": len(use),
        "flag_counts_usable": dict(Counter(f for r in use for f in r["flags"])),
        "median_phase_disagreement_usable": float(np.median([r["phase_disagreement"] for r in use])) if use else None,
        "radar_only_usable": sum("radar_only" in r["flags"] for r in use),
        "m7": [r for r in per if r["type"] == "M7"],
    }
    json.dump({"summary": summary, "labels": per}, open(os.path.join(HERE, "label_qa.json"), "w"), indent=1, sort_keys=True)
    with open(os.path.join(HERE, "funnel.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["group", "labelled", "no flooded cell", "below 50/50 floor", "usable"])
        for k in sorted(funnel):
            c = funnel[k]
            w.writerow([k, sum(c.values()), c["no flooded cell"], c["below 50/50 floor"], c["usable"]])
    print(json.dumps({k: v for k, v in summary.items() if k != "m7"}, sort_keys=True))
    for r in summary["m7"]:
        print(r)


if __name__ == "__main__":
    main()
