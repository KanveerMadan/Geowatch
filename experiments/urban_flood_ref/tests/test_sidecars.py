import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from affine import Affine
import numpy as np
import rasterio

from experiments.urban_flood_ref import sidecars


class Sidecars(unittest.TestCase):
    def test_positive_only_does_not_label_others(self):
        classes=np.array([[1,1,0,255]],dtype=np.uint8)
        mask=np.array([[1,0,1,1]],dtype=bool)
        wet,known=sidecars.label_masks(classes,mask,positive_only=True)
        self.assertEqual(wet.tolist(),[[True,False,False,False]])
        self.assertTrue(np.array_equal(wet,known))

    def test_review_contract_and_occurrence_support(self):
        grid={"crs":"EPSG:32631","shape":[1,4],"transform":[30,0,480000,0,-30,3000000]}
        unit="sample"
        site={"unit":unit,"date":"2020-01-07","incident":"synthetic_flood"}
        with TemporaryDirectory() as d, patch.object(sidecars,"authorize",return_value=site):
            root=Path(d)
            source=root/"independent"/unit
            source.mkdir(parents=True)
            event=root/"events"/unit
            event.mkdir(parents=True)
            cache=root/"cache"/unit
            cache.mkdir(parents=True)
            (event/"manifest.json").write_text(json.dumps({"role":"dev","unit":unit,"event":site["date"],
                                                          "grid":grid,"bbox":[0,0,1,1]}))
            review={"unit":unit,"acquisition_dates":{"pre":"2020-01-01","post":"2020-01-07"},
                    "reviewer":"two simulated readers","licence":"test terms","licence_url":"https://example.org",
                    "attribution":"simulated","eligible_for_dev_sidecar":False}
            (source/"maxar_review.json").write_text(json.dumps(review))
            self.assertIsNone(sidecars.make_sidecar(root,unit,"reviewed"))
            with rasterio.open(source/"maxar_review.tif","w",driver="GTiff",crs=grid["crs"],
                               transform=Affine(*grid["transform"]),width=4,height=1,count=1,
                               dtype="uint8",nodata=255) as ds:
                ds.write(np.array([[1,0,0,255]],dtype="uint8"),1)
            occ=np.zeros((3,12))
            occ[0,6]=80
            np.savez(cache/(unit+"_radar_v1.npz"),occ=occ)
            review["eligible_for_dev_sidecar"]=True
            (source/"maxar_review.json").write_text(json.dumps(review))
            out=sidecars.make_sidecar(root,unit,"reviewed")
            self.assertEqual((out["wet"],out["dry"],out["unknown"]),(1,1,2))
            with np.load(root/out["file"],allow_pickle=False) as z:
                self.assertEqual(z["valid"].tolist(),[[True,True,False,False]])
            # A distributed package can rebuild with the support raster alone.
            (cache/(unit+"_radar_v1.npz")).unlink()
            self.assertEqual(sidecars.make_sidecar(root,unit,"reviewed")["sha256"],out["sha256"])
