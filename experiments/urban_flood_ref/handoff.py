"""Guarded package inventory and manifest for the training session. No cache scans."""
import argparse
import csv
import json

import numpy as np
import rasterio
from pathlib import Path

from .guard import authorize, metadata
from .evaluation import reference_array
from .package import check_grid,sha
from .sidecars import make_sidecar


def make_index(root):
    root=Path(root)
    result=[]
    for candidate in metadata()[1]:
        event=candidate["unit"]
        try:
            record=authorize(event)
        except ValueError:
            continue
        for control in (False,True):
            unit=event+("_control" if control else "")
            pkg=root/"events"/unit
            if not (pkg/"manifest.json").is_file():
                continue
            refs=[]
            ind=root/"independent"/event
            if not control and event.startswith("usf_weihui_"):
                receipt=ind/"weihui_reference.json"
                if receipt.is_file():
                    info=json.loads(receipt.read_text())
                    if info["unit"]!=event:
                        raise ValueError("Mismatched benchmark provenance")
                    for stem,label in (("weihui_gt","All flood"),("weihui_fu","Flooded urban"),
                                       ("weihui_fo","Flooded open")):
                        path=ind/(stem+".tif")
                        if path.is_file():
                            refs.append({"name":label,"path":str(path.relative_to(root)),"date":info["date"],
                                         "role":"Shared-Sentinel-1 external benchmark","source":info["source"],
                                         "receipt":str(receipt.relative_to(root))})
            stem = "s2_control" if control else "s2_event"
            if (ind/(stem+".tif")).is_file() and (ind/(stem+".json")).is_file():
                receipt=ind/(stem+".json")
                info=json.loads(receipt.read_text())
                # A time envelope may include two dates. Never substitute the SAR date.
                dates=([info["reference_date"]] if info.get("reference_date") else info.get("post_dates",[]))
                if not dates:
                    scenes=info.get("acquisitions",{}).get("post",[])
                    dates=sorted({s["datetime"][:10] for s in scenes if isinstance(s,dict) and s.get("datetime")})
                    if not dates:
                        dates=sorted({f"{s[:4]}-{s[4:6]}-{s[6:8]}" for s in scenes if isinstance(s,str) and s[:8].isdigit()})
                refs.append({"name":"Sentinel-2 visible water","path":str((ind/(stem+".tif")).relative_to(root)),
                             "date":dates[0] if len(dates)==1 else "", "dates":dates,
                             "role":"Independent sensor, automated optical","source":info.get("sensor","Sentinel-2"),
                             "receipt":str(receipt.relative_to(root))})
            if not control and (ind/"ufo_surface.tif").is_file() and (ind/"ufo_reference.json").is_file():
                rec=ind/"ufo_reference.json"
                info=json.loads(rec.read_text())
                meta=json.loads((pkg/"manifest.json").read_text())
                if info["unit"]!=event or info["grid"]!=meta["grid"] or not info.get("date"):
                    raise ValueError("Published VHR reference identity, grid or date mismatch")
                vhr=reference_array(ind/"ufo_surface.tif",meta["grid"])
                if np.isin(vhr,[0,1]).any():
                    refs.append({"name":"UFO PlanetScope visible water","path":str((ind/"ufo_surface.tif").relative_to(root)),
                                 "date":info["date"],"role":"Independent sensor, published human optical interpretation",
                                 "source":info.get("source","Urban Flood Observations, 3 metre PlanetScope"),
                                 "receipt":str(rec.relative_to(root))})
            if not control and (ind/"maxar_review.tif").is_file() and (ind/"maxar_review.json").is_file():
                receipt=ind/"maxar_review.json"
                info=json.loads(receipt.read_text())
                dates=info.get("acquisition_dates",{})
                refdate=dates.get("post","") if isinstance(dates,dict) else ""
                refs.append({"name":"Maxar visual review","path":str((ind/"maxar_review.tif").relative_to(root)),
                             "date":refdate or "","role":"Independent sensor, assistant visual interpretation",
                             "source":"Maxar Open Data optical imagery","receipt":str(receipt.relative_to(root))})
            result.append({"event_id":event,"unit":unit,"kind":"pre_event_control" if control else "event",
                           "incident":record["incident"],"references":refs,
                           "historical":not control and (root/"historical"/unit/"receipt.json").is_file()})
    return result


