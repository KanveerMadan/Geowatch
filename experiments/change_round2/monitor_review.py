"""Build and score a prediction-blind, independent Landsat review packet for one live cutoff."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageDraw
from experiments.change_history import ordinary_city_visual as visual
from . import data
from .monitor import DEFAULT_STORE, disk_check, fingerprint, layers, period, receipts, setup
from .monitor_lock import ee_lock

TARGETS = ("water_gain","water_loss","forest_loss")


def select(snapshots):
    selected = []
    for snap in snapshots:
        def blind(c):
            key = "|".join((snap["site"],snap["method"],c["id"],snap["cutoff"]))
            return sha256(key.encode()).hexdigest()[:16]
        cells = sorted(snap["cells"],key=blind)
        confirmed = [c for c in cells if any(layers(c)["confirmed"].values())]
        candidate = [c for c in cells if layers(c)["candidate"] and c not in confirmed]
        quiet = [c for c in cells if c not in candidate and c not in confirmed]
        visible = [c for c in quiet if layers(c)["observed"]]
        for stratum, pool in (("confirmed" if confirmed else "candidate",confirmed or candidate),
                              ("quiet",visible or quiet)):
            if not pool:
                continue
            c = pool[0]
            pred=layers(c)
            pred["target_observed"]={"water_"+direction:direction in c["water"]["observed_targets"]
                                     for direction in ("gain","loss")}
            pred["target_observed"]["forest_loss"]=bool(c["forest"]["observed_sources"])
            selected.append({"id":blind(c),"stratum":stratum,"site":snap["site"],"cell":c["id"],
                             "start":snap["period"][0],"end":snap["period"][1],
                             "pred":pred,"stratum_n":len(pool)})
    return sorted(selected, key=lambda c:c["id"])


def folder(store, cutoff):
    return store / "review" / fingerprint() / cutoff


def make(store, cutoff):
    dest = folder(store,cutoff)
    raw, blind = dest / "data", dest / "blind"
    raw.mkdir(parents=True, exist_ok=True)
    blind.mkdir(exist_ok=True)
    with ee_lock(), setup(store) as db:
        cases = select(receipts(db,cutoff))
        ee = None
        for c in cases:
            disk_check(store)
            png, evidence = blind/(c["id"]+".png"), raw/(c["id"]+".json")
            if png.exists() and evidence.exists():
                continue
            if ee is None:
                ee = data.connect()
            views, all_ids = visual.fetch_strip(ee,c)
            # Use a neutral identifier for the actual display and filesystem.
            fake = {"site":c["id"],"cell":"","start":""}
            labels = visual.display(fake,views,blind)
            old = blind/(visual.blind_id(fake)+".png")
            with Image.open(old) as source:
                view=source.copy()
            pen=ImageDraw.Draw(view)
            pen.rectangle((0,0,view.width,22),fill="white")
            pen.text((3,3),c["id"]+"  RGB / SWIR-NIR-red",fill="black")
            view.save(png)
            old.unlink()
            data.save(evidence,dict(usable=labels,inventory=[a["id"] for a in all_ids],
                                    image_sha256=sha256(png.read_bytes()).hexdigest()))
        data.save(raw/"selection.json",cases)
    print(blind)


def seal(path, value):
    encoded=json.dumps(value,allow_nan=False,sort_keys=True).encode()
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("earlier signed review differs; preserve original review")
        return
    with NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(encoded)
    temp=Path(f.name)
    try:
        os.link(temp,path)
    finally:
        temp.unlink()


def assess(cases,labels,evidence):
    if not labels.get("reviewer") or labels.get("prediction_blind") is not True:
        raise ValueError("reviewer and prediction-blind attestation required")
    verdicts=labels["cases"]
    if set(verdicts)!={c["id"] for c in cases}:
        raise ValueError("include every blind packet case, including unknown")
    report=[]
    metrics={t:Counter() for t in TARGETS}
    silent={t:Counter() for t in TARGETS}
    paired={t:Counter() for t in TARGETS}
    reference_positive=Counter()
    for c in cases:
        label=verdicts[c["id"]]
        if not label.get("reason") or label.get("water") not in ("stable","gain","loss","both","unknown") or label.get("vegetation") not in ("stable","loss","unknown"):
            raise ValueError("invalid visual verdict or missing reason")
        e=evidence[c["id"]]["usable"]
        before={v.split("_")[-1] for v in e["prior"]}
        during={v.split("_")[-1] for v in e["during"]}
        for val in [label["water"],label["vegetation"]]:
            if val!="unknown" and (not before or len(during)<(2 if val=="stable" else 1)):
                raise ValueError("insufficient dates for visual verdict")
        for t in TARGETS:
            observed=label["vegetation"] if t=="forest_loss" else label["water"]
            pred=c["pred"]["confirmed"][t]
            if observed=="unknown":
                metrics[t]["unknown_reference"]+=1
                silent[t]["unknown_reference"]+=1
                continue
            truth=observed in (t.split("_")[1],"both")
            reference_positive[t]+=int(truth)
            baseline="fn" if truth else "tn"
            silent[t][baseline]+=1
            if not pred and not c["pred"]["target_observed"][t]:
                metrics[t]["abstained_reference_positive" if truth else "abstained_reference_negative"]+=1
                continue
            outcome=("tp" if truth else "fp") if pred else baseline
            metrics[t][outcome]+=1
            paired[t][baseline]+=1
        report.append({**c,"review":label,"evidence":evidence[c["id"]]})
    return {"reviewer":labels["reviewer"],"prediction_blind":True,"sample":report,
            "sample_counts":metrics,"always_silent_comparison":silent,"silent_on_judged_subset":paired,
            "recall_including_abstentions":{t:metrics[t]["tp"]/reference_positive[t] if reference_positive[t] else None
                                            for t in TARGETS}}


def carry_forward(store,cutoff,previous):
    """Carry immutable blind decisions only when physical support, date and displayed pixels match."""
    if len(previous)!=64 or any(c not in "0123456789abcdef" for c in previous):
        raise ValueError("previous method must be a full SHA256")
    old=store/"review"/previous/cutoff
    current=folder(store,cutoff)
    if old==current:
        raise ValueError("choose a different previously sealed method")
    sealed=data.read(old/"sealed_labels.json")
    key=lambda c:(c["site"],c["cell"],c["start"],c["end"])
    by_key={key(c):c["id"] for c in data.read(old/"data/selection.json")}
    labels={}
    for case in data.read(current/"data/selection.json"):
        prev_id=by_key.get(key(case))
        if prev_id is None: continue
        ident=case["id"]
        a=data.read(old/"data"/(prev_id+".json"))
        b=data.read(current/"data"/(ident+".json"))
        if a["usable"]!=b["usable"] or a["inventory"]!=b["inventory"]:
            continue
        def body(path):
            with Image.open(path) as img:
                return img.size,img.crop((0,23,img.width,img.height)).tobytes()
        if body(old/"blind"/(prev_id+".png"))==body(current/"blind"/(ident+".png")):
            labels[ident]=sealed["cases"][prev_id]
    return {"reviewer":sealed["reviewer"],"prediction_blind":True,"cases":labels,
            "carried_from":previous}


def join(store,cutoff,labels_path):
    dest=folder(store,cutoff)
    cases=data.read(dest/"data/selection.json")
    labels=data.read(labels_path)
    evidence={c["id"]:data.read(dest/"data"/(c["id"]+".json")) for c in cases}
    outcome=assess(cases,labels,evidence)
    seal(dest/"sealed_labels.json",labels)
    return {"cutoff":cutoff,"method":fingerprint(),**outcome}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action",choices=["make","join","carry"])
    ap.add_argument("--store",type=Path,default=DEFAULT_STORE)
    ap.add_argument("--cutoff",default=str(period(datetime.now(timezone.utc))[1]))
    ap.add_argument("--labels",type=Path)
    ap.add_argument("--previous",help="previously sealed method for carry")
    args=ap.parse_args()
    if args.action=="make":
        make(args.store,args.cutoff)
    elif args.action=="carry":
        if not args.previous:
            ap.error("carry requires --previous method hash")
        print(json.dumps(carry_forward(args.store,args.cutoff,args.previous),indent=2))
    else:
        if not args.labels:
            ap.error("join requires --labels")
        print(json.dumps(join(args.store,args.cutoff,args.labels),indent=2))


if __name__=="__main__":
    main()
