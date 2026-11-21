
import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon, box

from experiments.change_history.monsoon_water import polygon_membership


def test_reference_membership_includes_islands_and_excludes_holes(tmp_path):
    ring = Polygon(box(0,0,8,8).exterior.coords, [box(2,2,6,6).exterior.coords])
    island = box(3,3,5,5)
    # Include a disjoint feature marked as reference water to ensure it is skipped.
    df = gpd.GeoDataFrame({"Water_Clas":["Flood Water","Flood Water","Reference"],
                           "Sensor_ID":["RCM-1"]*3, "Sensor_Dat":["2022-06-18"]*3},
                          geometry=[ring,island,box(9,9,11,11)],crs="EPSG:4326")
    path = tmp_path / "test.shp"
    df.to_file(path)
    xy = np.array([1.,2.5,4.1,7.,9.5,12.])
    assert polygon_membership(path,df,xy,xy).tolist() == [True,False,True,True,False,False]


def test_monsoon_receipt_matches_sealed_locations_and_acquisition_cutoffs():
    import json
    from experiments.change_history.monsoon_water import MANIFEST, RESULT, ROOT, digest

    manifest = json.loads(MANIFEST.read_text())
    result = json.loads(RESULT.read_text())
    assert all(digest(ROOT / name) == h for name, h in manifest["inputs"].items())
    assert result["manifest_sha256"] == digest(MANIFEST)
    cells = result["cells"]
    assert len(cells) == len(set(manifest["cells"]))
    assert {r["id"] for r in cells} == set(manifest["cells"])
    for r in cells:
        for day in ("2022-06-18", "2022-06-30"):
            if r[day]["confirmed"] is not None:
                assert r["first_usable_in_june"] <= r[day]["confirmed"] <= day
