import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from affine import Affine

from experiments.urban_flood_ref.review_consensus import consensus
from experiments.urban_flood_ref.vhr_scanline import chip


class TestVhrReference(unittest.TestCase):
    def test_scanline_returns_correct_georeferenced_window(self):
        side=100
        raw=np.zeros((side,side,3),np.uint8)
        raw[:,:,0]=np.arange(side)+1
        raw[:,:,1]=np.arange(side)[:,None]+1
        raw[:,:,2]=60
        data=raw.tobytes()
        meta={"datetime":"2019-01-04","width":side,"height":side,"crs":"EPSG:32631","local_bounds":[500000,4999950,500050,5000000]}
        layout={"width":side,"height":side,"first":0,"row_bytes":300}
        calls=[]
        with TemporaryDirectory() as out, patch("experiments.urban_flood_ref.vhr_scanline._layout",return_value=layout),patch(
            "experiments.urban_flood_ref.vhr_scanline._get",side_effect=lambda u,start,end:data[start:end+1]):
            rgb,valid=chip(meta,"fixture",meta["crs"],Affine(.5,0,500010,0,-.5,4999995),30,Path(out),lambda *a:calls.append(a))
        self.assertTrue(valid.all())
        self.assertEqual(len(calls),1)
        np.testing.assert_array_equal(rgb,raw[10:40,20:50,:].transpose(2,0,1))

    def test_disagreement_coverage_and_unknown(self):
        obs=lambda v: {"2019-01-01":{"center_raw_valid_fraction":v},"2019-02-01":{"center_raw_valid_fraction":1.}}
        sample=[{"id":x,"observed":obs(v)} for x,v in [("A",1),("B",1),("C",0.5),("D",1)]]
        a={k:[q,"specific visible cue"] for k,q in zip("ABCD",["wet","wet","dry","ambiguous"])}
        b={k:[q,"specific visible cue"] for k,q in zip("ABCD",["wet","ambiguous","dry","ambiguous"])}
        self.assertEqual([r["label"] for r in consensus(sample,a,b)],["wet","ambiguous","ambiguous","ambiguous"])
        with self.assertRaises(ValueError):
            consensus(sample,{k:v for k,v in a.items() if k!="D"},b)


if __name__=="__main__":
    unittest.main()
