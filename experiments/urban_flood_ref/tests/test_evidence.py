import csv
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import rasterio
from affine import Affine

from experiments.urban_flood_ref.package import package_event,sha

ENTRY=Path(__file__).resolve().parents[3]/"paper/evidence/urban_flood_reference/build_evidence.py"
spec=importlib.util.spec_from_file_location("evidence_cli",ENTRY)
evidence=importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class Evidence(unittest.TestCase):
    @staticmethod
    def allow(name):
        if name!="sample":
            raise ValueError("synthetic guard")
        return {"unit":name}

    def test_guard_before_io(self):
        items=[{"unit":"sample","event_id":"sample","kind":"event"},
               {"unit":"blocked","event_id":"blocked","kind":"event"}]
        with TemporaryDirectory() as d:
            out=Path(d)/"never"
            with self.assertRaisesRegex(ValueError,"synthetic guard"):
                evidence.build(Path(d)/"absent",items,out,authorize_unit=self.allow)
            self.assertFalse(out.exists())
            items=items[:1]
            items[0]["references"]=[{"name":"wrong","path":"independent/blocked/gt.tif"}]
            with self.assertRaisesRegex(ValueError,"cross-event"):
                evidence.build(Path(d),items,out,authorize_unit=self.allow)

    def test_full_build_matched_old_and_validation(self):
        grid={"crs":"EPSG:32631","shape":[1,3],"transform":[30,0,501000,0,-30,4005000]}
        state=np.repeat(np.repeat([[2,1,3]],3,axis=0),3,axis=1)
        base=state.copy()
        base[base==2]=3
        fine={"state":state,"baseline_state":base,"confidence":np.full(state.shape,.8),
              "method":np.ones(state.shape,np.uint8),"urban":np.ones(state.shape,bool)}
        meta={"event":"2021-07-27","post_date":"2021-07-27","pre_dates":["2021-07-01"],
              "acquisitions":{"post":{"track":1}}}
        with TemporaryDirectory() as d:
            root=Path(d)
            package_event(root,"sample",grid,fine,meta)
            truth=root/"independent/sample/gt.tif"
            old=root/"historical/sample/intensity.tif"
            for p,data in ((truth,[[1,0,255]]),(old,[[0,0,255]])):
                p.parent.mkdir(parents=True)
                with rasterio.open(p,"w",driver="GTiff",crs=grid["crs"],transform=Affine(*grid["transform"]),
                                   height=1,width=3,count=1,nodata=255,dtype="uint8") as src:
                    src.write(np.array(data,dtype="uint8"),1)
            receipt={"unit":"sample","event":"2021-07-27","grid":grid,"sha256":sha(old),
                     "reference":{"event_image_date":"2021-07-27","relative_orbits":[1],"event_images":1,"source":"synthetic"}}
            (old.parent/"receipt.json").write_text(json.dumps(receipt))
            index=[{"unit":"sample","event_id":"sample","kind":"event","historical":True,
                    "references":[{"name":"external","path":"independent/sample/gt.tif","date":"2021-07-29"}]}]
            out=root/"report"
            r=evidence.build(root,index,out,authorize_unit=self.allow)
            self.assertEqual(len(r),4)
            self.assertEqual(r[0]["new_ref_wet"],1)
            self.assertEqual(r[0]["reference_minus_radar_days"],2)
            with (out/"tables/legacy_comparison.csv").open() as src:
                legacy=list(csv.DictReader(src))
            self.assertEqual(legacy[0]["new_wet_over_legacy_valid_nonwet"],"1")
            self.assertEqual(legacy[1]["detector"],"archived_intensity")
            self.assertEqual(len(list((out/"figures").iterdir())),2)
            receipt["reference"]["event_image_date"]="2021-07-26"
            (old.parent/"receipt.json").write_text(json.dumps(receipt))
            evidence.build(root,index,out,authorize_unit=self.allow)
            with (out/"tables/legacy_comparison.csv").open() as src:
                self.assertEqual(list(csv.DictReader(src))[0]["reason"],"different post date")
