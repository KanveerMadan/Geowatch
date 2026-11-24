"""Write sparse visible-surface VHR labels on the exact flood-model grid."""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

from .grid import grid30
from .guard import authorize_window
from .optical_catalog import _save
from .vhr_reference import LICENCE, TERMS


def consensus(sample, review_a, review_b):
    expected={r["id"] for r in sample}
    if expected!=set(review_a) or expected!=set(review_b) or len(expected)!=len(sample):
        raise ValueError("Every selected cell requires two unique blind readings")
    outcome=[]
    for row in sample:
        first,second=review_a[row["id"]],review_b[row["id"]]
        votes=[first[0],second[0]]
        if any(v not in ("wet","dry","ambiguous") for v in votes) or not first[1] or not second[1]:
            raise ValueError("Invalid review entry")
        same=votes[0]==votes[1] and votes[0]!="ambiguous"
        mask=row["observed"]
        # No-data inside the reference cell must be separately shown as source coverage.
        complete=all(obs["center_raw_valid_fraction"]==1.0 for obs in mask.values())
        state=votes[0] if same and complete else "ambiguous"
        outcome.append({**row,"review_a":first,"review_b":second,"label":state})
    return outcome


def build(root, unit, sample_file, first_file, second_file, radar_date, *, filename="maxar_review"):
    # Unit before any local source file, then check the exact acquisition dates.
    from .guard import authorize
    site=authorize(unit)
    sample=json.loads(Path(sample_file).read_text())
    if sample["unit"]!=unit: raise ValueError("VHR sample identity mismatch")
    pre,post=sample["pre_date"],sample["post_date"]
    authorize_window(unit,pre,post)
    if radar_date:
        authorize_window(unit,radar_date,radar_date)
    a,b=[json.loads(Path(x).read_text()) for x in (first_file,second_file)]
    if a["reviewer"]==b["reviewer"] or not a["blind_to_detector"] or not b["blind_to_detector"]:
        raise ValueError("Distinct readings blinded to detection required")
    rows=consensus(sample["cells"],a["cells"],b["cells"])
    grid=grid30(unit);out=np.full(grid["shape"],255,"uint8")
    for cell in rows:
        if not (0<=cell["row"]<out.shape[0] and 0<=cell["col"]<out.shape[1]):
            raise ValueError("VHR sample outside registered grid")
        out[cell["row"],cell["col"]]={"dry":0,"wet":1,"ambiguous":255}[cell["label"]]
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    evidence_urls=sorted({url for cell in rows for d in cell["observed"].values() for url in d["assets"]})
    record={"unit":unit,"incident":site["incident"],"grid":grid,"acquisition_dates":{"pre":pre,"post":post},
            "radar_date":radar_date,"reviewer":a["reviewer"]+" and "+b["reviewer"],"review_status":"Two separately blinded assistant interpretations. No independent human adjudication.",
            "class_rule":"WET: newly visible connected standing water over most of the 30 m cell. DRY: most of cell clearly exposed and non-water, no visible flooding. Clouds, roofs, canopy, shadow, mixed or unclear surfaces abstain.",
            "eligible_for_dev_sidecar": False,
            "eligibility_basis":"Research diagnostic only. Separately interpreted assistant votes do not establish adjudicated ground truth or training eligibility.",
            "licence":"CC BY-NC 4.0 — non-commercial research only","licence_url":TERMS,
            "licence_uri":LICENCE,"attribution":"Imagery © Maxar Technologies, Maxar Open Data Program; derived visual interpretation by GeoWatch.",
            "source_urls":evidence_urls,"source_distributed":False,
            "limitations":["Labels describe visible conditions at optical acquisition, with no claim about the storm peak.",
             "Both reviewers are AI assistants, with correlated interpretation errors. Source independence comes from the different optical sensor.",
             "Only agreed visible open surfaces can receive a label. Hidden urban streets stay unknown.",
             "Narrow roads, building interiors, point-level debris or damage do not label an entire cell flooded or dry."],
            "selection":sample["design"],"pixel_counts":{str(v):int((out==v).sum()) for v in (0,1,255)},"cells":rows}
    with rasterio.open(root/(filename+".tif"),"w",driver="GTiff",height=out.shape[0],width=out.shape[1],count=1,
                       dtype="uint8",crs=grid["crs"],transform=Affine(*grid["transform"]),nodata=255,compress="deflate") as ds:
        ds.write(out,1)
    _save(root/(filename+".json"),json.dumps(record,indent=2).encode())
    return record


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("unit");p.add_argument("--sample",type=Path,required=True)
    p.add_argument("--first",type=Path,required=True);p.add_argument("--second",type=Path,required=True)
    p.add_argument("--radar-date",required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    print(build(args.output,args.unit,args.sample,args.first,args.second,args.radar_date)["pixel_counts"])
