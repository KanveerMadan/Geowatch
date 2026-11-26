"""Take a silent, wall-clock observation snapshot; no public alert is sent."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3

from experiments.change_history import ordinary_city_default as cohort
from vector.change_detection import detect_cell


def monitoring_dates(now):
    # Keep the monitoring calendar and its calibration block length fixed as new
    # acquisitions arrive. Only completed UTC acquisition days are considered.
    cutoff = now.date() - timedelta(days=1)
    start = cutoff.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end, cutoff


def record(db, snapshot, events):
    db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
               site TEXT, cutoff TEXT, receipt TEXT NOT NULL, PRIMARY KEY(site, cutoff))""")
    db.execute("""CREATE TABLE IF NOT EXISTS confirmations (
               site TEXT, event_id TEXT, cell TEXT NOT NULL, first_seen_utc TEXT NOT NULL,
               event TEXT NOT NULL, PRIMARY KEY(site, event_id))""")
    key = (snapshot["site"], snapshot["acquisition_cutoff"])
    with db:
        claimed = db.execute("INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?)", (*key, "{}")).rowcount
        if not claimed:
            return json.loads(db.execute("SELECT receipt FROM snapshots WHERE site=? AND cutoff=?", key).fetchone()[0])
        added = 0
        for cell, e in events:
            added += db.execute("INSERT OR IGNORE INTO confirmations VALUES (?, ?, ?, ?, ?)",
                                (snapshot["site"], e["event_id"], cell, snapshot["received_until_utc"],
                                 json.dumps(e, allow_nan=False))).rowcount
        receipt = {**snapshot, "newly_logged_signal_episodes": added}
        db.execute("UPDATE snapshots SET receipt=? WHERE site=? AND cutoff=?", (json.dumps(receipt), *key))
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sites = {s["id"]:s for s in cohort.load_protocol()["sites"]}
    p.add_argument("--site", required=True, choices=sorted(sites))
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--env-file", type=Path)
    args = p.parse_args()
    folder = args.cache / ("shadow-" + cohort.LOCK)
    folder.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    start, end, cutoff = monitoring_dates(started)
    with sqlite3.connect(folder / "ledger.sqlite", timeout=60) as db:
        existing = db.execute("SELECT name FROM sqlite_master WHERE name='snapshots'").fetchone()
        if existing:
            prior = db.execute("SELECT receipt FROM snapshots WHERE site=? AND cutoff=?",
                               (args.site, cutoff.isoformat())).fetchone()
            if prior:
                print(prior[0])
                return
        import ee
        from dotenv import load_dotenv
        if args.env_file:
            load_dotenv(args.env_file)
        ee.Initialize(project=os.environ["GEE_PROJECT_ID"])
        first = start.replace(year=start.year - 5)
        tile, histories, inventory = cohort.histories(ee, sites[args.site], folder/"sensor",
                            first.isoformat(), (cutoff + timedelta(days=1)).isoformat())
        events = []
        cells = []
        for cell, history in zip(tile["cells"], histories):
            result = detect_cell(cell["cell_id"], history, start=start, end=end, as_of=cutoff)
            events.extend((cell["cell_id"], e) for e in result["events"] if e["confirmed_on"])
            cells.append({"cell": cell["cell_id"], "state": result["state"],
                          "confirmed_ids":[e["event_id"] for e in result["events"] if e["confirmed_on"]],
                          "candidates":sum(e["confirmed_on"] is None for e in result["events"]),
                          "series":[{"source": s["source"], "track": s["track"], "signal": s["signal"],
                                     "status": s["status"], "usable_dates": s["observed_count"]}
                                    for s in result["series"]]})
        receipt = record(db, {"source_study":cohort.LOCK, "site":args.site, "mode":"live_silent",
            "received_from_utc":started.isoformat(), "received_until_utc":datetime.now(timezone.utc).isoformat(),
            "acquisition_cutoff":cutoff.isoformat(), "period":[start.isoformat(),end.isoformat()],
            "source_inventories":inventory, "cells":cells}, events)
        print(json.dumps(receipt, separators=(",",":")))


if __name__ == "__main__":
    main()
