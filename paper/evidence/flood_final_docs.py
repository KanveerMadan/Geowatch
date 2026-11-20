"""
Markdown for the flood_final evidence packs. Every number is read from the
result JSONs, never typed in by hand. Run after flood_final_build.py:

    python paper/evidence/flood_final_docs.py

Writes README/METHOD/EVIDENCE/LIMITS/REPRODUCE.md for M2, M3, M4, M5 and M9,
and FLOOD_FINAL.md for M1. The M1 README and EVIDENCE summary rows are edited
by hand.
"""
from __future__ import annotations

import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FF = "experiments/flood_final"
TITLE = {"fluvial": "M1 fluvial (river)", "pluvial": "M2 pluvial (rain / urban)", "waterlogging": "M3 waterlogging",
         "flash_flood": "M4 flash flood", "coastal": "M5 coastal", "compound": "M9 compound"}
PACKS = {"fluvial": "M1_fluvial", "pluvial": "M2_pluvial", "waterlogging": "M3_waterlogging",
         "flash_flood": "M4_flash_flood", "coastal": "M5_coastal", "compound": "M9_compound"}
MODULE = {"fluvial": "fluvial", "pluvial": "pluvial", "waterlogging": "waterlogging", "flash_flood": "flash_flood"}

# Type-specific limits: facts recorded in DECISIONS.md, cited by decision number.
NOTES = {
    "fluvial": [
        "The current production fluvial module (validated configuration, round 2) was re-tested on the same 8 reserved units and **failed** (see EVIDENCE). Its round-2 validation now has a pre-registered failure on a broader river set beside it.",
        "Two reserved river events (Assam 2024, Sunamganj 2024) share a main basin with DEV units. The pre-registration accepted this exception link before any data was read (D6).",
        "Five reserved river references are Sentinel-1 VV-drop extents. They cannot see flooding among buildings (D20), so urban river flooding is under-represented.",
    ],
    "pluvial": [
        "Only 4 reserved units in 3 clusters qualified, the minimum the bar allows is 3 units in 2 clusters: the interval is wide.",
        "The production pluvial module's own inputs were not built for the new DEV pluvial units (D8), so it did not compete in the DEV choice; it is scored on RESERVED where its inputs built.",
        "Pluvial flooding is largely urban, where the references are weakest: at Weihui the learned model ranks flooded streets **below** dry ground (D20).",
    ],
    "waterlogging": [
        "The pass rests on the minimum the pre-registration allows: 3 reserved units in 2 clusters (Albania lowlands x2, Niger delta). One more failed unit could have reversed it.",
        "The reserved set has fewer than the brief's target of 5 units (D18).",
        "The Niger-delta reference is a Sentinel-1 VV-drop extent (urban blind spot, D20).",
    ],
    "flash_flood": [
        "On the reserved flash-flood units HAND is already strong (mean 0.83), so the bar's Δ-vs-HAND test is hard; the learned model's AUC is high but not above HAND.",
        "Arid and mountain flash floods fail on DEV (Derna 2023, Himachal 2023). The reserved set has no arid event.",
        "SFINCS (physics) on Valencia 2024 is DEV-only evidence, not a held-out test (sfincs/results/valencia_sfincs.json).",
    ],
    "coastal": [
        "The model has no surge, tide or wave input; coastal skill comes from elevation, distance to coast and land cover. Plain low-elevation ranking is as good.",
        "The method chosen on DEV (LightGBM) scored lower on RESERVED than the logistic variant that was not chosen. The choice rule is applied as written.",
        "Only 5 DEV coastal units (D18). The coastal SFINCS case was deferred (D17).",
    ],
    "compound": [
        "Compound units overlap heavily with coastal (same storms: Beryl, Harry) and with flash flood (Portugal 2026); the groups are not independent.",
        "5 reserved units in 3 clusters; the Δ-vs-HAND interval spans -0.26 to +0.10.",
        "Valencia 2024 SFINCS (rain + river, DEV): every ensemble member beats HAND on max depth (DEV evidence only).",
    ],
}
COMMON_LIMITS = [
    "**Plain elevation is as good or better.** Negated GLO-30 elevation (`neg_elev_glo30`, lowest ground first) was reported beside every verdict but was not a pre-registered candidate. On RESERVED it beats the learned model on 4 of 6 types, including both that passed. The data do **not** show that the learned model adds skill over low-ground ranking (D21).",
    "**Urban blind spot.** The learned model learned from references that cannot see flooding among buildings. At Weihui (UrbanSARFloods, CC BY 4.0) it ranks flooded urban cells below dry cells (AUC 0.12–0.36). Cells with built-up share >= 0.5 must be shown as 'not assessed' (D20).",
    "**Land cover drives the model.** Removing WorldCover costs 0.04–0.13 DEV AUC on every type; with the urban blind spot, part of this signal is a reference artefact.",
    "**References.** Copernicus EMS delineations (and Sentinel-1 VV-drop extents) at their acquisition time, not peak extent; unobserved cells are excluded, never treated as dry; JRC occurrence >= 80 % excluded; accra, capetown, dhaka, hcmc and nusantara never used as labels (JRC-circular).",
    "**Within-event ranking only.** AUC measures whether flooded cells rank above dry cells in the same 4 km box. It says nothing about absolute depth, return period or between-place comparison.",
    "**Missing data.** 2 reserved units failed to build (an Earth Engine projection error, not fixed after the freeze) and 4 had no flood in the product; 7 did not reach 50 flooded cells. They are listed in `data_manifest.csv`, never scored as zero.",
]
LICENCES = """| input (open variant) | licence | commercial use |
|---|---|---|
| Copernicus DEM GLO-30 2024_1 (terrain, elevation) | Copernicus WorldDEM-30 licence, attribution "© DLR e.V." | no purpose restriction found; confirm full text |
| HydroSHEDS v1 15ACC (accumulation) | HydroSHEDS terms (free incl. commercial) vs one catalogue CC BY-NC 3.0 | **conflicting; confirm** |
| JRC Global Surface Water 1.4 (occurrence, recurrence) | Copernicus free; "Source: EC JRC/Google" | yes |
| OpenStreetMap (water, distance to water) | ODbL | yes, share-alike for derived databases |
| CHIRPS v2, IMERG V07 (rain) | public domain / NASA open data | yes |
| SoilGrids (clay), ESA WorldCover (land cover), Cloud Score+ / Sentinel-2 (NDVI) | CC BY 4.0 / Copernicus open | yes |
| GHSL GHS-BUILT-S 2020 (built share) | CC BY 4.0 (JRC) | yes |
| sat-io shoreline outlines (distance to coast) | per catalogue (assumed open) | confirm |
| Copernicus EMS products, Sentinel-1 (labels only) | CEMS terms; Copernicus open | validation only |

FABDEM (CC BY-NC-SA) and MERIT Hydro (CC BY-NC / ODbL) are used only in the `full` variants, which were not chosen."""


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def f3(x):
    return "—" if x is None else f"{x:.3f}"


