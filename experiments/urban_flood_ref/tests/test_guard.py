from datetime import date
import unittest
from unittest.mock import patch

from experiments.urban_flood_ref import guard


class GuardTests(unittest.TestCase):
    def test_before_fetch(self):
        row=next(x for x in guard.metadata()[0] if x['role']=='reserved')
        with patch('builtins.print') as fetch:
            with self.assertRaises(ValueError): fetch(guard.authorize(row['event_id']))
            fetch.assert_not_called()

    def test_fetch_dates(self):
        self.assertEqual(guard.authorize('usf_weihui_1')['date'],'2021-07-27')
        with self.assertRaises(ValueError): guard.authorize_window('usf_weihui_1','2021-07-27','2022-01-01')
        with self.assertRaises(ValueError): guard.authorize('../../other_scene')
        with self.assertRaises(ValueError): guard.authorize('bad_neuenahr')

    def test_links_across_aliases(self):
        geom={'type':'boxes','boxes':[{'bbox':[1,2,3,4]}]}
        orig={'geometry':geom,'products':['EMSR123:AOI01'],'basins':{'main_bas':4}}
        other={'geometry':{'type':'point_approx','point':[5,5]},'products':['EMSR123:AOI03']}
        self.assertTrue(guard.connected(orig,other))
        self.assertTrue(guard.connected(orig,{**other,'products':[],'basins':{'main_bas':4}}))
        self.assertTrue(guard.connected(orig,{**other,'products':[],'geometry':{'type':'point_approx','point':[2,3]}}))

    def test_disallow_recent_and_usa_at_source(self):
        snapshot,sites,round3=guard.metadata()
        for patch_values in ({'country':'US'},{'date':'2022-06-01'}):
            amended={**sites[0],**patch_values}
            with patch.object(guard,'metadata',return_value=(snapshot,[amended],round3)):
                with self.assertRaises(ValueError): guard.authorize(amended['unit'])
