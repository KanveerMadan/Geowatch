"""Ordinary plot-month replay of the production default source configuration."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path

from experiments.change_history import ordinary_city as base
from vector import change_observations as provider
from vector.change_detection import detect_cell

LOCK = "169b3c039a510e4e2bf1fb4ac70be96fed903109013a20b7ea76ce6eaa64abe1"
PROTOCOL = base.HERE / "ordinary_city_default_protocol.json"
PERIODS = [(date(2024, m, 1).isoformat(), date(2024, m + 1, 1).isoformat()) for m in (1, 4, 7, 10)]


def load_protocol():
    base.lock()
    if sha256(PROTOCOL.read_bytes()).hexdigest() != LOCK:
        raise ValueError("default-source ordinary protocol changed")
    return json.loads(PROTOCOL.read_text())


def histories(ee, site, cache, first, last):
    area = base.layer(site)
    tile, = provider._spatial_tiles(area)
    histories = [[] for _ in tile["cells"]]
    inventories = {}
    for source in provider.DEFAULT_SOURCES:
        records, values = base.prepare(ee, area, tile, cache, source=source, first=first, last=last)
        inventories[source] = len(records)
        for j, cell in enumerate(tile["cells"]):
            for obs, sample in zip(records, values[:, :, j]):
                histories[j].append({"date": obs["date"], "source": source, "track": obs["track"],
                    "lineage": obs["lineage"], "support_id": cell["support_id"], "coverage": float(sample[-1]),
                    "values": dict(zip(provider.SOURCES[source]["signals"], sample[:-1]))})
    return tile, histories, inventories


def detect(site, first, last, periods, ee, folder):
    tile, histories_by_cell, inventory = histories(ee, site, folder / "sensor", first, last)
    rows = []
    for cell, history in zip(tile["cells"], histories_by_cell):
        for start, end in periods:
            result = detect_cell(cell["cell_id"], history, start=start, end=end)
            complete = [s for s in result["series"] if s["status"] == "observed"]
            rows.append({"site": site["id"], "cell": cell["cell_id"], "start": start, "end": end,
                         "state": result["state"], "observable_signals": sorted({s["signal"] for s in complete}),
                         "observable_sources": sorted({s["source"] for s in complete}),
                         "candidates": sum(e["confirmed_on"] is None for e in result["events"]),
                         "confirmed": [{k:e[k] for k in ("event_id", "detected_on", "confirmed_on", "transition",
                                                         "sources")} for e in result["events"] if e["confirmed_on"]]})
    return {"protocol_sha256": LOCK, "acquisitions": inventory, "rows": rows}


def summary(rows):
    counts = Counter()
    sources, signals, changes, confirmed_sources = (Counter() for _ in range(4))
    for r in rows:
        alarm = bool(r["confirmed"])
        counts.update(cell_months=1, fully_observable=int(bool(r["observable_signals"])),
                      alarmed=int(alarm), confirmed_partial=int(alarm and not r["observable_signals"]),
                      candidate_only=int(bool(r["candidates"]) and not alarm), candidate_episodes=r["candidates"],
                      confirmed_episodes=len(r["confirmed"]))
        sources.update(r["observable_sources"])
        signals.update(r["observable_signals"])
        changes.update(sorted({e["transition"] for e in r["confirmed"]}))
        confirmed_sources.update(sorted({source for e in r["confirmed"] for source in e["sources"]}))
    return {"counts": counts, "observable_by_source": sources, "observable_by_signal": signals,
            "confirmed_cells_by_transition": changes, "confirmed_cells_by_source": confirmed_sources,
            "plot_months": len({(r["site"], r["start"]) for r in rows})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["run","summary","rows"])
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    plan = load_protocol()
    folder = args.cache / LOCK
    folder.mkdir(parents=True, exist_ok=True)
    if args.stage == "run":
        import ee
        from dotenv import load_dotenv
        if args.env_file:
            load_dotenv(args.env_file)
        ee.Initialize(project=os.environ["GEE_PROJECT_ID"])
        for site in plan["sites"]:
            path = folder / (site["id"] + ".json")
            if not path.exists():
                base.write_json(path, detect(site, "2019-01-01", "2024-11-01", PERIODS, ee, folder))
                print(f"completed {site['id']}", flush=True)
    else:
        checkpoints = {s["id"]: json.loads((folder / (s["id"] + ".json")).read_text()) for s in plan["sites"]}
        if any(s["protocol_sha256"] != LOCK or len(s["rows"]) != 144 for s in checkpoints.values()):
            raise ValueError("incomplete default study")
        rows = [r for v in checkpoints.values() for r in v["rows"]]
        if args.stage == "rows":
            for r in rows:
                print(json.dumps(r, separators=(",",":")))
        else:
            print(json.dumps({"protocol_sha256": LOCK, "pooled": summary(rows),
                              "per_site": {k: summary(v["rows"]) for k,v in checkpoints.items()}}, indent=2))


if __name__ == "__main__":
    main()
