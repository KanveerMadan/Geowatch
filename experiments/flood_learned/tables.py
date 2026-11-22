"""Markdown tables from results/learned.json -> results/tables.md.

    python -m experiments.flood_learned.tables
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results", "learned.json")
OUT = os.path.join(HERE, "results", "tables.md")
COMP = ("hand", "occurrence", "dist_water", "fluvial", "pluvial", "waterlogging", "flash_flood")
NICE = {"lco__full__lgbm": "LGBM full (LCO)", "lro__full__lgbm": "LGBM full (LRO)",
        "lco__full__logreg": "LogReg full (LCO)", "lro__full__logreg": "LogReg full (LRO)",
        "lco__open__lgbm": "LGBM open (LCO)", "lro__open__lgbm": "LGBM open (LRO)"}


def f3(x):
    return "–" if x is None else f"{x:.3f}"


def fs(x):
    return "–" if x is None else f"{x:+.3f}"


def ci(c, signed=False):
    f = fs if signed else f3
    return f"[{f(c[0])}, {f(c[1])}]" if c and c[0] is not None else ""


def main():
    r = json.load(open(RES))
    tags = sorted(r["runs"])
    head = [t for t in NICE if t in tags]
    L = ["# Learned flood model: full tables", "",
         f"Generated from `results/learned.json` (run {r['run_utc']}). AUC [990 m-block 95% CI]. "
         "LCO = leave-cluster-out, LRO = leave-region-out. Δ = model − comparator; "
         "'clear' = paired 95% interval excludes 0.", ""]
    # means, every run, every group
    L += ["## Mean AUC per group (cluster × block 95% CI)", ""]
    for g, m in r["means"].items():
        L += [f"### {g} ({len(m['events'])} events / {m['clusters']} clusters)", "",
              "| score | mean AUC | Δ vs HAND | Δ vs best baseline | Δ vs fluvial | Δ vs pluvial | "
              "Δ vs waterlogging | Δ vs flash | wins/clear vs HAND |", "|---|---|---|---|---|---|---|---|---|"]
        for k in tags:
            a, d = m["auc"][k], m["delta"][k]
            L.append(f"| {k} | {f3(a['mean'])} {ci(a['ci'])} | " + " | ".join(
                f"{fs(d[x]['mean'])} {ci(d[x]['ci'], True)}" for x in
                ("hand", "best", "fluvial", "pluvial", "waterlogging", "flash_flood"))
                + f" | {d['hand']['beats']}/{d['hand']['n']} ({d['hand']['clear_wins']} clear, "
                  f"{d['hand']['clear_losses']} clearly worse) |")
        for k in COMP:
            a = m["auc"][k]
            L.append(f"| *{k}* | {f3(a['mean'])} {ci(a['ci'])} | | | | | | | |")
        L.append("")
    # per event, headline runs
    L += ["## Per event (headline runs)", "",
          "| event | region | type | f/d | HAND | best baseline | fluvial | pluvial | waterlog. | flash | "
          + " | ".join(NICE[t] for t in head) + " | Δ LGBM-LCO vs HAND |",
          "|" + "---|" * (11 + len(head))]
    for n, e in r["per_event"].items():
        a, c = e["auc"], e["ci"]
        dd = e["delta"].get("lco__full__lgbm", {}).get("hand")
        L.append(f"| {n} | {r['regions'][n]} | {', '.join(r['mechanism'][n])} | "
                 f"{e['flooded']}/{e['dry']} | " +
                 " | ".join(f"{f3(a[k])} {ci(c[k])}" for k in ("hand",)) +
                 f" | {e['best_baseline']} {f3(a[e['best_baseline']])} | " +
                 " | ".join(f3(a[k]) for k in ("fluvial", "pluvial", "waterlogging", "flash_flood"))
                 + " | " + " | ".join(f"{f3(a[t])} {ci(c[t])}" for t in head) +
                 (f" | {fs(dd['delta'])} {ci(dd['ci'], True)} |" if dd else " | |"))
    L.append("")
    # every run, per event point AUC
    L += ["## Per event, every run (point AUC)", "", "| event | " + " | ".join(tags) + " |",
          "|" + "---|" * (1 + len(tags))]
    for n, e in r["per_event"].items():
        L.append(f"| {n} | " + " | ".join(f3(e["auc"][t]) for t in tags) + " |")
    L.append("")
    # calibration
    L += ["## Calibration (pooled held-out labelled cells, event-weighted)", "",
          "| run | ECE | Brier | Brier (constant) | Brier skill | intercept | slope | "
          "event prevalence ρ | call it |", "|---|---|---|---|---|---|---|---|---|"]
    for t, c in r["calibration"].items():
        L.append(f"| {t} | {c['ece']:.3f} {ci(c['ci']['ece'])} | {c['brier']:.4f} | "
                 f"{c['brier_constant']:.4f} | {c['brier_skill']:+.3f} {ci(c['ci']['brier_skill'], True)} | "
                 f"{c['intercept']:+.3f} {ci(c['ci']['intercept'], True)} | {c['slope']:.3f} "
                 f"{ci(c['ci']['slope'])} | {c['event_prevalence_spearman']:+.2f} | {c['call_it']} |")
    L.append("")
    for t, c in r["calibration"].items():
        L += [f"Reliability, {t}:", "", "| bin | weight | mean predicted | observed |",
              "|---|---|---|---|"]
        for b in c["bins"]:
            if b:
                L.append(f"| {b['lo']:.1f}–{b['hi']:.1f} | {b['weight']:.3f} | "
                         f"{b['mean_pred']:.3f} | {b['observed']:.3f} |")
        L.append("")
    # importance
    imp = r["importance"]
    L += ["## Feature importance (LGBM full, LCO)", "",
          "| feature | permutation: mean held-out AUC drop | events hurt | gain share |",
          "|---|---|---|---|"]
    for f, v in sorted(imp["permutation"].items(), key=lambda kv: -kv[1]["mean_auc_drop"]):
        L.append(f"| {f} | {v['mean_auc_drop']:+.4f} | {v['events_hurt']}/{v['n']} | "
                 f"{imp['gain_share_mean_over_folds'].get(f, 0):.3f} |")
    L += ["", "| group | mean held-out AUC drop | events hurt |", "|---|---|---|"]
    for g, v in sorted(r["importance_groups"].items(), key=lambda kv: -kv[1]["mean_auc_drop"]):
        L.append(f"| {g} | {v['mean_auc_drop']:+.4f} | {v['events_hurt']}/{v['n']} |")
    L.append("")
    if r.get("learning_curve"):
        L += ["## Learning curve (LGBM full, LCO; share of training clusters)", "",
              "| share | mean training events | mean AUC | mean Δ vs HAND |", "|---|---|---|---|"]
        for k, v in r["learning_curve"].items():
            L.append(f"| {k} | {v['mean_train_events']} | {v['mean_auc']:.3f} | "
                     f"{v['mean_minus_hand']:+.3f} |")
        L.append("")
    # setting tags
    L += ["## Setting tags per event", "",
          "| event | settlement | mountain | arid (Köppen) | coastal | delta | coast km | median elev m |",
          "|---|---|---|---|---|---|---|---|"]
    for n, t in r["setting_tags"].items():
        if t:
            L.append(f"| {n} | {t['settlement']} | {t['mountain']} | {t['arid']} ({t['koppen']['class']}) "
                     f"| {t['coastal']} | {t['delta']} | {f3(t['coast_distance_km'])} | "
                     f"{f3(t['elev_median_m'])} |")
    with open(OUT, "w") as fh:
        fh.write("\n".join(L) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
