"""Optional model-ready DEV labels with evidence lineage distinct from the candidate detector."""
import io
import json
from pathlib import Path

import numpy as np
import rasterio

from .evaluation import reference_array
from .guard import authorize
from .optical_catalog import _save
from .package import _blocks,check_grid,sha


def _occ_support(root,unit,grid,where):
    mask_file=where/(unit+"_nonpermanent.tif")
    crs,t,shape=check_grid(grid)
    if mask_file.is_file():
        mask=reference_array(mask_file,grid)
        if np.any(mask==0):
            raise ValueError("Occurrence support must be eligible=1 or excluded/unknown=255")
        return mask==1
    with np.load(root/"cache"/unit/(unit+"_radar_v1.npz"),allow_pickle=False) as src:
        occ=src["occ"]
    if occ.shape!=(shape[0]*3,shape[1]*3):
        raise ValueError("Occurrence surface does not nest on the reviewed grid")
    # Same project permanent-water definition. All contributing subcells
    # require a known observation history on the common lattice.
    support=_blocks(np.isfinite(occ) & (occ>=0) & (occ<80)).all(axis=-1)
    with rasterio.open(mask_file,"w",driver="GTiff",crs=crs,transform=t,height=shape[0],width=shape[1],
                       count=1,dtype="uint8",nodata=255,compress="deflate") as dst:
        dst.write(np.where(support,1,255).astype("uint8"),1)
        dst.set_band_description(1,"All 9 children observed by JRC, occurrence below 80 percent")
    return support


def label_masks(classes,support,*,positive_only):
    if (classes.shape!=support.shape or support.dtype!=bool
            or not np.isin(classes,[0,1,255]).all()):
        raise ValueError("Invalid categorical input or support")
    known=support & ((classes==1) if positive_only else (classes!=255))
    return (classes==1)&known,known


def make_sidecar(root,unit,kind):
    site=authorize(unit)
    root=Path(root)
    primary=json.loads((root/"events"/unit/"manifest.json").read_text())
    if primary["role"]!="dev" or primary["unit"]!=unit or site["date"]!=primary["event"]:
        raise ValueError("Identity mismatch between guard and primary product")
    grid=primary["grid"]
    srcdir=root/"independent"/unit
    if kind=="benchmark":
        if not unit.startswith("usf_weihui_") or site["incident"]!="henan_jul_2021":
            raise ValueError("No approved published flooded-urban benchmark")
        src,receipt=srcdir/"weihui_fu.tif",srcdir/"weihui_reference.json"
        info=json.loads(receipt.read_text())
        if (info["unit"]!=unit or info["grid"]!=grid or info["date"]!=site["date"]
                or info["licence"]!="CC BY 4.0" or not info.get("attribution")):
            raise ValueError("No verified benchmark attribution, date or model grid")
        classes=reference_array(src,grid)
        if (classes==0).any():
            raise ValueError("Published urban sidecar must contain positives or unknown only")
        # Upstream valid already required a surveyed benchmark footprint and
        # finite JRC 30 m occurrence below 80; never turn NF into dry here.
        support=np.ones(classes.shape,bool)
        observed=info["date"]
        lineage="Published shared-Sentinel-1 intensity/coherence flooded-urban class"
        interpretation="Positive-only development aid. Keep all three tiles in one storm group and exclude them from any later independent test."
        rights={"licence":"CC BY 4.0","licence_uri":"https://creativecommons.org/licenses/by/4.0/",
                "attribution":info["attribution"],"source":info["source_url"],
                "licence_source":"https://github.com/jie666-6/UrbanSARFloods#license",
                "method":info["method_url"],"change":"Cropped, area-aggregated and masked; FU-only Boolean model input."}
        folder=root/"benchmark_refs"
        folder.mkdir(exist_ok=True)
    elif kind=="reviewed":
        src,receipt=srcdir/"maxar_review.tif",srcdir/"maxar_review.json"
        info=json.loads(receipt.read_text())
        if info.get("eligible_for_dev_sidecar") is not True:
            return None
        if info.get("unit",info.get("event_id"))!=unit or not info.get("licence") or not info.get("reviewer"):
            raise ValueError("A dated reviewer identity and rights receipt are required")
        observed=info.get("acquisition_dates",{}).get("post")
        if not observed:
            raise ValueError("Reviewed label needs dated optical acquisition")
        classes=reference_array(src,grid)
        folder=root/"reviewed_refs"
        folder.mkdir(exist_ok=True)
        support=_occ_support(root,unit,grid,folder)
        lineage="Assistant visually interpreted VHR optical evidence, separate from radar"
        interpretation="Purposefully selected visible cells for development. No random sampling or independent human adjudication."
        rights={"licence":info["licence"],"licence_source":info.get("licence_url") or info.get("licence_source"),
                "source":info.get("source_urls") or info.get("source"),"attribution":info.get("attribution"),
                "reviewer":info["reviewer"],"review_status":info.get("review_status")}
        if not rights["licence_source"] or not rights["attribution"]:
            raise ValueError("Visual labels require recorded licence terms and attribution")
    else:
        raise ValueError("Unrecognised optional label source")
    wet,known=label_masks(classes,support,positive_only=kind=="benchmark")
    if not known.any():
        return None
    file=folder/(unit+".npz")
    meta={"unit":unit,"role":"dev","event":site["date"],"grid":grid,"bbox":primary["bbox"],"block":1,
          "parent_incident":site["incident"],"reference_date":observed,"source_kind":kind,
          "source":lineage,"interpretation":interpretation,"rights":rights,"raster_sha256":sha(src),
          "provenance_sha256":sha(receipt),"source_raster":str(src.relative_to(root)),
          "source_receipt":str(receipt.relative_to(root))}
    if kind=="reviewed":
        maskfile=folder/(unit+"_nonpermanent.tif")
        meta.update(nonpermanent_support=str(maskfile.relative_to(root)),nonpermanent_sha256=sha(maskfile))
    else:
        meta["permanent_water_exclusion"]="Inherited upstream JRC occurrence <80% and finite; benchmark observation support required"
    buf=io.BytesIO()
    np.savez_compressed(buf,flooded=wet,valid=known,meta=json.dumps(meta,allow_nan=False))
    _save(file,buf.getvalue())
    record={**meta,"file":str(file.relative_to(root)),"sha256":sha(file),"wet":int(wet.sum()),
            "dry":int((known & ~wet).sum()),"unknown":int((~known).sum())}
    _save(file.with_suffix(".json"),(json.dumps(record,indent=2)+"\n").encode())
    return record
