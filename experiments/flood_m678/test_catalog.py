"""Offline checks for the metadata firewall, timing rules, and committed receipts."""
import csv
import json
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from shapely.geometry import Point, box

from discover import ARCHIVES
from gauge_crests import bracket
from overlap import conflicts
from screen_acquisitions import HERE, crest_interval, radar_pair, screen


class CatalogTests(unittest.TestCase):
    def test_publisher_files(self):
        self.assertEqual({v[1] for v in ARCHIVES.values()},
                         {"Global_Flood_Records.csv","glofdatabase_v4-2.ods"})
        with (HERE/"source_leads.csv").open() as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len({r["source_row"] for r in rows}),len(rows))
        self.assertNotIn("glof-v4.2:2",{r["source_row"] for r in rows})
        self.assertNotIn("glof-v4.2:3",{r["source_row"] for r in rows})
        self.assertTrue(all(r["coordinate_role"] in {"country_only","lake_source"} for r in rows))

    def test_calendar_interval_uses_local_dst(self):
        lo,hi=crest_interval("2021-03-14","America/Chicago")
        self.assertEqual(hi-lo,timedelta(hours=23))

    def test_gauge_ties_and_gaps(self):
        lo=datetime(2020,1,1,tzinfo=timezone.utc)
        def obs(i,value):
            return {"properties":{"time_series_id":"a","unit_of_measure":"ft","time":(lo+timedelta(minutes=i)).isoformat(),
                    "value":value,"parameter_code":"00065","approval_status":"Approved","qualifier":None}}
        series=[obs(i,v) for i,v in enumerate([1,3,2.99,3,1])]
        end=lo+timedelta(minutes=4)
        r=bracket(series,lo,end)
        self.assertEqual((r["start"],r["end"]),(lo.isoformat(),end.isoformat()))
        self.assertEqual(bracket(series[:2]+series[3:],lo,end)["status"],"gap_in_gauge_record")
        self.assertEqual(bracket([],lo,end)["status"],"no_unambiguous_approved_series")

    def test_radar_pair(self):
        a={"mode":"IW","orbit":7,"direction":"ascending","pol":["VV"]}
        self.assertTrue(radar_pair(a,a))
        for key,value in [("orbit",8),("direction","descending"),("mode","EW"),("pol",["HH"])]:
            self.assertFalse(radar_pair(a,{**a,key:value}))

    def test_overlap(self):
        area=box(-96.81,46.84,-96.76,46.90)
        self.assertTrue(conflicts(area,Point(-96.79,46.86)))
        self.assertTrue(conflicts(area,Point(-96.90,46.86)))
        self.assertFalse(conflicts(area,Point(-97.90,46.86)))

    def test_screen_enforces_entire_uncertain_peak(self):
        site=dict(zone="UTC",longitude=-84,latitude=44,type="M7",subtype="dam")
        event=dict(date="2020-05-19",crest_date="2020-05-20")
        def query_stub(session,cache,collection,box,start,end):
            if collection!="landsat-c2-l2":
                return []
            return [dict(id=s,utc=s,collection=collection) for s in
                    ("2020-05-19T12:00:00Z","2020-05-20T12:00:00Z","2020-05-21T12:00:00Z")]
        with patch("screen_acquisitions.query",side_effect=query_stub):
            receipt=screen(event,site,{},None,None)
        self.assertEqual([x["scene"] for x in receipt["scenes"]],["2020-05-20T12:00:00Z","2020-05-21T12:00:00Z"])
        with patch("screen_acquisitions.query",side_effect=query_stub):
            receipt=screen({**event,"not_before_utc":"2020-05-21T00:00:00+00:00"},site,{},None,None)
        self.assertEqual([x["scene"] for x in receipt["scenes"]],["2020-05-21T12:00:00Z"])

    def test_committed_receipts_reconcile(self):
        with (HERE/"catalog.csv").open() as f:
            rows=list(csv.DictReader(f))
        receipts=json.loads((HERE/"scene_metadata.json").read_text())
        self.assertEqual(len({r["incident_id"] for r in rows}),len(rows))
        for row in rows:
            self.assertEqual(row["split"],"DEV" if row["date"]<"2022-01-01" else "reserve_candidate")
            data=receipts.get(row["incident_id"])
            if not data:
                self.assertEqual(row["optical_scenes"],"")
                continue
            scenes=data["scenes"]
            counts=Counter("optical" if s["collection"]!="sentinel-1-grd" else
                           "radar" if s["baseline"] else "no_baseline" for s in scenes)
            self.assertEqual(counts["optical"],int(row["optical_scenes"]))
            self.assertEqual(counts["radar"],int(row["paired_radar_scenes"]))
            self.assertEqual(counts["radar"]+counts["optical"]>0,row["screening"]=="timed_footprint")
            for s in scenes:
                self.assertGreaterEqual(s["lag_hours_min"],-24)
                maximum=72 if row["type"]=="M8" and "ice jam" not in row["subtype"] else 48
                self.assertLessEqual(s["lag_hours_max"],maximum)
                self.assertNotIn("assets",s)


if __name__=="__main__":
    unittest.main()
