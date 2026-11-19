"""
Build the M1 fluvial evidence pack: tables/, data_manifest.csv, figures/.

    python paper/evidence/M1_fluvial/build_evidence.py            # from the repo root

Read-only on every existing result. It only reads:
  * experiments/flood_validation/result_*.json and PREREGISTRATION*.md (rounds 1-4)
  * experiments/flood_baselines/results/baselines.json (exp/flood-baselines, d1894e4)
  * the experiment registry (experiments/flood_core/registry/events.json)
  * git history (commit ids, dates, file contents at a commit)
and, for figures (b) and (c) only, the cached per-cell arrays of the
baselines experiment (~/.cache/geowatch/flood_baselines/<unit>.npz and the
cached round 2-4 references). Those figures recompute the per-cell scores
with the same code as experiments/flood_baselines/score.py and check that the
recomputed AUC equals the stored one (tables/figure_auc_check.csv). No Earth
Engine, network or new scoring run.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

TABLES = os.path.join(HERE, "tables")
FIGS = os.path.join(HERE, "figures")
FV = "experiments/flood_validation"
BASELINES = "experiments/flood_baselines/results/baselines.json"
R1 = f"{FV}/result_2026-10-28.json"
R2 = f"{FV}/result_round2_2026-10-28.json"
R3 = f"{FV}/result_round3_2026-10-29.json"
R4 = f"{FV}/result_round4_2026-10-30.json"
PREREG = {R1: f"{FV}/PREREGISTRATION.md", R2: f"{FV}/PREREGISTRATION_ROUND2.md",
          R3: f"{FV}/PREREGISTRATION_ROUND3.md", R4: f"{FV}/PREREGISTRATION_ROUND4.md"}
JRC_CIRCULAR = ("accra", "capetown", "dhaka", "hcmc", "nusantara")
WINS = ("kyaukpyu", "kolonnawa", "nam_dinh", "paiporta", "encantado")   # CI above 0, 990 m
MAP_EVENTS = ("hanoi", "assam_2026")       # best round-2 held-out; worst round-4 test
SCORES = ("fluvial", "hand", "occurrence", "dist_water")
LABEL = {"fluvial": "Fluvial (M1)", "hand": "HAND", "occurrence": "JRC occurrence",
         "dist_water": "Distance to water"}
# dataviz reference categorical slots 1-4 (validated: tables are the relief view)
COLOR = {"fluvial": "#2a78d6", "hand": "#eb6834", "occurrence": "#1baf7a",
         "dist_water": "#eda100"}
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


# ── provenance ─────────────────────────────────────────────────────────

def git(*args) -> str:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def last_commit(path: str) -> tuple[str, str]:
    """(full sha, ISO date) of the last commit that touched path."""
    out = git("log", "-1", "--format=%H %cI", "--", path)
    sha, date = out.split()
    return sha, date


def first_commit(path: str) -> tuple[str, str, str]:
    """(full sha, committer ISO date, author ISO date) of the commit that added path."""
    out = git("log", "--diff-filter=A", "--format=%H %cI %aI", "--", path).split("\n")[-1]
    sha, cdate, adate = out.split()
    return sha, cdate, adate


def src(path: str) -> dict:
    sha, date = last_commit(path)
    return {"source_file": path, "source_commit": sha[:7], "source_commit_date": date}


def write_csv(name: str, rows: list, fields: list | None = None):
    os.makedirs(TABLES, exist_ok=True)
    fields = fields or list(rows[0].keys())
    with open(os.path.join(TABLES, name), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def load(path: str) -> dict:
    with open(os.path.join(ROOT, path)) as fh:
        return json.load(fh)


# ── 1. pre-registration hashes ─────────────────────────────────────────

def prereg_hashes() -> list:
    rows = []
    for res_path, pre in PREREG.items():
        res = load(res_path)
        mods = res.get("modules", {})
        recorded = res["preregistration_sha256"]
        now = hashlib.sha256(open(os.path.join(ROOT, pre), "rb").read()).hexdigest()
        p_sha, p_date, p_adate = first_commit(pre)
        at_commit = hashlib.sha256(
            subprocess.run(["git", "-C", ROOT, "show", f"{p_sha}:{pre}"], capture_output=True,
                           check=True).stdout).hexdigest()
        r_sha, r_date, _ = first_commit(res_path)
        run = datetime.datetime.fromisoformat(res["run_utc"])
        p_dt = datetime.datetime.fromisoformat(p_date)
        p_adt = datetime.datetime.fromisoformat(p_adate)
        rows.append({
            "round": {R1: 1, R2: 2, R3: 3, R4: 4}[res_path],
            "fluvial_in_round": "fluvial" in mods,
            "preregistration": pre, "sha256_recorded_in_result": recorded,
            "sha256_at_preregistration_commit": at_commit, "sha256_file_now": now,
            "all_three_match": recorded == at_commit == now,
            "preregistration_commit": p_sha[:7], "preregistration_author_date": p_adate,
            "preregistration_committer_date": p_date,
            "result_file": res_path, "result_run_utc": res["run_utc"],
            "result_commit": r_sha[:7], "result_commit_date": r_date,
            "author_date_before_run": p_adt < run,
            "committer_date_before_run": p_dt < run,
            "same_commit_as_result": p_sha == r_sha,
        })
    return rows


# ── 2. round results ───────────────────────────────────────────────────

def round1() -> list:
    m = load(R1)["modules"]["fluvial"]
    rows = [{"site": k, "aoi_wide_score": v["score"], "flooded_cells": v["flooded_cells"],
             "dry_cells": v["dry_cells"], **src(R1)} for k, v in m["sites"].items()]
    rows.append({"site": "POOLED (verdict)", "aoi_wide_score": None,
                 "flooded_cells": m["flooded_cells"], "dry_cells": m["dry_cells"],
                 "pooled_auc": m["auc"], "verdict": m["verdict"], **src(R1)})
    return rows


def round2() -> tuple[list, list]:
    m = load(R2)["modules"]["fluvial"]
    tun = [{"weights_low_hand": t["weights"]["low_hand"],
            "weights_river_size": t["weights"]["river_size"], "tuning_mean_auc": t["mean_auc"],
            **{f"auc_{e}": a for e, a in t["per_event"].items()},
            "chosen": t["weights"] == m["tuning"]["chosen"], **src(R2)}
           for t in m["tuning"]["table"]]
    held = []
    for e, v in m["held_out_per_event"].items():
        ev = m["events"][e]
        held.append({"event": e, "date": ev["event"], "split": ev["split"],
                     "reference": ev["reference"]["source"], "flooded_cells": v["flooded_cells"],
                     "dry_cells": v["dry_cells"], "auc": v["auc"], "qualifies": v["qualifies"],
                     **src(R2)})
    held.append({"event": "MEAN over qualifying held-out (verdict)", "auc": m["held_out"]["auc"],
                 "qualifies": m["held_out"]["qualifying_events"],
                 "reference": f"verdict={m['held_out']['verdict']}; bar 0.70; "
                              f"pooled diagnostic {m['pooled_held_out_auc_diagnostic']}",
                 **src(R2)})
    return tun, held


def round4() -> list:
    m = load(R4)["modules"]["fluvial"]
    rows = []
    for e, v in m["held_out_per_event"].items():
        ev = m["events"][e]
        rows.append({"event": e, "date": ev["event"], "reference": ev["reference"]["source"],
                     "flooded_cells": v["flooded_cells"], "dry_cells": v["dry_cells"],
                     "auc": v["auc"], "qualifies": v["qualifies"], **src(R4)})
    rows.append({"event": "MEAN over qualifying test events (verdict)", "auc": m["held_out"]["auc"],
                 "qualifies": m["held_out"]["qualifying_events"],
                 "reference": f"verdict={m['held_out']['verdict']}; bar 0.70; "
                              f"pooled diagnostic {m['pooled_held_out_auc_diagnostic']}; "
                              f"tuning: {m['tuning']['chosen']}", **src(R4)})
    return rows


# ── 3. baselines ───────────────────────────────────────────────────────

def baselines_tables(res: dict) -> dict:
    s = src(BASELINES)
    excl = set(res["excl_r4_test"]["kept"])
    jrc = set(res["jrc_reference_units"])
    per_event, wins = [], []
    for e in res["events"]:
        if not e.get("qualifies"):
            continue
        r = {"event": e["unit"], "date": e["event"], "round_box": e["round"],
             "reference": e["reference_source"], "r4_test_or_alias": e["unit"] not in excl,
             "jrc_circular": e["unit"] in jrc, "flooded_cells": e["flooded_cells"],
             "dry_cells": e["dry_cells"], "block_tiles_990m": e["tiles"]["990m"]}
        for k in SCORES:
            r[f"auc_{k}"] = e["auc"][k]
            r[f"ci_lo_{k}"], r[f"ci_hi_{k}"] = e["ci"]["990m"][k]
        d = e["delta_vs_best"]["fluvial"]
        r.update({"best_baseline": e["best_baseline"], "fluvial_minus_best": d["delta"],
                  "delta_ci_lo_990m": d["ci"]["990m"][0], "delta_ci_hi_990m": d["ci"]["990m"][1],
                  "delta_ci_lo_1980m": d["ci"]["1980m"][0], "delta_ci_hi_1980m": d["ci"]["1980m"][1],
                  "delta_ci_lo_own_range": d["ci"]["own_range"][0],
                  "delta_ci_hi_own_range": d["ci"]["own_range"][1],
                  "clear_win_990m": d["ci"]["990m"][0] > 0,
                  "clear_loss_990m": d["ci"]["990m"][1] < 0, **s})
        per_event.append(r)
        if d["delta"] > 0:
            wins.append({k: r[k] for k in ("event", "best_baseline", "fluvial_minus_best",
                                            "delta_ci_lo_990m", "delta_ci_hi_990m",
                                            "clear_win_990m", "r4_test_or_alias", "jrc_circular")}
                        | {"auc_fluvial": r["auc_fluvial"],
                           "auc_best_baseline": r[f"auc_{e['best_baseline']}"]} | s)
    wins.sort(key=lambda x: -x["fluvial_minus_best"])
    means = []
    names = {"all": "all qualifying (34)", "excl_r4_test": "excl. round-4 test + aliases (22)",
             "excl_jrc_ref": "excl. JRC-circular (29)",
             "excl_r4_test|excl_jrc_ref": "excl. both (17)",
             "mechanism:fluvial": "fluvial-mechanism events",
             "mechanism:fluvial|excl_r4_test": "fluvial-mechanism, excl. round-4 test",
             "mechanism:fluvial|excl_r4_test|excl_jrc_ref": "fluvial-mechanism, excl. both"}
    for g, label in names.items():
        G = res["means"].get(g)
        if not G:
            continue
        for k in SCORES:
            a = G["auc"][k]
            means.append({"group": g, "group_label": label, "events": len(G["events"]),
                          "clusters": G["clusters"], "quantity": f"mean AUC {k}",
                          "value": a["mean"], "ci_lo": a["ci"][0], "ci_hi": a["ci"][1], **s})
        for b in ("hand", "occurrence", "dist_water"):
            d = G["delta"][f"fluvial-{b}"]
            means.append({"group": g, "group_label": label, "events": len(G["events"]),
                          "clusters": G["clusters"], "quantity": f"mean dAUC fluvial-{b}",
                          "value": d["mean"], "ci_lo": d["ci"][0], "ci_hi": d["ci"][1], **s})
    members = [{"group": g, "events": ";".join(sorted(res["means"][g]["events"])), **s}
               for g in names if g in res["means"]]
    st = res["settings"]
    settings = [{"setting": k, "value": json.dumps(st[k]) if isinstance(st[k], dict) else st[k], **s}
                for k in ("block_cells", "block_cells_wide", "reps", "seed", "min_flooded_cells",
                          "min_dry_cells", "dist_cap_m")]
    rep = [{"check": k, "pinned": v["pinned"], "recomputed": v["recomputed"], "match": v["match"], **s}
           for k, v in res["reproduce_round4"].items() if k.startswith("fluvial/")]
    return {"baselines_per_event.csv": per_event, "baselines_fluvial_beats_best.csv": wins,
            "baselines_means.csv": means, "baselines_group_members.csv": members,
            "baselines_settings.csv": settings, "baselines_reproduce_round4_fluvial.csv": rep}


# ── 4. manifest ────────────────────────────────────────────────────────

def ref_kind(source: str) -> str:
    s = source or ""
    for key, kind in (("Copernicus EMS", "EMS"), ("UNOSAT", "UNOSAT"), ("S1_GRD", "S1"),
                      ("JRC/GSW", "JRC (recurrent water)")):
        if key in s:
            return kind
    return "other"


def manifest(res: dict) -> list:
    from experiments.flood_baselines import events as E
    from experiments.flood_core.registry import registry as REG
    from vector.aois import BASELINE_AOIS
    reg = REG.load()
    units = REG.units(reg)
    rows = []

    def unit_info(n):
        u = units.get(n) or {}
        return {"registry_role": u.get("role", "not in registry"),
                "region_cluster": u.get("region_cluster"), "storm_cluster": u.get("storm_cluster"),
                "exposure_level": u.get("exposure_level")}

    def centre(m):
        c = m.get("centre")
        if c is None and m.get("bbox"):     # some round-2 boxes store only the bbox
            w, s_, e_, n = m["bbox"]
            c = [round((s_ + n) / 2, 6), round((w + e_) / 2, 6)]
        return {"centre_lat": c[0], "centre_lon": c[1]} if c else {}

    def bbox_cols(b):
        return dict(zip(("bbox_w", "bbox_s", "bbox_e", "bbox_n"), b)) if b else {}

    r1 = load(R1)["modules"]["fluvial"]["sites"]
    for n, v in r1.items():
        b = BASELINE_AOIS.get(n)
        b = b["bbox"] if isinstance(b, dict) else b
        rows.append({"event": n, "use": "round 1 (AOI-wide scalar; pooled)", "date": "",
                     **centre({"bbox": list(b)}), **bbox_cols(b), "reference_source": "JRC/GSW1_4 occurrence, recurrent 5-80 % (1984-2021)",
                     "reference_kind": "JRC (recurrent water)", "split": "site",
                     "flooded_cells": v["flooded_cells"], "dry_cells": v["dry_cells"],
                     "qualifies": "", "jrc_circular": True, **unit_info(n), "source_file": R1})
    for path, use, key in ((R2, "round 2", "held_out_per_event"), (R4, "round 4", "held_out_per_event")):
        m = load(path)["modules"]["fluvial"]
        evs = m["events"]
        cells = dict(m[key])
        if path == R2:     # tuning events: cells are not in held_out_per_event
            for e in evs:
                cells.setdefault(e, {})
        for e, ev in evs.items():
            c = cells.get(e, {})
            split = ev.get("split") or "test"
            rows.append({"event": e, "use": use, "date": ev["event"],
                         "centre_lat": ev["centre"][0], "centre_lon": ev["centre"][1],
                         **bbox_cols(ev["bbox"]), "reference_source": ev["reference"]["source"],
                         "reference_kind": ref_kind(ev["reference"]["source"]), "split": split,
                         "flooded_cells": c.get("flooded_cells"), "dry_cells": c.get("dry_cells"),
                         "qualifies": c.get("qualifies"), "jrc_circular": False, **unit_info(e),
                         "source_file": path})
    cat = {c["unit"]: c for c in E.catalogue(reg)}
    jrc = set(res["jrc_reference_units"])
    excl = set(res["excl_r4_test"]["kept"])
    for e in res["events"]:
        c = cat[e["unit"]]
        m = c["meta"]
        rows.append({"event": e["unit"], "use": "baselines (exp/flood-baselines)", "date": e["event"],
                     **centre(m), **bbox_cols(m["bbox"]), "reference_source": e["reference_source"],
                     "reference_kind": ref_kind(e["reference_source"]),
                     "split": f"dev (box from {e['round']}" + (f"/{e['split']})" if e["split"] else ")"),
                     "flooded_cells": e["flooded_cells"], "dry_cells": e["dry_cells"],
                     "qualifies": e["qualifies"], "jrc_circular": e["unit"] in jrc,
                     "r4_test_or_alias": (e["unit"] not in excl) if e["qualifies"] else "",
                     **unit_info(e["unit"]), "source_file": BASELINES})
    return rows


# ── 5. figures ─────────────────────────────────────────────────────────

def _style(plt):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": INK2,
                         "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                         "savefig.facecolor": SURFACE, "legend.frameon": False,
                         "svg.hashsalt": "geowatch-m1"})     # stable SVG ids across rebuilds


def fig_a(res: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _style(plt)
    excl, jrc = set(res["excl_r4_test"]["kept"]), set(res["jrc_reference_units"])
    ev = sorted([e for e in res["events"] if e.get("qualifies")], key=lambda e: e["auc"]["fluvial"])
    n = len(ev)
    fig, ax = plt.subplots(figsize=(7.2, 0.26 * n * 1.6 + 1.6))
    h = 0.19
    for i, k in enumerate(SCORES):
        y = np.arange(n) * 1.0 + (1.5 - i) * h
        x = [e["auc"][k] for e in ev]
        lo = [e["auc"][k] - e["ci"]["990m"][k][0] for e in ev]
        hi = [e["ci"]["990m"][k][1] - e["auc"][k] for e in ev]
        ax.errorbar(x, y, xerr=[lo, hi], fmt="o", ms=3.2 if k != "fluvial" else 4.2,
                    color=COLOR[k], ecolor=COLOR[k], elinewidth=1.0, capsize=0,
                    label=LABEL[k], zorder=3 if k == "fluvial" else 2,
                    markeredgecolor=SURFACE, markeredgewidth=0.6)
    labels = []
    for e in ev:
        t = e["unit"] + (" †" if e["unit"] not in excl else "") + (" ‡" if e["unit"] in jrc else "")
        if e["delta_vs_best"]["fluvial"]["ci"]["990m"][0] > 0:
            t += "  ★"
        labels.append(t)
    ax.set_yticks(np.arange(n))
    ax.set_yticklabels(labels, fontsize=7.5)
    for yv in np.arange(n) + 0.5:
        ax.axhline(yv, color=GRID, lw=0.5, zorder=0)
    ax.axvline(0.5, color=INK2, lw=0.8, ls=(0, (2, 2)), zorder=1)
    ax.axvline(0.7, color=INK2, lw=0.8, ls=(0, (6, 2)), zorder=1)
    ax.text(0.5, n - 0.3, "chance", fontsize=7, color=INK2, ha="center", va="bottom")
    ax.text(0.7, n - 0.3, "pass bar 0.70", fontsize=7, color=INK2, ha="center", va="bottom")
    ax.set_xlim(0.1, 1.02)
    ax.set_ylim(-0.6, n + 0.4)
    ax.set_xlabel("Within-event ROC AUC (30 m cells), 95% CI: paired 990 m block bootstrap, 1,000 reps")
    ax.legend(loc="lower right", ncol=1, fontsize=8, bbox_to_anchor=(1.0, 0.0))
    ax.set_title("Fluvial (M1) vs three baselines, 34 qualifying dev events", loc="left",
                 fontsize=10.5, color=INK)
    fig.text(0.01, 0.005, "Sorted by fluvial AUC. ★ fluvial − best baseline CI above 0. "
             "† round-4 test event or alias. ‡ reference is JRC occurrence (circular for the JRC baseline).",
             fontsize=6.8, color=INK2)
    fig.tight_layout(rect=(0, 0.015, 1, 1))
    for ext in ("png", "svg"):
        fig.savefig(os.path.join(FIGS, f"fig_a_per_event_auc.{ext}"), dpi=200,
                    metadata={"Date": None} if ext == "svg" else None)
    plt.close(fig)


def cell_arrays(name: str):
    """Per-cell scores, flooded, ok mask for one unit, exactly as score.score_unit."""
    from experiments.flood_baselines import build as BUILD, events as E, score as S
    from experiments.flood_core.registry import registry as REG
    reg = REG.load()
    entry = next(c for c in E.catalogue(reg) if c["unit"] == name)
    built = BUILD.load(name)
    ref = E.reference(entry)
    shape = ref["flooded"].shape
    sc = S.all_scores(built["arrays"], shape, S.round4_chosen())
    sc, flooded, valid = S.evaluation_grid(sc, ref["flooded"], ref["valid"], ref["block"])
    present = [k for k in S.PRIMARY if sc.get(k) is not None and np.isfinite(sc[k]).any()]
    ok = valid.copy()
    for k in present:
        ok &= np.isfinite(sc[k])
    return {"scores": sc, "flooded": flooded, "ok": ok, "valid": valid,
            "hand_m": built["arrays"].get("layer_hand_m"), "block": ref["block"]}


def roc(score, flooded, ok):
    from sklearn.metrics import roc_curve
    y = flooded[ok].astype(int)
    fpr, tpr, _ = roc_curve(y, score[ok])
    return fpr, tpr


def fig_b(res: dict) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from experiments.flood_validation.harness import auc as harness_auc
    _style(plt)
    byname = {e["unit"]: e for e in res["events"]}
    fig, axes = plt.subplots(1, len(WINS), figsize=(12.5, 3.6), sharey=True)
    checks = []
    for ax, name in zip(axes, WINS):
        a = cell_arrays(name)
        e = byname[name]
        for k in SCORES:
            s = a["scores"][k]
            f, ok = a["flooded"], a["ok"]
            re = harness_auc(s[ok], f[ok], ~f[ok])
            checks.append({"event": name, "score": k, "auc_stored": e["auc"][k],
                           "auc_recomputed": round(re, 4), "match": round(re, 4) == e["auc"][k],
                           "flooded_cells": int((f & ok).sum()), "dry_cells": int((~f & ok).sum()),
                           **src(BASELINES)})
            fpr, tpr = roc(s, f, ok)
            ax.plot(fpr, tpr, color=COLOR[k], lw=2.0 if k == "fluvial" else 1.3,
                    label=f"{LABEL[k]} {e['auc'][k]:.3f}", zorder=3 if k == "fluvial" else 2)
        ax.plot([0, 1], [0, 1], color=INK2, lw=0.7, ls=(0, (2, 2)))
        d = e["delta_vs_best"]["fluvial"]
        ax.set_title(f"{name}\nfluvial − {LABEL[e['best_baseline']]}\n{d['delta']:+.3f} "
                     f"[{d['ci']['990m'][0]:+.3f}, {d['ci']['990m'][1]:+.3f}]", fontsize=8.2, loc="left")
        ax.set_xlabel("False positive rate (dry cells)", fontsize=7.5)
        ax.legend(loc="lower right", fontsize=6.4, handlelength=1.2)
        ax.set_aspect("equal")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("True positive rate (flooded cells)", fontsize=7.5)
    fig.suptitle("ROC curves: the five events where fluvial beats the best baseline "
                 "(paired 990 m block 95% CI above 0); legend = AUC", x=0.01, ha="left",
                 fontsize=10, color=INK)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(os.path.join(FIGS, f"fig_b_roc_five_wins.{ext}"), dpi=200,
                    metadata={"Date": None} if ext == "svg" else None)
    plt.close(fig)
    return checks


def fig_c(res: dict) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    _style(plt)
    byname = {e["unit"]: e for e in res["events"]}
    fig, axes = plt.subplots(len(MAP_EVENTS), 3, figsize=(9.6, 3.3 * len(MAP_EVENTS)))
    rows = []
    for r, name in enumerate(MAP_EVENTS):
        a = cell_arrays(name)
        e = byname[name]
        ok, f = a["ok"], a["flooded"]
        flu = np.where(ok, a["scores"]["fluvial"], np.nan)
        hand = np.where(ok, np.asarray(a["hand_m"], float), np.nan)
        obs = np.full(f.shape, np.nan)
        obs[ok & ~f], obs[ok & f] = 0, 1
        ax = axes[r, 0]
        im = ax.imshow(flu, cmap="Blues", vmin=0, vmax=1, interpolation="nearest")
        ax.set_title(f"{name}: fluvial score (AUC {e['auc']['fluvial']:.3f})", fontsize=8.5, loc="left")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02).ax.tick_params(labelsize=7)
        ax = axes[r, 1]
        im = ax.imshow(hand, cmap="Oranges_r", vmin=0, vmax=30, interpolation="nearest")
        ax.set_title(f"HAND, m (−HAND AUC {e['auc']['hand']:.3f})", fontsize=8.5, loc="left")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02).ax.tick_params(labelsize=7)
        ax = axes[r, 2]
        im = ax.imshow(obs, cmap=ListedColormap(["#e4e3df", "#184f95"]), vmin=-0.5, vmax=1.5,
                       interpolation="nearest")
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02, ticks=[0, 1])
        cb.ax.set_yticklabels(["dry", "flooded"], fontsize=7)
        ref = e["reference_source"]
        ax.set_title(f"observed: {int((f & ok).sum())} flooded / {int((~f & ok).sum())} dry",
                     fontsize=8.5, loc="left")
        import textwrap
        ax.text(0.0, -0.04, "\n".join(textwrap.wrap(ref, 58)), transform=ax.transAxes,
                fontsize=6.3, color=INK2, va="top")
        for ax in axes[r]:
            ax.set_xticks([])
            ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_visible(False)
        rows.append({"event": name, "auc_fluvial": e["auc"]["fluvial"], "auc_hand": e["auc"]["hand"],
                     "flooded_cells": int((f & ok).sum()), "dry_cells": int((~f & ok).sum()),
                     "reference": ref, "pixel_m": 30, **src(BASELINES)})
    fig.text(0.01, 0.005, "30 m cells; white = excluded (JRC permanent water or outside the "
             "reference's valid area). Dark blue = flooded in the reference, grey = dry.\n"
             "Top: best round-2 held-out event (Hanoi). Bottom: worst round-4 test event (Assam), "
             "where HAND is low across the whole box and fluvial's ranking disagrees with the Sentinel-1 reference.",
             fontsize=6.8, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    for ext in ("png", "svg"):
        fig.savefig(os.path.join(FIGS, f"fig_c_maps_hanoi_assam.{ext}"), dpi=200,
                    metadata={"Date": None} if ext == "svg" else None)
    plt.close(fig)
    return rows


def main():
    os.makedirs(TABLES, exist_ok=True)
    os.makedirs(FIGS, exist_ok=True)
    res = load(BASELINES)
    write_csv("preregistration_hashes.csv", prereg_hashes())
    write_csv("round1_fluvial.csv", round1(),
              ["site", "aoi_wide_score", "flooded_cells", "dry_cells", "pooled_auc", "verdict",
               "source_file", "source_commit", "source_commit_date"])
    tun, held = round2()
    write_csv("round2_fluvial_tuning.csv", tun)
    write_csv("round2_fluvial_heldout.csv", held,
              ["event", "date", "split", "reference", "flooded_cells", "dry_cells", "auc",
               "qualifies", "source_file", "source_commit", "source_commit_date"])
    write_csv("round4_fluvial_test.csv", round4(),
              ["event", "date", "reference", "flooded_cells", "dry_cells", "auc", "qualifies",
               "source_file", "source_commit", "source_commit_date"])
    for name, rows in baselines_tables(res).items():
        write_csv(name, rows)
    man = manifest(res)
    fields = ["event", "use", "date", "centre_lat", "centre_lon", "bbox_w", "bbox_s", "bbox_e",
              "bbox_n", "reference_kind", "reference_source", "split", "registry_role",
              "exposure_level", "region_cluster", "storm_cluster", "flooded_cells", "dry_cells",
              "qualifies", "jrc_circular", "r4_test_or_alias", "source_file"]
    with open(os.path.join(HERE, "data_manifest.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in man:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    fig_a(res)
    write_csv("figure_auc_check.csv", fig_b(res))
    write_csv("figure_c_maps.csv", fig_c(res))
    print("wrote", TABLES, FIGS, os.path.join(HERE, "data_manifest.csv"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
