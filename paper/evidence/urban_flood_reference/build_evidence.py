"""Generate reproducible DEV evidence from an explicit, guard-checked index."""
import argparse
import csv
from datetime import date
import json
from pathlib import Path
import re
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO))

from experiments.urban_flood_ref.evaluation import event_arrays, reference_array, score_arrays
from experiments.urban_flood_ref.figures import write_map
from experiments.urban_flood_ref.guard import authorize
from experiments.urban_flood_ref.package import sha


def csv_out(path, rows, empty_fields):
    with path.open("w",newline="") as dst:
        writer = csv.DictWriter(dst,lineterminator="\n",fieldnames=list(dict.fromkeys(k for row in rows for k in row)) if rows else empty_fields)
        writer.writeheader()
        writer.writerows(rows)


def safe(root, relative):
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Expected a relative package path")
    p = root/relative
    if p.resolve()!=p or not p.is_file():
        raise ValueError(f"Expected a regular, non-symlinked package file: {relative}")
    return p


def checked(index, authorize_unit):
    if not isinstance(index,list):
        raise ValueError("Index must be a list of eligible products")
    units = set()
    for item in index:
        event,unit,kind = item["event_id"],item["unit"],item["kind"]
        record = authorize_unit(event)
        if record["unit"] != event or unit in units:
            raise ValueError("Duplicate or mismatched approved identity")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*",unit):
            raise ValueError("Unsafe package name")
        if kind == "event" and unit != event:
            raise ValueError("Mismatched incident package")
        if kind == "pre_event_control" and unit != event+"_control":
            raise ValueError("Mismatched control package")
        if kind not in ("event","pre_event_control"):
            raise ValueError("Invalid package kind")
        units.add(unit)
        names=set()
        for ref in item.get("references",[]):
            p=Path(ref["path"])
            if (len(p.parts)!=3 or tuple(p.parts[:2])!=("independent",event)
                    or (kind=="pre_event_control" and p.name!="s2_control.tif")
                    or (kind=="event" and p.name=="s2_control.tif")
                    or p.suffix!=".tif" or ref["name"] in names):
                raise ValueError("Invalid, duplicate or cross-event independent reference")
            names.add(ref["name"])
    return index


