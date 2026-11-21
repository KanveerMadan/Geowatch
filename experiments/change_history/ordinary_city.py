"""Reproduce the registered ordinary city-month study with independent water endpoints."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import box
from shapely.ops import transform

from vector import change_observations as provider
from vector.change_detection import detect_cell

HERE = Path(__file__).resolve().parent
LOCK = "2df8198219ceae91bbc993cfdcf6216ec4da911aec5c179f679a580b548e258a"
PROTOCOL = HERE / "ordinary_city_protocol.json"
MONTHS = [date(2021, month, 1) for month in range(1, 13)] + [date(2022, 1, 1)]
BEFORE_MONTHS = [date(2020, 12, 1), *MONTHS[:-1]]
WATER = "open_water_signal"
DIRECTED = [f"{s}_{d}" for s in (WATER, "greenness", "built_surface_signal") for d in ("gain", "loss")]


def lock():
    if sha256(PROTOCOL.read_bytes()).hexdigest() != LOCK:
        raise ValueError("ordinary city protocol changed")
    plan = json.loads(PROTOCOL.read_text())
    for file, digest in plan["frozen_files"].items():
        if sha256((HERE.parents[1] / file).read_bytes()).hexdigest() != digest:
            raise ValueError(f"frozen implementation changed: {file}")
    return plan


def layer(site):
    lon, lat = site["lon"], site["lat"]
    zone = int((lon + 180) // 6) + 1
    crs = CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    unproject = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    x, y = (int(v // 100) * 100 for v in project(lon, lat))
    aoi = box(x - 300, y - 300, x + 300, y + 300)
    return SimpleNamespace(crs=crs, aoi=aoi, bbox=transform(unproject, aoi).bounds)


def schedule(site):
    tile, = provider._spatial_tiles(layer(site))
    for cell in tile["cells"]:
        for i, start in enumerate(MONTHS[:-1]):
            yield dict(site=site["id"], cell=cell["cell_id"], start=start.isoformat(),
                       end=MONTHS[i + 1].isoformat(), geometry=cell["geometry"])


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n")
    tmp.replace(path)


def reference(ee, area, tile, cache):
    """Raw monthly JRC classes at co-located fixed lattice centres."""
    from ee_timeout import call

    if cache.exists():
        return json.loads(cache.read_text())
    x, y, w, h = tile["grid"]
    bands = []
    for day in BEFORE_MONTHS:
        key = day.strftime("%Y_%m")
        bands.append(ee.Image("JRC/GSW1_4/MonthlyHistory/" + key)
                     .select("water").unmask(0, False).rename("m" + key))
    grid = {"dimensions": {"width": w * 5, "height": h * 5}, "crsCode": area.crs.to_string(),
            "affineTransform": {"scaleX": 20, "scaleY": -20, "translateX": x, "translateY": y,
                                "shearX": 0, "shearY": 0}}
    raw = call(lambda: ee.data.computePixels({"expression": ee.Image.cat(bands).toByte(),
                "fileFormat": "NUMPY_NDARRAY", "grid": grid}), retries=1, label="JRC monthly reference")
    out = {}
    for day in BEFORE_MONTHS:
        vals = raw["m" + day.strftime("%Y_%m")].reshape(h, 5, w, 5)
        out[day.isoformat()] = [[int(a), int(b)] for a,b in zip((vals > 0).sum(axis=(1,3)).ravel(),
                                                                (vals == 2).sum(axis=(1,3)).ravel())]
    write_json(cache, out)
    return out


def prepare(ee, area, tile, cache, *, source="sentinel2", first="2018-01-01", last="2022-01-01"):
    records = []
    for start, end in provider._calendar_years(first, last):
        entries, error = provider._cached_catalog(source, area.bbox, start, end, cache, lambda: ee)
        if error:
            raise RuntimeError(error)
        records.extend(entries)
    records = provider._groups(source, records, first, last)
    # Batching changes the number of HTTP calls only. Same frozen pixel function
    # and sorted, same-track mosaics and fixed support as production.
    batches = [records[j:j + provider.BATCH_DATES] for j in range(0, len(records), provider.BATCH_DATES)]
    def fetch(batch):
        return provider._cached_block(ee, area, tile, batch, cache)
    with ThreadPoolExecutor(max_workers=3) as pool:
        cubes = list(pool.map(fetch, batches))
    cube = np.concatenate(cubes) if cubes else np.empty((0, 1 + len(provider.SOURCES[source]["signals"]), len(tile["cells"])), dtype="float32")
    return records, cube


def ref_direction(before, after):
    if before[0] != 25 or after[0] != 25:
        return None
    return "gain" if after[1] > before[1] else "loss" if after[1] < before[1] else "stable"


def run_site(ee, site, folder):
    path = folder / (site["id"] + ".json")
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get("protocol") != LOCK or len(saved["rows"]) != 432:
            raise ValueError("invalid site checkpoint")
        return
    area = layer(site)
    tile, = provider._spatial_tiles(area)
    refs = reference(ee, area, tile, folder / (site["id"] + "_jrc.json"))
    records, values = prepare(ee, area, tile, folder / "sensor")
    rows = []
    signals = provider.SOURCES["sentinel2"]["signals"]
    for j, cell in enumerate(tile["cells"]):
        history = [{"source": "sentinel2", "date": obs["date"], "track": obs["track"],
                    "support_id": cell["support_id"], "coverage": float(sample[-1]),
                    "values": dict(zip(signals, sample[:-1]))}
                   for obs, sample in zip(records, values[:,:,j])]
        for i, month in enumerate(MONTHS[:-1]):
            start, end = month.isoformat(), MONTHS[i + 1].isoformat()
            result = detect_cell(cell["cell_id"], history, start=start, end=end)
            confirmed = [e for e in result["events"] if e["confirmed_on"]]
            before = refs[BEFORE_MONTHS[i].isoformat()][j]
            after = refs[start][j]
            rows.append(dict(site=site["id"], cell=cell["cell_id"], start=start, end=end, state=result["state"],
                             complete=any(s["status"] == "observed" for s in result["series"]),
                             water_complete=any(s["status"] == "observed" and s["signal"] == "mndwi"
                                                for s in result["series"]),
                             candidates=len(result["events"]) - len(confirmed),
                             confirmed=[[e["transition"], e["detected_on"], e["confirmed_on"], e["event_id"]]
                                        for e in confirmed], jrc_before=before, jrc_after=after,
                             jrc_direction=ref_direction(before, after)))
    write_json(path, dict(protocol=LOCK, acquisitions=len(records), rows=rows))
    print(f"completed {site['id']} ({len(records)} acquisitions, {len(rows)} cell-months)", flush=True)


def confusion(pred, truth):
    return ("tp" if pred else "fn") if truth else ("fp" if pred else "tn")


def metrics(rows):
    stats = Counter()
    matrix = {key: {d: Counter(dict.fromkeys(("tp","tn","fp","fn"),0)) for d in ("gain","loss")}
              for key in ("observable_and_reference", "all_reference")}
    for r in rows:
        predicted = {e[0] for e in r["confirmed"]}
        stats.update(dict(cell_months=1, fully_observable=int(r["complete"]),
                          alarmed=int(bool(predicted)), quiet=int(not r["candidates"] and not predicted),
                          candidate_only=int(not predicted and bool(r["candidates"])),
                          confirmed_partial=int(bool(predicted) and not r["complete"]),
                          candidate_only_partial=int(not predicted and bool(r["candidates"]) and not r["complete"]),
                          confirmed_episodes=len(r["confirmed"]), candidate_episodes=r["candidates"],
                          jrc_reference_pairs=int(r["jrc_direction"] is not None)))
        for transition in DIRECTED:
            stats[transition] += int(transition in predicted)
        if r["jrc_direction"] is not None:
            for d in ("gain","loss"):
                key = confusion(WATER + "_" + d in predicted, r["jrc_direction"] == d)
                matrix["all_reference"][d][key] += 1
                if r["water_complete"]:
                    matrix["observable_and_reference"][d][key] += 1
    return {"counts": stats, "water_proxy": matrix, "n_plot_months":len({(r["site"], r["start"]) for r in rows})}


def reviewed_metrics(rows, labels):
    """Join blinded labels after scoring. Return bounds when labels are incomplete."""
    cases = {(r["site"], r["cell"], r["start"]): r for r in rows}
    targets = {"water": WATER, "vegetation": "greenness"}
    joined = {}
    for label in labels:
        k = (label["site"], label["cell"], label["start"])
        target = label["target"]
        verdict = label["verdict"]
        if k not in cases or target not in targets or verdict not in ("gain", "loss", "both", "stable", "unknown"):
            raise ValueError("review row outside the registered sample or vocabulary")
        if (*k, target) in joined:
            raise ValueError("duplicate review row")
        if not label.get("reviewer") or label.get("prediction_blind") is not True:
            raise ValueError("reviewer and prediction-blind attestation required")
        if verdict != "unknown" and (not label.get("evidence_id") or not label.get("evidence_source")
                                     or label.get("independent_of_sentinel2") is not True):
            raise ValueError("observed label needs independent dated evidence and source")
        joined[(*k, target)] = verdict
    reports = {}
    for target, signal in targets.items():
        totals = Counter(dict.fromkeys(("reviewed", "unresolved", "confirmed_cell_months",
                                       "verified_false", "verified_true", "unresolved_confirmations"), 0))
        cms = {d: Counter(dict.fromkeys(("tp", "tn", "fp", "fn"), 0)) for d in ("gain", "loss")}
        for k, row in cases.items():
            verdict = joined.get((*k, target))
            directions = {e[0].removeprefix(signal + "_") for e in row["confirmed"]
                          if e[0].startswith(signal + "_")}
            totals["confirmed_cell_months"] += bool(directions)
            if verdict in (None, "unknown"):
                totals["unresolved"] += 1
                totals["unresolved_confirmations"] += bool(directions)
                continue
            truth = {"gain","loss"} if verdict == "both" else {verdict}
            totals["reviewed"] += 1
            if directions:
                totals["verified_true" if truth.intersection(directions) else "verified_false"] += 1
            for d in cms:
                cms[d][confusion(d in directions, d in truth)] += 1
        plots = len({(r["site"], r["start"]) for r in rows})
        low = totals["verified_false"]
        high = low + totals["unresolved_confirmations"]
        reports[target] = {"counts": totals, "directions": cms, "n_plot_months": plots,
                           "false_alerted_cells_per_plot_month_bounds": [low / plots, high / plots]}
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["roster", "run", "summary", "review", "rows"])
    parser.add_argument("--cache", type=Path, help="local satellite and site cache; required for run, rows, summary")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--site", help="run only this registered site")
    parser.add_argument("--labels", type=Path, help="blinded physical review JSONL")
    args = parser.parse_args()
    plan = lock()
    if args.stage == "review":
        if not args.labels:
            parser.error("review requires --labels")
        with gzip.open(HERE / "ordinary_city_predictions.jsonl.gz", "rt") as stream:
            rows = [json.loads(line) for line in stream]
        raw = args.labels.read_text().strip()
        labels = json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines() if line.strip()]
        print(json.dumps(reviewed_metrics(rows, labels), indent=2))
        return
    if args.stage == "roster":
        for site in plan["sites"]:
            for row in schedule(site):
                print(json.dumps(row, separators=(",",":")))
        return
    if args.cache is None:
        parser.error(f"{args.stage} requires --cache")
    folder = args.cache / LOCK
    folder.mkdir(parents=True, exist_ok=True)
    if args.stage == "run":
        import ee
        from dotenv import load_dotenv
        if args.env_file:
            load_dotenv(args.env_file)
        ee.Initialize(project=os.environ["GEE_PROJECT_ID"])
        sites = [s for s in plan["sites"] if args.site is None or s["id"] == args.site]
        if not sites:
            raise ValueError("unknown registered site")
        for site in sites:
            run_site(ee, site, folder)
    else:
        sites = {s["id"]: json.loads((folder / (s["id"]+".json")).read_text()) for s in plan["sites"]}
        if any(s["protocol"] != LOCK or len(s["rows"]) != 432 for s in sites.values()):
            raise ValueError("incomplete or incompatible site checkpoint")
        rows = [r for v in sites.values() for r in v["rows"]]
        if args.stage == "rows":
            for row in rows:
                print(json.dumps(row, separators=(",", ":")))
            return
        print(json.dumps(dict(protocol_sha256=LOCK, per_site={k: metrics(v["rows"]) for k,v in sites.items()},
                              pooled=metrics(rows)), indent=2))


if __name__ == "__main__":
    main()
