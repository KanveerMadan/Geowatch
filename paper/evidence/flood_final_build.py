"""
Tables, data manifests and figures for the flood_final evidence packs
(M1 update, M2 pluvial, M3 waterlogging, M4 flash flood, M5 coastal, M9 compound).

    python paper/evidence/flood_final_build.py          # from the repo root

Read-only on results. It reads:
  experiments/flood_final/results/{method_choice,dev_report,heldout}.json
  experiments/flood_final/registry_units.json, PREREGISTRATION.md, PREREG_HASH.txt
  experiments/flood_final/{sfincs,urban}/results/*.json
and git history (commit ids and dates). No Earth Engine, network or scoring run.
heldout.json is optional: without it the held-out tables are not written.
Every CSV row carries source_file, source_commit and source_commit_date.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FF = "experiments/flood_final"
RES = f"{FF}/results"
PACKS = {"fluvial": "M1_fluvial", "pluvial": "M2_pluvial", "waterlogging": "M3_waterlogging",
         "flash_flood": "M4_flash_flood", "coastal": "M5_coastal", "compound": "M9_compound"}
MODULE = {"fluvial": "fluvial", "pluvial": "pluvial", "waterlogging": "waterlogging",
          "flash_flood": "flash_flood"}
BASE = ("hand", "neg_elev_glo30", "occurrence", "dist_water", "neg_dist_coast")


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def src(path):
    """(source_file, commit, commit date) of the last commit touching path; 'uncommitted' if none."""
    c = git("log", "-1", "--format=%h|%cI", "--", path)
    if not c:
        return {"source_file": path, "source_commit": "uncommitted", "source_commit_date": ""}
    h, d = c.split("|")
    return {"source_file": path, "source_commit": h, "source_commit_date": d}


def load(path):
    p = os.path.join(ROOT, path)
    return json.load(open(p)) if os.path.exists(p) else None


def write_csv(path, rows):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, keys)
        w.writeheader()
        w.writerows(rows)


def r4(x):
    return None if x is None else round(float(x), 4)


def main():
    choice = load(f"{RES}/method_choice.json")
    dev = load(f"{RES}/dev_report.json")
    held = load(f"{RES}/heldout.json")
    regu = load(f"{FF}/registry_units.json")
    regu = {u["event_id"]: u for u in (regu if isinstance(regu, list) else regu["units"])}
    s_choice, s_dev, s_held = src(f"{RES}/method_choice.json"), src(f"{RES}/dev_report.json"), src(f"{RES}/heldout.json")
    prereg = open(os.path.join(ROOT, FF, "PREREGISTRATION.md"), "rb").read()
    hashtxt = open(os.path.join(ROOT, FF, "PREREG_HASH.txt")).read()
    freeze = git("rev-list", "-n", "1", "flood-final-heldout-freeze")
    pre_rows = [{"file": f"{FF}/PREREGISTRATION.md", "sha256_now": hashlib.sha256(prereg).hexdigest(),
                 "sha256_recorded": next((l.split()[-1] for l in hashtxt.splitlines() if l.startswith("sha256:")), ""),
                 "companion": hashtxt.replace("\n", " | "),
                 "freeze_tag": "flood-final-heldout-freeze", "freeze_commit": freeze[:7],
                 "freeze_commit_date": git("log", "-1", "--format=%cI", freeze) if freeze else "",
                 "heldout_preflight": json.dumps(held["preflight"]) if held else "",
                 "heldout_run_utc": held["run_utc"] if held else "", **src(f"{FF}/PREREGISTRATION.md")}]
    for ty, pack in PACKS.items():
        out = os.path.join(HERE, pack, "tables", "flood_final") if ty == "fluvial" else os.path.join(HERE, pack, "tables")
        ch = choice["choice"][ty]
        chosen = ch["chosen"]
        mod = MODULE.get(ty)
        write_csv(os.path.join(out, "preregistration_hashes.csv"), pre_rows)
        rows = []
        for c, v in sorted(ch["lro_mean_auc"].items(), key=lambda kv: -kv[1]):
            rows.append({"type": ty, "candidate": c, "lro_mean_auc": r4(v), "lco_mean_auc": r4(ch["lco_mean_auc"].get(c)),
                         "chosen": c == chosen, "n_units": ch["n"], **s_choice})
        for b, v in ch["baselines_lro"].items():
            rows.append({"type": ty, "candidate": f"baseline:{b}", "lro_mean_auc": r4(v), "lco_mean_auc": None,
                         "chosen": False, "n_units": ch["n"], **s_choice})
        write_csv(os.path.join(out, "dev_method_choice.csv"), rows)
        g = dev["groups"][ty]
        rows = []
        for k, m in sorted(g["mean_auc"].items(), key=lambda kv: -kv[1]["mean"]):
            dh = g["minus_hand"].get(k, {})
            rows.append({"type": ty, "score": k, "is_chosen": k == f"lro:{chosen}", "mean_auc": m["mean"],
                         "ci_lo": m["ci"][0], "ci_hi": m["ci"][1], "minus_hand": dh.get("mean"),
                         "minus_hand_ci_lo": (dh.get("ci") or [None])[0], "minus_hand_ci_hi": (dh.get("ci") or [None, None])[1],
                         "n_units": m["n"], "n_clusters": g["clusters"], **s_dev})
        write_csv(os.path.join(out, "dev_means.csv"), rows)
        keys = [f"lro:{chosen}", *BASE] + ([mod] if mod else [])
        rows = []
        for n in g["units"]:
            u = dev["units"][n]
            rec = {"unit": n, "type": ty, "tags": " ".join(u["tags"]), "cluster": u["cluster"],
                   "flooded": u["flooded"], "dry": u["dry"]}
            for k in keys:
                rec[k] = u["auc"].get(k)
                ci = u["ci"].get(k) or [None, None]
                rec[f"{k}_ci_lo"], rec[f"{k}_ci_hi"] = ci
            rows.append({**rec, **s_dev})
        write_csv(os.path.join(out, "dev_per_unit.csv"), rows)
        # data manifest: DEV members + RESERVED members of this type
        man = []
        for n in g["units"]:
            u = regu.get(n)
            dd = dev["units"][n]
            box = (u or {}).get("geometry", {}).get("boxes", [{}])[0].get("bbox") if u else None
            man.append({"event": n, "split": "DEV", "date": (u or {}).get("date", ""), "tags": " ".join(dd["tags"]),
                        "region": (u or {}).get("flood_final", {}).get("region", "batch0"),
                        "bbox_w": box[0] if box else "", "bbox_s": box[1] if box else "",
                        "bbox_e": box[2] if box else "", "bbox_n": box[3] if box else "",
                        "reference": " ".join((u or {}).get("products", [])) or "flood_learned batch 0 (see experiments/flood_learned/REPORT.md)",
                        "flooded_cells": dd["flooded"], "dry_cells": dd["dry"], "storm_cluster": dd["cluster"],
                        "source_file": f"{RES}/dev_report.json"})
        for n, u in regu.items():
            if u["role"] != "reserved" or ty not in u["flood_final"]["tags"]:
                continue
            h = (held or {}).get("units", {}).get(n)
            status = ("scored" if h else "not qualifying" if n in (held or {}).get("not_qualifying", {})
                      else "missing" if n in (held or {}).get("missing", {}) else "not yet scored")
            pt = u["geometry"].get("point", ["", ""])
            man.append({"event": n, "split": "RESERVED", "date": u["date"], "tags": " ".join(u["flood_final"]["tags"]),
                        "region": u["flood_final"]["region"], "centre_lon": pt[0], "centre_lat": pt[1],
                        "reference": " ".join(map(str, u["flood_final"].get("reference", u.get("products", [])))),
                        "flooded_cells": h["flooded"] if h else "", "dry_cells": h["dry"] if h else "",
                        "storm_cluster": u["storm_cluster"], "heldout_status": status,
                        "source_file": f"{FF}/registry_units.json" + (f"; {RES}/heldout.json" if held else "")})
        write_csv(os.path.join(os.path.dirname(out) if ty == "fluvial" else os.path.join(HERE, pack),
                               "data_manifest_flood_final.csv" if ty == "fluvial" else "data_manifest.csv"), man)
        if held:
            hg = held["groups"].get(ty)
            rows = []
            for k, m in sorted((hg or {}).get("mean_auc", {}).items(), key=lambda kv: -kv[1]["mean"]):
                dh = hg["minus_hand"].get(k, {})
                rows.append({"type": ty, "score": k, "mean_auc": m["mean"], "ci_lo": m["ci"][0], "ci_hi": m["ci"][1],
                             "minus_hand": dh.get("mean"), "minus_hand_ci_lo": (dh.get("ci") or [None])[0],
                             "minus_hand_ci_hi": (dh.get("ci") or [None, None])[1], "n_units": m["n"],
                             "n_clusters": hg["clusters"], **s_held})
            write_csv(os.path.join(out, "heldout_means.csv"), rows)
            hk = [f"learned_raw:{chosen}", f"learned:{chosen}", *BASE] + ([mod] if mod else [])
            rows = []
            for n, u in held["units"].items():
                if ty not in u["tags"]:
                    continue
                rec = {"unit": n, "type": ty, "region": u["region"], "cluster": u["cluster"],
                       "flooded": u["flooded"], "dry": u["dry"]}
                for k in hk:
                    rec[k] = u["auc"].get(k)
                    ci = u["ci"].get(k) or [None, None]
                    rec[f"{k}_ci_lo"], rec[f"{k}_ci_hi"] = ci
                    rec[f"{k}_ap"] = u.get("ap", {}).get(k)
                    rec[f"{k}_iou_area_matched"] = u.get("iou_area_matched", {}).get(k)
                rows.append({**rec, **s_held})
            write_csv(os.path.join(out, "heldout_per_unit.csv"), rows)
            v = held["verdicts"].get(ty, {})
            vr = [{"type": ty, "test": "learned (pre-registered choice)", "chosen": v.get("chosen"),
                   "verdict": v.get("verdict"), "mean_auc": v.get("mean_auc"),
                   "minus_hand": (v.get("minus_hand") or {}).get("mean"),
                   "minus_hand_ci": json.dumps((v.get("minus_hand") or {}).get("ci")),
                   "units": v.get("units"), "clusters": v.get("clusters"), **s_held}]
            if ty == "fluvial" and "fluvial_module_retest" in held["verdicts"]:
                w = held["verdicts"]["fluvial_module_retest"]
                vr.append({"type": ty, "test": "fluvial module (validated config) re-test", "chosen": "fluvial",
                           "verdict": w.get("verdict"), "mean_auc": w.get("mean_auc"),
                           "minus_hand": (w.get("minus_hand") or {}).get("mean"),
                           "minus_hand_ci": json.dumps((w.get("minus_hand") or {}).get("ci")),
                           "units": w.get("units"), "clusters": w.get("clusters"), **s_held})
            write_csv(os.path.join(out, "heldout_verdict.csv"), vr)
        figures(ty, pack, dev, held, chosen)
        print(f"{pack}: tables written{' (with held-out)' if held else ''}")
    return 0


def figures(ty, pack, dev, held, chosen):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figdir = os.path.join(HERE, pack, "figures", "flood_final") if ty == "fluvial" else os.path.join(HERE, pack, "figures")
    os.makedirs(figdir, exist_ok=True)
    sets = [("dev", "DEV, leave-region-out", dev["groups"][ty]["units"], dev["units"], f"lro:{chosen}")]
    if held and ty in held["groups"]:
        sets.append(("heldout", "RESERVED, scored once", held["groups"][ty]["units"], held["units"],
                     f"learned_raw:{chosen}"))
    for tag, title, names, units, key in sets:
        series = [(key, f"learned ({chosen})", "#1f6fb2"), ("hand", "HAND", "#888888"),
                  ("neg_elev_glo30", "low elevation (GLO-30)", "#d08a2c")]
        fig, ax = plt.subplots(figsize=(7.5, 0.32 * len(names) + 1.4))
        names = sorted(names, key=lambda n: units[n]["auc"].get(key) or 0)
        for j, (k, lab, col) in enumerate(series):
            for i, n in enumerate(names):
                v, ci = units[n]["auc"].get(k), units[n]["ci"].get(k) or [None, None]
                if v is None:
                    continue
                y = i + (j - 1) * 0.22
                if ci[0] is not None:
                    ax.plot(ci, [y, y], color=col, lw=1, alpha=0.6)
                ax.plot(v, y, "o", color=col, ms=3.5, label=lab if i == 0 else None)
        ax.axvline(0.5, color="#bbbbbb", lw=0.8, ls=":")
        ax.axvline(0.7, color="#bbbbbb", lw=0.8, ls="--")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=7)
        ax.set_xlabel("within-event AUC (95% CI, 990 m block bootstrap)")
        ax.set_xlim(0, 1)
        ax.set_title(f"{ty}: {title}", fontsize=9)
        ax.legend(fontsize=7, loc="lower right")
        fig.tight_layout()
        for ext in ("png", "svg"):
            fig.savefig(os.path.join(figdir, f"fig_{tag}_per_event_auc.{ext}"), dpi=150)
        plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