def build(root, index, out, *, authorize_unit=authorize):
    checked(index,authorize_unit)  # guard the whole index before opening any event
    root,out = Path(root).resolve(),Path(out)
    out.mkdir(parents=True,exist_ok=True)
    for part in ("tables","figures"):
        (out/part).mkdir(exist_ok=True)
    rows,counts,sources,figures,legacy_rows,partial_rows = [],[],[],[],[],[]
    for item in index:
        event,unit,kind = item["event_id"],item["unit"],item["kind"]
        manifest_path=safe(root,f"events/{unit}/manifest.json")
        manifest=json.loads(manifest_path.read_text())
        if manifest["role"]!="dev" or manifest["unit"]!=unit:
            raise ValueError("Package manifest does not match the guarded unit")
        sources.append({"unit":unit,"kind":kind,"role":"package provenance","file":str(manifest_path.relative_to(root)),
                        "sha256":sha(manifest_path),"date":manifest["post_date"],"provenance":manifest.get("rights","")})
        for name in ("reference_30m.tif","reference_10m.tif","model_ref.npz"):
            rel=f"events/{unit}/{name}"
            p=safe(root,rel)
            expected=manifest["sha256"][rel]
            if sha(p)!=expected:
                raise ValueError("Archived product checksum mismatch")
            sources.append({"unit":unit,"kind":kind,"role":"radar-derived product","file":rel,"sha256":expected,
                            "date":manifest["post_date"],"provenance":manifest.get("lineage") or json.dumps(manifest.get("sources",[]))})
        model_path=f"refs/{unit}.npz"
        if sha(safe(root,model_path))!=manifest["sha256"][model_path]:
            raise ValueError("Model reference checksum mismatch")
        sources.append({"unit":unit,"kind":kind,"role":"model input","file":model_path,
                        "sha256":manifest["sha256"][model_path],"date":manifest["post_date"],
                        "provenance":"flooded and valid masks; human review pending"})
        state,base,urban,grid=event_arrays(safe(root,f"events/{unit}/reference_30m.tif"))
        if grid!=manifest["grid"]:
            raise ValueError("Packaged raster and manifest grid disagree")
        historical=None
        oldmeta=None
        if item.get("historical"):
            if kind!="event":
                raise ValueError("An incident intensity archive is not a dry-control comparator")
            receipt=safe(root,f"historical/{unit}/receipt.json")
            oldmeta=json.loads(receipt.read_text())
            rel=f"historical/{unit}/intensity.tif"
            p=safe(root,rel)
            olddate=oldmeta["reference"]["event_image_date"]
            tracks=oldmeta["reference"]["relative_orbits"]
            track=manifest.get("acquisitions",{}).get("post",{}).get("track")
            reason=None
            if (oldmeta["unit"]!=unit or oldmeta["event"]!=manifest["event"]
                    or oldmeta["sha256"]!=sha(p)):
                raise ValueError("Legacy receipt/identity mismatch")
            if oldmeta["grid"]!=grid:
                reason="different grid"
            elif olddate!=manifest["post_date"]:
                reason="different post date"
            elif tracks!=[track] or oldmeta["reference"].get("event_images")!=1:
                reason="multiple or different legacy tracks/scenes"
            if reason:
                legacy_rows.append({"unit":unit,"comparison":"unmatched","reason":reason,
                                    "legacy_date":olddate,"post_date":manifest["post_date"],
                                    "legacy_tracks":str(tracks),"post_track":track})
            else:
                historical=reference_array(p,grid)
            sources.append({"unit":unit,"kind":kind,"role":"legacy provenance","file":str(receipt.relative_to(root)),
                            "sha256":sha(receipt),"date":olddate,"provenance":oldmeta.get("licence","")})
            sources.append({"unit":unit,"kind":kind,"role":"archived radar comparator","file":rel,"sha256":oldmeta["sha256"],
                            "date":olddate,"provenance":oldmeta["reference"]["source"]})
        if kind=="event":
            for directory in ("reviewed_refs","benchmark_refs","manual_refs","partial_water_refs"):
                spath=f"{directory}/{unit}.npz"
                receipt_path=f"{directory}/{unit}.json"
                if "optional_dev_labels" in item and spath not in item["optional_dev_labels"]:
                    continue
                if not (root/receipt_path).is_file():
                    continue
                rr=safe(root,receipt_path)
                side=json.loads(rr.read_text())
                if directory in ("manual_refs","partial_water_refs"):
                    from experiments.urban_flood_ref.handoff import read_manual_labels
                    side=read_manual_labels(root,unit,manifest,item.get("incident"),partial=directory=="partial_water_refs")
                    if not side:
                        continue
                if (side["unit"]!=unit or side.get("role","dev")!="dev" or side.get("grid",grid)!=grid
                        or side["sha256"]!=sha(safe(root,spath))):
                    raise ValueError("Optional label archive failed identity or digest check")
                if directory=="partial_water_refs":
                    partial_rows.append({"unit":unit,"incident":item.get("incident"),"source_date":side["reference_date"],
                                         "positive_neighbourhoods":side["wet"],"confirmed_wet_10m_cells":side["confirmed_wet_children"],
                                         "unknown":side["unknown"],"source":side["source_raster"],"label_file":spath})
                    sources.append({"unit":unit,"kind":kind,"role":"optional partial urban water count raster",
                                    "file":side["source_raster"],"sha256":side["source_raster_sha256"],
                                    "date":side["reference_date"],"provenance":side["definition"]})
                for resource in (spath,receipt_path):
                    sources.append({"unit":unit,"kind":kind,"role":side["source_kind"]+" DEV input",
                                    "file":resource,"sha256":sha(safe(root,resource)),"date":side["reference_date"],
                                    "provenance":side["rights"]["licence"]})
                if side.get("nonpermanent_support"):
                    support=side["nonpermanent_support"]
                    if support!=f"reviewed_refs/{unit}_nonpermanent.tif" or sha(safe(root,support))!=side["nonpermanent_sha256"]:
                        raise ValueError("Invalid permanent-water support for reviewed labels")
                    sources.append({"unit":unit,"kind":kind,"role":"reviewed label JRC exclusion",
                                    "file":support,"sha256":side["nonpermanent_sha256"],"date":"",
                                    "provenance":"EC JRC/Google Global Surface Water 1.4"})
        refs=item.get("references",[])
        for j,ref in enumerate(refs or [None]):
            truth = None
            refname = "No independent reference"
            role,refdate,gap = "none","",None
            if ref:
                p=safe(root,ref["path"])
                truth=reference_array(p,grid)
                refname=ref["name"]
                role=ref.get("role","visible-surface comparator")
                refdate=ref.get("date","")
                if refdate:
                    gap=(date.fromisoformat(refdate)-date.fromisoformat(manifest["post_date"])).days
                if ref.get("receipt"):
                    record=Path(ref["receipt"])
                    if record.parent!=Path(ref["path"]).parent or record.suffix!=".json":
                        raise ValueError("Independent reference receipt belongs to a different product")
                    rpath=safe(root,record)
                    if not any(s["file"]==ref["receipt"] for s in sources):
                        sources.append({"unit":unit,"kind":kind,"role":"external provenance","file":ref["receipt"],
                                        "sha256":sha(rpath),"date":refdate,"provenance":role})
                sources.append({"unit":unit,"kind":kind,"role":role,"file":ref["path"],"sha256":sha(p),
                                "date":refdate,"provenance":ref.get("source","")})
            data=score_arrays(state,base,urban,truth)
            for row in data:
                timing=("date unavailable" if gap is None else
                        "same UTC date" if gap==0 else "different UTC dates")
                rows.append({"unit":unit,"event_id":event,"kind":kind,"reference":refname,"timing":timing,
                             "reference_role":role,"reference_date":refdate,"reference_minus_radar_days":gap,**row})
                if j==0:
                    cols=("stratum","detector","total","observed","classified","ambiguous","unobserved",
                          "wet","dry","new_wet","new_over_baseline_dry","lost_baseline_wet","coverage",
                          "wet_share_observed","wet_share_observed_lo","wet_share_observed_hi")
                    counts.append({"unit":unit,"event_id":event,"incident":item.get("incident",event),"kind":kind,**{k:row[k] for k in cols}})
            if historical is not None:
                legacy_state=np.select([historical==0,historical==1],[1,2],default=0)
                legacy_data=score_arrays(state,legacy_state,urban,truth)
                for lr in legacy_data:
                    domain=urban.astype(bool) if lr["stratum"]=="urban" else np.ones(state.shape,bool)
                    new_on_old_dry=domain & (state==2) & (historical==0)
                    legacy_rows.append({"unit":unit,"comparison":"same post date, same single track and grid",
                                        "reference":refname,"reference_role":role,"reference_date":refdate,
                                        "post_date":manifest["post_date"],"legacy_date":oldmeta["reference"]["event_image_date"],
                                        **lr,"detector":("archived_intensity" if lr["detector"]=="intensity_only" else lr["detector"]),
                                        "new_wet_over_legacy_valid_nonwet":int(new_on_old_dry.sum()),
                                        "new_wet_over_legacy_unknown":int((domain & (state==2) & (historical==255)).sum())})
                histfig=f"figures/{unit}_{j+1}_historical.svg"
                write_map(out/histfig,unit.replace("_"," ")+" · archive comparison",state,legacy_state,urban,
                          truth,grid,refname,baseline_title="Archived VV drop")
                figures.append({"unit":unit,"kind":kind,"reference":refname,"figure":histfig})
            figure=f"figures/{unit}_{j+1}.svg"
            write_map(out/figure,unit.replace("_"," "),state,base,urban,truth,grid,refname)
            figures.append({"unit":unit,"kind":kind,"reference":refname,"figure":figure})
    csv_out(out/"tables/agreement.csv",rows,["unit","event_id","kind","reference","stratum","detector",
                                           "ref_wet","ref_dry","wet_recall","dry_false_alarm"])
    csv_out(out/"tables/coverage_and_additions.csv",counts,["unit","kind","stratum","detector","new_wet"])
    csv_out(out/"tables/legacy_comparison.csv",legacy_rows,["unit","comparison","reason","reference","stratum","detector"])
    csv_out(out/"tables/partial_water_presence.csv",partial_rows,["unit","incident","source_date","positive_neighbourhoods",
                                                                 "confirmed_wet_10m_cells","unknown","source","label_file"])
    csv_out(out/"tables/figures.csv",figures,["unit","kind","reference","figure"])
    csv_out(out/"data_manifest.csv",sources,["unit","kind","role","file","sha256","date","provenance"])
    write_results(out/"RESULTS.md",counts,rows,legacy_rows)
    return rows