def read_manual_labels(root,unit,info,incident,*,partial=False):
    folder=root/("partial_water_refs" if partial else "manual_refs")
    p=folder/(unit+".npz")
    receipt=folder/(unit+".json")
    if not (p.is_file() and receipt.is_file()):
        return None
    data=json.loads(receipt.read_text())
    if data.get("unit")!=unit or data.get("file")!=str(p.relative_to(root)) or data.get("sha256")!=sha(p):
        raise ValueError("Human reference receipt disagrees with file or unit")
    with np.load(p,allow_pickle=False) as z:
        wet,valid=z["flooded"],z["valid"]
        meta=json.loads(str(z["meta"]))
    if (wet.dtype!=bool or valid.dtype!=bool or wet.shape!=tuple(info["grid"]["shape"])
            or wet.shape!=valid.shape or (wet & ~valid).any() or meta.get("grid")!=info["grid"]):
        raise ValueError("Model-compatible human reference mask/schema mismatch")
    counts={"wet":int(wet.sum()),"dry":int((valid & ~wet).sum()),"unknown":int((~valid).sum())}
    if any(data[k]!=v for k,v in counts.items()):
        raise ValueError("Reviewed archive counts disagree with source receipt")
    if data.get("incident",incident)!=incident or data.get("role","dev")!="dev":
        raise ValueError("DEV label source has a conflicting incident or role")
    source_raster=f"independent/{unit}/ufo_surface.tif"
    name="published human optical"
    interpretation=("Optional DEV use on reviewed visible cells; group all tiles of this flood together." if valid.any() else "Zero classified cells; no training samples for this whole-cell target.")
    if partial:
        source_raster=f"independent/{unit}/ufo_urban_wet_children.tif"
        if (data.get("source_raster")!=source_raster or data.get("source_raster_sha256")!=sha(root/source_raster)
                or not np.array_equal(wet,valid) or counts["dry"]!=0):
            raise ValueError("Partial-water source must be authenticated and positive-only")
        with rasterio.open(root/source_raster) as src:
            crs,t,shape=check_grid(info["grid"])
            if src.count!=1 or src.nodata!=255 or src.crs!=crs or src.shape!=shape or src.transform!=t:
                raise ValueError("Partial-water count raster grid mismatch")
            children=src.read(1)
            if not np.isin(children,[*range(10),255]).all():
                raise ValueError("Unexpected number of homogeneous 10 m water patches")
            evidence=(children!=255)&(children>0)
            if not np.array_equal(wet,evidence) or int(children[evidence].sum())!=data["confirmed_wet_children"]:
                raise ValueError("Partial-presence model labels and source counts disagree")
        name="partial urban water presence (positive-only)"
        interpretation=("Optional DEV target for any observed 10 m newly wet patch inside a built-up 30 m cell; "
                        "never pool with whole-cell inundation or use for whole-cell accuracy." if counts["wet"]
                        else "Zero supported positive cells. Manifest-only result for this target.")
    rights=data.get("rights",{})
    licence=rights.get("licence") or data.get("licence")
    if not licence:
        raise ValueError("Published human reference lacks distribution terms")
    return {**data,"parent_incident":incident,"source_kind":name,
            "reference_date":data.get("reference_date") or data.get("date") or meta.get("reference_date"),
            "source_raster":source_raster,
            "source_receipt":f"independent/{unit}/ufo_reference.json","rights":{**rights,"licence":licence},
            "interpretation":interpretation}


