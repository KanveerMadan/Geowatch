import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import rasterio
from affine import Affine

from experiments.urban_flood_ref import evaluation as E
from experiments.urban_flood_ref import package as P
from experiments.urban_flood_ref.figures import write_map


class Products(unittest.TestCase):
    def setUp(self):
        self.grid = {"crs":"EPSG:32631","shape":[1,4],"transform":[30,0,501000,0,-30,4005000]}
        s = np.repeat(np.repeat(np.array([[1,2,3,0]],dtype=np.uint8),3,axis=1),3,axis=0)
        self.fine = {"state":s, "baseline_state":s.copy(), "confidence":np.where(s==0,np.nan,0.8),
                     "method":np.where(s==2,3,8).astype(np.uint8),"urban":np.ones(s.shape,bool)}
        self.meta = {"role":"dev","event":"2022-01-09","pre_dates":["2022-01-01","2022-01-03"],
                     "post_date":"2022-01-11","peak_date":"2022-01-09"}

    def test_package_reader_alignment_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            pre=[np.full((3,12),P._days(d)) for d in self.meta["pre_dates"]]
            report=P.package_event(out,"sample",self.grid,self.fine,self.meta,reference_dates=pre)
            ref=out/"refs/sample.npz"
            with np.load(ref,allow_pickle=False) as z:
                meta=json.loads(str(z["meta"]))
                labels=np.full((1,4),-1,dtype=np.int8)
                labels[z["valid"]]=z["flooded"][z["valid"]]
                self.assertEqual(labels.tolist(),[[0,1,-1,-1]])
                self.assertEqual(meta["grid"],self.grid)
                self.assertEqual(meta["block"],1)
            for scale in (10,30):
                with rasterio.open(out/f"events/sample/reference_{scale}m.tif") as src:
                    self.assertEqual(src.transform,Affine(scale,0,501000,0,-scale,4005000))
                    self.assertEqual(src.descriptions,P.BANDS)
                    self.assertEqual(src.tags()["date_unit"],"days since 1970-01-01 UTC")
                    self.assertEqual(src.read(11)[0,0],2)
                    self.assertEqual(src.read(8)[0,0],pre[0][0,0])
            self.assertEqual(report["counts30"]["confident_flooded"],1)
            ref.unlink()
            P.recover_reference(out,"sample")
            self.assertEqual(P.sha(ref),report["sha256"]["refs/sample.npz"])

    def test_mixed_or_missing_never_dry(self):
        self.fine["state"][0,0]=0
        self.fine["baseline_state"][0,0]=0
        self.fine["state"][1,3]=1
        f,c=P.products(self.grid,self.fine,self.meta)
        self.assertEqual(c["state"].tolist(),[[3,3,3,0]])
        self.assertTrue(np.all(f["pre_first_day"]==P.NODATA)) # multi-look, date envelope unspecified
        self.assertAlmostEqual(c["observed_fraction"][0,0],8/9,places=6)
        with self.assertRaises(ValueError):
            P.check_grid({**self.grid,"transform":[1,0,0,0,-1,0]})

    def test_against_known_cells_and_independent_grid(self):
        state=np.array([[2,3,1,0],[2,2,2,1]])
        base =np.array([[3,3,1,0],[2,1,3,1]])
        truth=np.array([[1,1,0,1],[1,0,255,0]],dtype=np.uint8)
        urban=np.ones(state.shape,bool)
        rows=E.score_arrays(state,base,urban,truth,block_cells=1)
        row=rows[0]
        self.assertEqual(row["wet_recall"],0.5)
        self.assertEqual(row["ref_wet_abstained"],2)
        self.assertEqual(row["new_wet"],3)
        self.assertEqual((row["new_ref_wet"],row["new_ref_dry"],row["new_ref_unknown"]),(1,1,1))
        self.assertAlmostEqual(row["dry_false_alarm"],1/3)
        self.assertAlmostEqual(row["paired_recall_delta"],0.25)
        self.assertIsNone(E.score_arrays(state,base,urban)[0]["wet_recall"])
        grid={**self.grid,"shape":[2,4]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.tif"
            with rasterio.open(p,"w",driver="GTiff",width=4,height=2,count=1,dtype="uint8",
                               transform=Affine(*grid["transform"]),crs=grid["crs"],nodata=255) as ds:
                ds.write(truth,1)
            self.assertTrue(np.array_equal(E.reference_array(p,grid),truth))
            with self.assertRaises(ValueError):
                E.reference_array(p,{**grid,"transform":[30,0,501010,0,-30,4005000]})
            svg=Path(d)/"test.svg"
            write_map(svg,"A & B",state,base,urban,truth,grid,"optical")
            import xml.etree.ElementTree as ET
            root=ET.parse(svg).getroot()
            self.assertEqual(len(root.findall("{http://www.w3.org/2000/svg}image")),4)