def write_results(path,counts,agreement,legacy):
    events=[r for r in counts if r["kind"]=="event" and r["stratum"]=="urban" and r["detector"]=="urban_detector"]
    controls=[r for r in counts if r["kind"]!="event" and r["stratum"]=="urban" and r["detector"]=="urban_detector"]
    total=lambda rows,key:sum(r[key] for r in rows)
    lines=["# Development results","",
           f"The {len(events)} event tiles from {len({r['incident'] for r in events})} distinct incidents contain "
           f"{total(events,'wet'):,} confidently mapped urban wet cells. "
           f"{total(events,'new_wet'):,} were absent from the matched intensity-only map. "
           f"The urban area contains {total(events,'dry'):,} confidently dry cells, "
           f"{total(events,'ambiguous'):,} ambiguous and {total(events,'unobserved'):,} excluded or unobserved cells.","",
           f"Across {len(controls)} earlier control tiles from {len({r['incident'] for r in controls})} incident locations, "
           f"the detector flagged {total(controls,'wet'):,} of "
           f"{total(controls,'observed'):,} observed urban cells as wet. "
           f"It classified {total(controls,'dry'):,} as confidently dry. The dates are nominal controls; "
           "independently observed non-water appears below only where available.","",
           "## Urban flood benchmark recovery","",
           "| Tile | Benchmark urban-flood cells | New detector | Matched darkening | Archived VV-drop |",
           "| --- | ---: | ---: | ---: | ---: |"]
    for row in agreement:
        if row["reference"]!="Flooded urban" or row["stratum"]!="all" or row["detector"]!="urban_detector":
            continue
        match=next(r["tp"] for r in agreement if r["unit"]==row["unit"] and r["reference"]==row["reference"]
                   and r["stratum"]=="all" and r["detector"]=="intensity_only")
        old=next((r["tp"] for r in legacy if r["unit"]==row["unit"] and r.get("reference")==row["reference"]
                  and r["stratum"]=="all" and r["detector"]=="archived_intensity"),"unavailable")
        lines.append(f"| {row['unit']} | {row['ref_wet']} | {row['tp']} | {match} | {old} |")
    lines.extend(["","The Weihui tiles cover one event. The external benchmark and the candidate both use SAR. "
                  "The benchmark's flooded-urban denominator includes all such cells, including those outside "
                  "the candidate’s own urban mask.","","## Checks with optical evidence","",
                  "Counts cover the detector’s urban stratum. Each row gives detected/reference counts for two "
                  "observed classes. An empty or zero denominator leaves that measure unresolved.","",
                  "| Unit | Evidence | Flagged / known wet | Flagged / known non-water |",
                  "| --- | --- | ---: | ---: |"])
    for row in agreement:
        if ("Independent sensor" in row["reference_role"] and row["stratum"]=="urban"
                and row["detector"]=="urban_detector"):
            lines.append(f"| {row['unit']} | {row['reference']} | {row['tp']}/{row['ref_wet']} | {row['fp']}/{row['ref_dry']} |")
    optical=[r for r in agreement if r["reference_role"] in ("Independent sensor, published human optical interpretation",
                                                            "Independent sensor, assistant visual interpretation")
             and r["stratum"]=="all" and r["detector"]=="urban_detector"]
    if optical:
        lines.extend(["","## Independent optical interpretation across the whole footprint","",
                      "These counts also include visible surfaces outside the study's built-up mask. "
                      "Compare the corresponding urban-only denominators above before drawing conclusions about streets.","",
                      "| Unit | Evidence | Detected / observed wet | Flagged / observed dry | Optical minus radar days |",
                      "| --- | --- | ---: | ---: | ---: |"])
        for r in optical:
            lines.append(f"| {r['unit']} | {r['reference']} | {r['tp']}/{r['ref_wet']} | {r['fp']}/{r['ref_dry']} | {r['reference_minus_radar_days']} |")
    lines.extend(["","[Per-event intervals and reference timing](tables/agreement.csv). "
                  "[Exact historical comparisons and reasons for unmatched acquisitions](tables/legacy_comparison.csv)."])
    path.write_text("\n".join(lines)+"\n")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packages",type=Path,required=True)
    ap.add_argument("--index",type=Path,required=True)
    ap.add_argument("--out",type=Path,default=Path(__file__).resolve().parent)
    args=ap.parse_args()
    build(args.packages,json.loads(args.index.read_text()),args.out)


if __name__=="__main__":
    main()