def handoff(root, index, output):
    root,output=Path(root),Path(output)
    rows=[]
    aids=[]
    for item in index:
        record=authorize(item["event_id"])
        u=item["unit"]
        status=item["kind"]
        if u!=record["unit"]+("_control" if status=="pre_event_control" else ""):
            raise ValueError("Handoff unit and guarded incident identity differ")
        prefix=f"events/{u}"
        info=json.loads((root/prefix/"manifest.json").read_text())
        c=info["counts30"]
        path=f"refs/{u}.npz"
        checksum=sha(root/path)
        if checksum!=info["sha256"][path]:
            raise ValueError("Model training archive checksum mismatch")
        refs=item["references"]
        roles=sorted({r["role"] for r in refs})
        options=[]
        if status=="event":
            for filename,kind in (("maxar_review.tif","reviewed"),("weihui_fu.tif","benchmark")):
                if any(Path(r["path"]).name==filename for r in refs):
                    option=make_sidecar(root,u,kind)
                    if option:
                        options.append(option["file"])
                        aids.append(option)
            if (root/"manual_refs"/(u+".json")).is_file():
                option=read_manual_labels(root,u,info,record["incident"])
                if option:
                    options.append(option["file"])
                    aids.append(option)
            option=read_manual_labels(root,u,info,record["incident"],partial=True)
            if option:
                options.append(option["file"])
                aids.append(option)
        item["optional_dev_labels"]=options
        rows.append({"event_id":record["unit"],"unit":u,"incident":record["incident"],"kind":status,
                     "event_anchor":record["date"],"radar_post":info["post_date"],
                     "flooded":c["confident_flooded"],"dry":c["confident_dry"],"ambiguous":c["ambiguous"],
                     "unobserved":c["unobserved"],"npz":path,"training_npz_sha256":checksum,
                     "manifest":prefix+"/manifest.json","scientific_rasters":prefix+"/reference_{10,30}m.tif",
                     "external_receipts":" | ".join(sorted({r["receipt"] for r in refs if r.get("receipt")})),
                     "review_evidence":" | ".join(roles) or "none",
                     "recommendation":"exclude from training (control)" if status=="pre_event_control"
                                      else "hold pending independent review and justified training scope",
                     "archived_comparator":f"historical/{u}/receipt.json" if item["historical"] else "",
                     "optional_dev_label_paths":" | ".join(options),
                     "human_survey_labels":("published human interpretation of PlanetScope visible surfaces"
                                            if any(r["role"]=="Independent sensor, published human optical interpretation" for r in refs)
                                            else "no human-interpreted optical labels furnished")})
    primary={r["event_id"] for r in rows if r["kind"]=="event"}
    for candidate in metadata()[1]:
        unit=candidate["unit"]
        try:
            site=authorize(unit)
        except ValueError:
            continue
        if unit in primary:
            continue
        rec=root/"independent"/unit/"ufo_reference.json"
        if not rec.is_file():
            continue
        info=json.loads(rec.read_text())
        if info.get("unit")!=unit:
            raise ValueError("Optical-only source identity mismatch")
        for partial in (False,True):
            option=read_manual_labels(root,unit,info,site["incident"],partial=partial)
            if option:
                aids.append(option)
    output.mkdir(parents=True,exist_ok=True)
    with (output/"handoff_manifest.csv").open("w",newline="") as dst:
        fields=list(rows[0]) if rows else ["unit","incident","kind","npz","recommendation"]
        writer=csv.DictWriter(dst,lineterminator="\n",fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with (output/"label_options.csv").open("w",newline="") as dst:
        cols=["unit","parent_incident","source_kind","reference_date","file","sha256","wet","dry","unknown",
              "source_raster","source_receipt","licence","recommendation"]
        writer=csv.DictWriter(dst,lineterminator="\n",fieldnames=cols)
        writer.writeheader()
        for r in aids:
            writer.writerow({k:r[k] for k in cols if k not in ("licence","recommendation")}
                            | {"licence":r["rights"]["licence"],"recommendation":r["interpretation"]})
    msg=["# Handoff to the flood-model session","",
        f"The evidence package contains {sum(r['kind']=='event' for r in rows)} radar incident tiles and "
        f"{sum(r['kind']!='event' for r in rows)} pre-event control tiles. Each line in "
        "[handoff_manifest.csv](handoff_manifest.csv) identifies a shipped model-compatible NPZ, its checksum, "
        "the two scientific maps, provenance and its evidence-review receipts.","",
        "Treat incident products as development candidates. Preserve the wet, dry and unknown label mask. "
        "The emitted dry labels are the detector’s restricted open-ground proxy. Ambiguous urban streets must remain unknown. "
        "Controls measure repeat-detection burden and have no event target for retraining. The three Weihui tiles "
        "share one flood and a SAR-derived benchmark used during development. Keep them in one development group. "
        "Quantify transfer on independently selected incidents in a future locked test.","",
        "External reviewer evidence and automatic optical checks have separate rows in the evidence tables. "
        "A shared-sensor external benchmark is not an independent sensor. Some automated optical maps may contain "
        "no observed wet or dry cells; inspect the actual denominators. Assisted visual interpretation on a small VHR patch "
        "supports only its reviewed footprint. Source imagery in download caches is outside this shipment.","",
        "| Unit | Acquisition | 30 m flooded | Dry | Ambiguous | Unobserved | Action |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for r in rows:
        action="Exclude control" if r["kind"]!="event" else "Hold for review"
        msg.append(f"| {r['unit']} | {r['radar_post']} | {r['flooded']} | {r['dry']} | {r['ambiguous']} | {r['unobserved']} | {action} |")
    msg.extend(["","## Optional source-specific development aids","",
                "[label_options.csv](label_options.csv) lists every additional shipped NPZ and its provenance. "
                "Each uses the same Boolean flooded/valid schema. Published benchmark positives and visually "
                "reviewed optical cells and published human optical labels have separate files. Their masked neighbours remain unknown. Never "
                "replace the existing development references in place or count an incident used for training as an independent test.","",
                "The positive-only partial urban water target means at least one homogeneous 10 m patch within a "
                "built-up 30 m cell shows newly visible water. Those cells can overlap strict training labels. "
                "Keep a separate model target and denominator. The child-count raster records the observed area. "
                "An all-unknown package contributes no training rows.","",
                "| Unit | Source / target | Positive | Known dry | Licence |",
                "| --- | --- | ---: | ---: | --- |"])
    for r in aids:
        msg.append(f"| {r['unit']} | {r['source_kind']} | {r['wet']} | {r['dry']} | {r['rights']['licence']} |")
    msg.extend(["","[Compatibility and retraining instructions](LOAD.md). Use a new registered DEV identifier, "
                "keep every tile from a flood in one split, and rebuild that identifier’s feature cache."])
    (output/"HANDOFF.md").write_text("\n".join(msg)+"\n")
    (output/"evidence_index.json").write_text(json.dumps(index,indent=2)+"\n")
    return rows


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--packages",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    handoff(args.packages,make_index(args.packages),args.out)
