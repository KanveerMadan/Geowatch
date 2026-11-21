"""Record forward silent observations for the frozen six-site water and forest panel."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import sys

from . import data
from .forest import forest
from .monitor_lock import ee_lock
from .water import water

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "monitor_protocol.json"
DEFAULT_STORE = HERE.parents[2] / ".geowatch-round2-monitor"
FILE_SET = (PROTOCOL, HERE/"water.py", HERE/"forest.py", HERE/"data.py", Path(__file__).resolve())


def fingerprint():
    return sha256(b"".join(sha256(p.read_bytes()).digest() for p in FILE_SET)).hexdigest()


def disk_check(store):
    if shutil.disk_usage(store).free < 15_000_000_000:
        raise RuntimeError("downloads paused: less than 15 GB free")


def setup(store):
    store.mkdir(parents=True, exist_ok=True)
    data.CACHE = store / "source-cache"
    db = sqlite3.connect(store / "observations.sqlite", timeout=60)
    db.execute("""CREATE TABLE IF NOT EXISTS snapshots (method TEXT,site TEXT,cutoff TEXT,receipt TEXT NOT NULL,
               PRIMARY KEY(method,site,cutoff))""")
    db.execute("""CREATE TABLE IF NOT EXISTS evidence (
               method TEXT,site TEXT,cell TEXT,kind TEXT,target TEXT,day TEXT,source TEXT,track TEXT,
               first_received TEXT,first_cutoff TEXT,PRIMARY KEY(method,site,cell,kind,target,day,source,track))""")
    return db


def observed_evidence(c):
    for event in c["water"]["candidates"]:
        yield ("candidate", "water_"+event["target"],event["day"],event["source"],event["track"])
    for direction in ("gain","loss"):
        for day in c["water"][direction]:
            yield ("confirmation", "water_"+direction,day,"fused","")
    for kind, field in (("candidate","candidates"),("confirmation","confirmed")):
        for event in c["forest"][field]:
            yield (kind,"forest_loss",event["day"],event["source"],event["track"])


def record(db, receipt):
    """Claim each dated piece of evidence and its enclosing site snapshot in one transaction."""
    key=(receipt["method"],receipt["site"],receipt["cutoff"])
    with db:
        old=db.execute("SELECT receipt FROM snapshots WHERE method=? AND site=? AND cutoff=?",key).fetchone()
        if old:
            return json.loads(old[0])
        new=Counter()
        for c in receipt["cells"]:
            for item in observed_evidence(c):
                n=db.execute("INSERT OR IGNORE INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?)",
                             (*key[:2],c["id"],*item,receipt["received"],receipt["cutoff"])).rowcount
                new[item[0]]+=n
        receipt={**receipt, "new_evidence":dict(new)}
        db.execute("INSERT INTO snapshots VALUES(?,?,?,?)",(*key,json.dumps(receipt,allow_nan=False)))
    return receipt


def period(now):
    cutoff = now.date() - timedelta(days=1)
    start = cutoff.replace(day=1)
    return start, cutoff, cutoff+timedelta(days=1)


def histories(ee, crs, xy, first, end):
    finish_month = (first + timedelta(days=32)).replace(day=1)
    parts = []
    for prior_year in (first.year-2, first.year-1):
        a = first.replace(year=prior_year) - timedelta(days=47)
        b = finish_month.replace(year=prior_year + (finish_month.year-first.year)) + timedelta(days=47)
        parts.append(data.history(ee, crs, xy, str(a), str(b)))
    boundary = first - timedelta(days=120)
    # Splitting history at first lets future daily cutoffs reuse pre-month acquisitions.
    parts.append(data.history(ee, crs, xy, str(boundary), str(first)))
    parts.append(data.history(ee, crs, xy, str(first), str(end)))
    return [[record for part in parts for record in part[i]] for i in range(len(xy))]


def process(site, ee, now):
    first, cutoff, end = period(now)
    crs, xy = data.grid(site[1],site[2])
    rows = histories(ee,crs,xy,first,end)
    mask = data.permanence(ee,crs,xy,str(first))
    forest_mask = data.forest_cover(ee,crs,xy,str(first))
    cells = []
    for (x,y), obs, permanent, forest_share in zip(xy,rows,mask,forest_mask,strict=True):
        water_rows = [r for r in obs if r["day"] >= str(first-timedelta(days=120))]
        w = water(water_rows,str(first),str(end),permanent)
        f = forest(obs,str(first),str(end),forest_share)
        monitor = [r for r in obs if r["day"] >= str(first)]
        cells.append({"id": f"{crs}/{x}/{y+100}", "water":w,"forest":f,"monitor_observations":monitor,
                      "prior_water_fraction":permanent, "prior_forest_share":forest_share})
    return dict(site=site[0],method=fingerprint(),period=[str(first),str(end)],cutoff=str(cutoff),
                began=now.isoformat(),received=datetime.now(timezone.utc).isoformat(),cells=cells)


def layers(c):
    return {"confirmed": {"water_gain":bool(c["water"]["gain"]),"water_loss":bool(c["water"]["loss"]),
                          "forest_loss":bool(c["forest"]["confirmed"])},
            "candidate": bool(c["water"]["candidates"] or c["forest"]["candidates"]),
            "observed": bool(c["water"]["observed"] or c["forest"]["observed_sources"])}


def summary(receipts):
    out = {}
    total = Counter()
    for r in receipts:
        counts = Counter()
        for c in r["cells"]:
            hit = layers(c)
            counts["cells"] += 1
            counts["confirmed_cells"] += any(hit["confirmed"].values())
            counts["candidate_only_cells"] += hit["candidate"] and not any(hit["confirmed"].values())
            counts["observable_some_target"] += hit["observed"]
            counts["unjudged_quiet_cells"] += not hit["observed"] and not hit["candidate"] and not any(hit["confirmed"].values())
            counts["water_candidate_observations"] += len(c["water"]["candidates"])
            counts["forest_candidate_observations"] += len(c["forest"]["candidates"])
            counts.update(hit["confirmed"])
        total.update(counts)
        out[r["site"]] = {"counts":dict(counts),"received":r["received"],"cutoff":r["cutoff"],
                         "new_evidence":r.get("new_evidence",{})}
    return {"method":fingerprint(),"sites":out,"total":dict(total),"zero_baseline_confirmed_cells":0}


def run(store):
    plan = data.read(PROTOCOL)
    with ee_lock(), setup(store) as db:
        now = datetime.now(timezone.utc)
        _, cutoff, _ = period(now)
        errors = []
        result = []
        ee = None
        for site in plan["sites"]:
            key = fingerprint(),site[0],str(cutoff)
            old = db.execute("SELECT receipt FROM snapshots WHERE method=? AND site=? AND cutoff=?",key).fetchone()
            if old:
                result.append(json.loads(old[0]))
                continue
            disk_check(store)
            try:
                if ee is None:
                    ee = data.connect()
                # All sites in an invocation use one cutoff, but each records actual receipt time.
                began = datetime.now(timezone.utc).isoformat()
                receipt = process(site,ee,now)
                receipt["began"] = began
                result.append(record(db,receipt))
                print("recorded " + site[0] + " " + str(cutoff), file=sys.stderr,flush=True)
            except Exception as exc:
                errors.append((site[0],type(exc).__name__,str(exc)[:500]))
        if errors:
            raise RuntimeError(f"incomplete collection; retry same cutoff: {errors}")
        return summary(result)


def receipts(db,cutoff):
    rows = db.execute("SELECT receipt FROM snapshots WHERE method=? AND cutoff=? ORDER BY site",
                      (fingerprint(),cutoff)).fetchall()
    output = [json.loads(r[0]) for r in rows]
    if {r["site"] for r in output} != {s[0] for s in data.read(PROTOCOL)["sites"]}:
        raise ValueError("collection is incomplete for this method and cutoff")
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["run","summary"])
    parser.add_argument("--store",type=Path,default=DEFAULT_STORE)
    parser.add_argument("--cutoff",help="existing UTC acquisition cutoff, for summary only")
    args=parser.parse_args()
    if args.action=="run":
        if args.cutoff:
            parser.error("live collection always uses the actual last complete UTC day")
        out=run(args.store)
    else:
        with setup(args.store) as db:
            out=summary(receipts(db,args.cutoff or str(period(datetime.now(timezone.utc))[1])))
    print(json.dumps(out,indent=2))


if __name__=="__main__":
    main()