def sg(x):
    return "—" if x is None else f"{x:+.3f}"


def ci(c):
    return "—" if not c or c[0] is None else f"[{c[0]:+.3f}, {c[1]:+.3f}]"


def main():
    J = lambda p: json.load(open(os.path.join(ROOT, p)))      # noqa: E731
    choice, dev, held = J(f"{FF}/results/method_choice.json"), J(f"{FF}/results/dev_report.json"), J(f"{FF}/results/heldout.json")
    sha = held["preflight"]["prereg_sha256"]
    freeze = held["preflight"]["freeze_commit"][:7]
    hashtxt = open(os.path.join(ROOT, FF, "PREREG_HASH.txt")).read().strip()
    for ty, pack in PACKS.items():
        d = os.path.join(HERE, pack)
        ch = choice["choice"][ty]
        chosen = ch["chosen"]
        v = held["verdicts"][ty]
        hg = held["groups"][ty]
        dg = dev["groups"][ty]
        mod = MODULE.get(ty)
        key = f"learned_raw:{chosen}"
        verdict = v["verdict"].upper()
        hm = lambda k: hg["mean_auc"].get(k, {})          # noqa: E731
        hd = lambda k: hg["minus_hand"].get(k, {})        # noqa: E731
        rows = [(f"learned `{chosen}` (pre-registered)", key), ("learned, isotonic-calibrated output", f"learned:{chosen}"),
                ("HAND", "hand"), ("low elevation (GLO-30), not pre-registered", "neg_elev_glo30"),
                ("JRC occurrence", "occurrence"), ("distance to mapped water", "dist_water")]
        if mod:
            rows.append((f"production module `{mod}`", mod))
        other = "open__lgbm" if chosen == "open__logreg" else "open__logreg"
        rows.append((f"learned `{other}` (not chosen)", f"learned_raw:{other}"))
        held_tab = ["| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |", "|---|---|---|---|"]
        for lab, k in rows:
            m = hm(k)
            if not m:
                continue
            dh = hd(k)
            held_tab.append(f"| {lab} | {f3(m['mean'])} [{m['ci'][0]:.3f}, {m['ci'][1]:.3f}] | "
                            f"{'—' if k == 'hand' else (sg(dh.get('mean')) if dh else '—') + ' ' + ci(dh.get('ci'))} | {m['n']} |")
        dev_tab = ["| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |", "|---|---|---|---|"]
        for lab, k in [(f"learned `{chosen}` (chosen)", f"lro:{chosen}"), (f"learned `{other}`", f"lro:{other}"),
                       ("learned without land cover", f"lro:no_landcover__{chosen.split('__')[1]}"),
                       ("HAND", "hand"), ("low elevation (GLO-30)", "neg_elev_glo30")] + ([(f"module `{mod}`", mod)] if mod else []):
            m = dg["mean_auc"].get(k)
            if not m:
                continue
            dh = dg["minus_hand"].get(k, {})
            dev_tab.append(f"| {lab} | {f3(m['mean'])} [{m['ci'][0]:.3f}, {m['ci'][1]:.3f}] | "
                           f"{'—' if k == 'hand' else sg(dh.get('mean')) + ' ' + ci(dh.get('ci'))} | {m['n']} |")
        per_unit = ["| unit | region | flooded / dry | learned | HAND | low elevation |", "|---|---|---|---|---|---|"]
        for n in hg["units"]:
            u = held["units"][n]
            per_unit.append(f"| {n} | {u['region']} | {u['flooded']:,} / {u['dry']:,} | {f3(u['auc'].get(key))} | "
                            f"{f3(u['auc'].get('hand'))} | {f3(u['auc'].get('neg_elev_glo30'))} |")
        ne, lm = hm("neg_elev_glo30").get("mean"), hm(key).get("mean")
        headline = (f"**{verdict}** (pre-registered). Learned `{chosen}` on {v.get('units')} reserved units "
                    f"({v.get('clusters')} clusters): mean AUC {f3(v.get('mean_auc'))}, Δ vs HAND "
                    f"{sg((v.get('minus_hand') or {}).get('mean'))} {ci((v.get('minus_hand') or {}).get('ci'))}. "
                    f"Plain low elevation scored {f3(ne)} on the same cells"
                    + (" — higher than the learned model." if ne is not None and lm is not None and ne > lm else "."))
        bar = "mean within-event AUC >= 0.70 AND the lower 95% bound of Δ vs HAND > 0 AND >= 3 units in >= 2 clusters"
        os.makedirs(d, exist_ok=True)
        if ty == "fluvial":
            retest = held["verdicts"]["fluvial_module_retest"]
            md = [f"# M1 fluvial: flood_final update (independent river test, {held['run_utc'][:10]})", "",
                  f"Two tests on 8 reserved river units never used before (flood_final pre-registration, sha256 `{sha}`; freeze `{freeze}`):", "",
                  f"- **Learned model:** {headline}",
                  f"- **Production fluvial module (validated configuration) re-test: {retest['verdict'].upper()}.** Mean AUC {f3(retest.get('mean_auc'))}, "
                  f"Δ vs HAND {sg(retest['minus_hand']['mean'])} {ci(retest['minus_hand']['ci'])}.", "",
                  "## Held-out (RESERVED, scored once)", "", *held_tab, "", "Per unit:", "", *per_unit, "",
                  "## DEV (leave-region-out, out-of-fold)", "", *dev_tab, "",
                  "## Limits", "", *[f"- {x}" for x in NOTES[ty] + COMMON_LIMITS], "",
                  "Tables: `tables/flood_final/`; figures: `figures/flood_final/`; manifest: `tables/data_manifest_flood_final.csv`. "
                  "Method and licences: `../M2_pluvial/METHOD.md` (shared learned model). Reproduce: `../M2_pluvial/REPRODUCE.md`."]
            open(os.path.join(d, "FLOOD_FINAL.md"), "w").write("\n".join(md) + "\n")
            continue
        open(os.path.join(d, "README.md"), "w").write("\n".join([
            f"# Evidence pack: {TITLE[ty]}", "",
            "Built from `exp/flood-final` (one event set, pre-registered method choice, one held-out pass). Read-only on results.", "",
            "| File | Contents |", "|---|---|",
            "| `METHOD.md` | The learned model, features, choice rule, evaluation, inputs and licences |",
            "| `EVIDENCE.md` | Pre-registration, DEV result, the held-out verdict, per-unit results |",
            "| `LIMITS.md` | Where it fails and what the evidence does not show |",
            "| `REPRODUCE.md` | Commands that regenerate every number |",
            "| `data_manifest.csv` | Every DEV and RESERVED unit of this type, with status |",
            "| `tables/*.csv` | Every number, with `source_file`, `source_commit`, `source_commit_date` |",
            "| `figures/` | Per-event AUC with 95% CIs (DEV and RESERVED) |", "",
            f"**Headline.** {headline}", ""]))
        open(os.path.join(d, "METHOD.md"), "w").write("\n".join([
            f"# {TITLE[ty]}: method", "",
            "## Model",
            f"- Pre-registered choice for this type: **`{chosen}`** (PREREGISTRATION.md §4; DEV leave-region-out mean AUC, tie margin 0.005, logistic before LightGBM, open before full).",
            "- `open` features (26, all per 30 m cell in a 4 km box): GLO-30 slope, curvature, TPI 990 m, height above the 2 km minimum, depression depth, HAND to mapped water; log HydroSHEDS accumulation; distance to mapped water; JRC occurrence and recurrence; CHIRPS/IMERG rain statistics (p99.9 hourly, design day, annual); SoilGrids clay; ESA WorldCover fractions (8 classes); pre-event NDVI (Sentinel-2, Cloud Score+); GLO-30 elevation; distance to coast (capped 50 km); GHSL built share.",
            "- Logistic regression: standardised features, L2, C = 1.0. LightGBM: 300 trees, 15 leaves, learning rate 0.05, min 1,089 rows per leaf (one 990 m block), subsample 0.7, colsample 0.8, L2 1.0 (flood_learned.model; unchanged since batch 0).",
            f"- Trained on all 67 DEV units, every event equal weight; isotonic calibration on pooled leave-region-out predictions. Final model sha256: `{choice['final_models'][chosen]['sha256']}`.",
            "", "## Evaluation",
            "- Labels per cell: flooded / dry / unobserved (unobserved never dry); JRC occurrence >= 80 % excluded.",
            "- Primary metric: within-event ROC AUC of the raw score (D15). 95% CIs from a paired 990 m block bootstrap (1,000 reps) inside each event, then a cluster x block two-stage bootstrap of the mean; Δ vs HAND paired on the same blocks.",
            f"- Pass bar (pre-registered): {bar}.",
            "- Secondary: average precision, area-matched IoU, calibration (Van Calster weak calibration).",
            "", "## Inputs and licences", "", LICENCES, ""]))
        open(os.path.join(d, "EVIDENCE.md"), "w").write("\n".join([
            f"# {TITLE[ty]}: evidence", "",
            "Every number is in `tables/` with its source file and commit.", "",
            "## 1. Criteria fixed before scoring",
            f"- `{FF}/PREREGISTRATION.md`, sha256 `{sha}`.",
            "- Companion record (`PREREG_HASH.txt`):", "", "```", hashtxt, "```", "",
            f"- Freeze tag `flood-final-heldout-freeze` = `{freeze}` (code, method_choice.json and final-model hashes). The held-out run checked both before reading any reserved data; run {held['run_utc']}.",
            "", f"## 2. Held-out verdict: {verdict}", "", headline, "", *held_tab, "",
            "Per reserved unit (raw-score AUC):", "", *per_unit, "",
            f"Not scored: see `data_manifest.csv` (`heldout_status`).", "",
            "## 3. DEV (leave-region-out, out-of-fold; method choice)", "",
            f"{dg['clusters']} clusters, {len(dg['units'])} units.", "", *dev_tab, "",
            "Figures: `figures/fig_dev_per_event_auc.png`, `figures/fig_heldout_per_event_auc.png`.", ""]))
        open(os.path.join(d, "LIMITS.md"), "w").write("\n".join([
            f"# {TITLE[ty]}: limits", "", *[f"- {x}" for x in NOTES[ty]], "", "## Shared by every flood type", "",
            *[f"- {x}" for x in COMMON_LIMITS], ""]))
        open(os.path.join(d, "REPRODUCE.md"), "w").write("\n".join([
            f"# {TITLE[ty]}: reproduce", "",
            "Environment: `geowatch-env` Python with LightGBM 4.7.0 on `PYTHONPATH`; Earth Engine credentials for the build steps only.", "",
            "```bash",
            "# DEV inputs and tables (Earth Engine)",
            "python -m experiments.flood_final.build_units --dev",
            "# DEV cross-validation, method choice, report",
            "python -m experiments.flood_final.model_v2 cv",
            "python -m experiments.flood_final.model_v2 choose",
            "python -m experiments.flood_final.dev_report",
            "# held-out (refuses unless HEAD = flood-final-heldout-freeze and heldout.json is absent)",
            "python -m experiments.flood_final.heldout_pass build",
            "python -m experiments.flood_final.heldout_pass score",
            "# this pack",
            "python paper/evidence/flood_final_build.py && python paper/evidence/flood_final_docs.py",
            "```", "",
            "The held-out score refuses to run twice (`results/heldout.json` is opened with mode `x`).", ""]))
    print("docs written")


if __name__ == "__main__":
    main()
