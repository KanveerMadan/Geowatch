"""Midland-only access, observation masks and four-state payload invariants."""
import hashlib
import json
import unittest

import numpy as np

from midland_reference import AFTER, BANDS, BEFORE, CODES, HERE, INCIDENT, allow_pair, classify


class MidlandTests(unittest.TestCase):
    def test_dev_firewall(self):
        row={"incident_id":INCIDENT,"split":"DEV","date":"2020-05-19","screening":"timed_footprint"}
        scene={"scene":"LC08_L2SP_021030_20200520_02_T1","utc":"2020-05-20T16:21:46Z"}
        allow_pair(row,scene)
        for key,val in [("split","reserve_candidate"),("date","2022-05-19"),("incident_id","other_incident")]:
            with self.assertRaises(ValueError):
                allow_pair({**row,key:val},scene)
        with self.assertRaises(ValueError):
            allow_pair(row,{**scene,"utc":"2024-05-20T16:00:00Z"})

    def test_observation_states(self):
        pixel={}
        for prefix in ("before_","after_"):
            for b,val in zip(BANDS,[9000,11000,11000,12000,64,0]):
                pixel[prefix+b]=np.full(12,val)
        pixel.update(cover=np.full(12,82),history=np.full(12,100),occurrence=np.zeros(12))
        pixel["after_SR_B3"][[0,2,3,9]]=15000
        pixel["after_QA_PIXEL"][[0,2,9]] |= 128
        pixel["after_QA_PIXEL"][2] |= 8
        pixel["before_QA_PIXEL"][4] |= 32
        pixel["occurrence"][5]=80
        pixel["history"][6]=0
        pixel["cover"][7]=42
        pixel["after_QA_RADSAT"][8]=1
        pixel["before_QA_PIXEL"][9] |= 128
        pixel["before_SR_B5"][10]=26000
        pixel["after_SR_B4"][11]=-1
        np.testing.assert_equal(classify(pixel),[2,1,0,3,0,0,0,0,0,3,3,0])

    def test_shipped_reference(self):
        base=HERE/"dev_references"
        meta=json.loads((base/"midland_2020.json").read_text())
        p=base/"midland_2020.npz"
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),meta["sha256"])
        with np.load(p,allow_pickle=False) as d:
            state=d["state"]
            self.assertEqual(json.loads(d["meta"].item()),meta["meta"])
            self.assertEqual(meta["meta"]["before"],BEFORE)
            self.assertEqual(meta["meta"]["after"],AFTER)
            self.assertEqual(state.shape,tuple(meta["meta"]["grid"]["shape"]))
            self.assertEqual(state.dtype,np.uint8)
            np.testing.assert_equal(d["valid"],np.isin(state,[1,2]))
            np.testing.assert_equal(d["flooded"],state==2)
            self.assertEqual({k:int(np.sum(state==v)) for k,v in CODES.items()},meta["counts"])


if __name__=="__main__":
    unittest.main()
