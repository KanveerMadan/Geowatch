"""Markdown tables from results/baselines.json (no computation beyond
formatting and counting).

    python -m experiments.flood_baselines.tables   # writes results/tables.md
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results", "baselines.json")
OUT = os.path.join(HERE, "results", "tables.md")
BASE = ("hand", "occurrence", "dist_water")
MODS = ("fluvial", "pluvial", "waterlogging", "flash_flood")
COLS = BASE + MODS
SHORT = {"hand": "HAND", "occurrence": "JRC occ.", "dist_water": "dist. water",
         "fluvial": "fluvial", "pluvial": "pluvial", "waterlogging": "waterlog.",
         "flash_flood": "flash"}


def f3(x):
    return "–" if x is None else f"{x:.3f}"


def cell(e, k, block="990m"):
    if k not in e.get("auc", {}):
        return "–"
    lo, hi = e["ci"][block].get(k, [None, None])
    return f"{e['auc'][k]:.3f} [{f3(lo)}, {f3(hi)}]"


def per_event(events, excl, jrc=frozenset()):
    rows = ["| event | round | mechanism | flooded / dry cells | " + " | ".join(SHORT[c] for c in COLS)
            + " | best baseline |",
            "|" + "---|" * (5 + len(COLS))]
    for e in events:
        if not e.get("qualifies"):
            continue
        mark = ("" if e["unit"] in excl else " †") + (" ‡" if e["unit"] in jrc else "")
        rows.append(f"| {e['unit']}{mark} | {e['round']}{'/' + e['split'] if e['split'] else ''} | "
                    f"{', '.join(e['mechanism'])} | {e['flooded_cells']} / {e['dry_cells']} | "
                    + " | ".join(cell(e, c) for c in COLS) + f" | {SHORT[e['best_baseline']]} |")
    return "\n".join(rows)


def means(res, group):
    g = res["means"].get(group)
    if not g:
        return f"(no events in {group})"
    rows = [f"**{group}**: {len(g['events'])} events in {g['clusters']} clusters", "",
            "| score | mean AUC | 95% CI (cluster × block bootstrap) | events |", "|---|---|---|---|"]
    for k in COLS + ("occurrence_pre", "dist_osm_only", "pluvial_r4chosen",
                     "waterlogging_r4chosen", "flash_flood_r4chosen"):
        a = g["auc"].get(k)
        if a:
            rows.append(f"| {k} | {a['mean']:.3f} | [{f3(a['ci'][0])}, {f3(a['ci'][1])}] | {a['n_events']} |")
    rows += ["", "| module − baseline | mean ΔAUC | 95% CI | events |", "|---|---|---|---|"]
    for k, d in g["delta"].items():
        rows.append(f"| {k} | {d['mean']:+.3f} | [{f3(d['ci'][0])}, {f3(d['ci'][1])}] | {d['n_events']} |")
    return "\n".join(rows)


def beats(events, excl_only, excl, drop=frozenset()):
    rows = ["| module | events scored | beats best baseline (point) | … with 95% CI above 0 | "
            "largest margin (event) | median margin |", "|---|---|---|---|---|---|"]
    detail = []
    for m in MODS:
        ev = [e for e in events if e.get("qualifies") and m in e.get("delta_vs_best", {})
              and (not excl_only or e["unit"] in excl) and e["unit"] not in drop]
        if not ev:
            continue
        d = [(e["delta_vs_best"][m]["delta"], e["unit"], e["delta_vs_best"][m]["ci"]["990m"],
              e["best_baseline"]) for e in ev]
        pos = [x for x in d if x[0] > 0]
        sig = [x for x in d if x[2][0] is not None and x[2][0] > 0]
        top = max(d)
        rows.append(f"| {m} | {len(d)} | {len(pos)} | {len(sig)} | {top[0]:+.3f} ({top[1]}) | "
                    f"{np.median([x[0] for x in d]):+.3f} |")
        for x in sorted(pos, reverse=True):
            detail.append(f"- {m} @ {x[1]}: {x[0]:+.3f} vs {SHORT[x[3]]} "
                          f"[{f3(x[2][0])}, {f3(x[2][1])}]")
    return "\n".join(rows), "\n".join(detail) or "- none"


def block_sensitivity(events):
    rows = ["| block | median tiles per event | events where a module's Δ vs best baseline has CI above 0 | "
            "median CI width (module AUCs) |", "|---|---|---|---|"]
    for b in ("990m", "1980m", "own_range"):
        ev = [e for e in events if e.get("qualifies")]
        tiles = [e["tiles"][b] for e in ev]
        sig = sum(1 for e in ev for m in MODS if m in e.get("delta_vs_best", {})
                  and (e["delta_vs_best"][m]["ci"][b][0] or -1) > 0)
        widths = [e["ci"][b][m][1] - e["ci"][b][m][0] for e in ev for m in MODS
                  if m in e.get("ci", {}).get(b, {}) and e["ci"][b][m][0] is not None]
        rows.append(f"| {b} | {int(np.median(tiles))} | {sig} | {np.median(widths):.3f} |")
    return "\n".join(rows)


def ranges(events):
    q = [e for e in events if e.get("qualifies")]
    r = [e["indicator_range_m"] for e in q if e.get("indicator_range_m") is not None]
    return (f"{len(r)} of {len(q)} qualifying events have a measurable range; median {np.median(r):.0f} m, "
            f"quartiles {np.percentile(r, 25):.0f}–{np.percentile(r, 75):.0f} m, max {max(r):.0f} m; "
            f"{sum(x <= 990 for x in r)} of {len(r)} at or below 990 m.")


def gaps(events):
    out = []
    for e in events:
        if not e.get("qualifies"):
            continue
        bits = []
        if e.get("missing"):
            bits.append("missing: " + ", ".join(e["missing"]))
        if e.get("osm_water_complete") is False:
            bits.append("OSM water incomplete: " + json.dumps(e.get("osm_counts")))
        if e.get("raster_errors"):
            bits.append("raster errors: " + ", ".join(e["raster_errors"]))
        if bits:
            out.append(f"- {e['unit']}: " + "; ".join(bits))
    return "\n".join(out) or "- none"


def main():
    res = json.load(open(RES))
    ev = res["events"]
    excl = set(res["excl_r4_test"]["kept"])
    jrc = set(res.get("jrc_reference_units", []))
    rep = res["reproduce_round4"]
    parts = [
        "## Per event (AUC [blocked 95% CI], 990 m blocks); † = round-4 test event or its alias; "
        "‡ = reference is JRC GSW occurrence (occurrence baseline circular)",
        per_event(ev, excl, jrc),
        "## Means", means(res, "all"), means(res, "excl_r4_test"), means(res, "excl_jrc_ref"),
        means(res, "excl_r4_test|excl_jrc_ref"),
    ]
    for m in MODS + ("coastal",):
        parts += [means(res, f"mechanism:{m}"), means(res, f"mechanism:{m}|excl_r4_test"),
                  means(res, f"mechanism:{m}|excl_r4_test|excl_jrc_ref")]
    t_all, d_all = beats(ev, False, excl)
    t_ex, d_ex = beats(ev, True, excl)
    t_cl, d_cl = beats(ev, True, excl, jrc)
    parts += ["## Does a module beat the best baseline on an event? (all qualifying)", t_all, d_all,
              "## … excluding round-4 test events and their aliases", t_ex, d_ex,
              "## … excluding round-4 test events, their aliases and JRC-reference events", t_cl, d_cl,
              "## Block-size sensitivity", block_sensitivity(ev),
              "## Measured correlation range of the reference flood indicator", ranges(ev),
              "## Input gaps", gaps(ev),
              "## Reproduction check (round 4's cached test arrays and chosen parameters)",
              f"{sum(v['match'] for v in rep.values())} of {len(rep)} pinned per-event AUCs reproduced exactly."]
    with open(OUT, "w") as fh:
        fh.write("\n\n".join(parts) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
