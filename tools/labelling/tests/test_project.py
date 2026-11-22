"""Real PyQGIS round-trip and immutable inputs, using fabricated training imagery."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from labelling.label_style import empty_labels_gdf
from tools.labelling.guard import ROOT

GENERATOR = Path(__file__).resolve().parents[1] / "project.py"


def make_scene(folder):
    """An artificial training-location fixture; all pixels and example polygons are invented."""
    tile = folder / "PRACTICE_formal"
    tile.mkdir(parents=True)
    meta = ROOT / "data/practice_tiles/PRACTICE_formal/metadata.json"
    shutil.copyfile(meta, tile / "metadata.json")
    g = json.loads(meta.read_text())["tile_utm"]
    x, top = g["x0"], g["y1"]
    crs = g["crs"]
    outline = box(x, top - 200, x + 200, top)
    gpd.GeoDataFrame({"tile_id":[tile.name]},geometry=[outline],crs=crs).to_file(tile/"tile.geojson")
    empty_labels_gdf(crs).to_file(tile/"labels.gpkg", layer="labels", geometry_type="Polygon")
    # A deliberate sample of roofs, roads and vegetation gives the UI screenshot
    # recognisable boundaries without writing a third-party aerial to the repo.
    rng = np.random.default_rng(40)
    n = 800
    rgb = np.full((n,n,3), (166,155,124), dtype=np.int16)
    def rect(x1, y1, x2, y2, colour):
        rgb[y1*4:y2*4, x1*4:x2*4] = colour
    rect(0,90,200,104,(105,108,109))
    rect(76,0,86,200,(112,114,114))
    trees = [(16,32),(32,62),(59,37),(52,73),(144,36),(167,72),(98,155),(159,166),(22,126),(64,149)]
    y_px,x_px=np.ogrid[:n,:n]
    for xx,yy in trees:
        rgb[(x_px-4*xx)**2+(y_px-4*yy)**2 < 34**2] = (75,108,65)
    roofs = [(22,12,42,24),(48,50,65,62),(96,12,116,27),(141,47,159,62),
             (123,63,140,81),(18,145,34,162),(46,123,62,135),(114,123,131,139),
             (142,134,156,144),(168,157,185,172)]
    for i,(a,b,c,d) in enumerate(roofs):
        rect(a+2,b+2,c+2,d+2,(88,81,71))
        rect(a,b,c,d,((191,132,111),(192,189,172),(155,161,162))[i%3])
        rect(a,(b+d)//2,c,(b+d)//2+1,(163,150,138))
    rgb += rng.integers(-8,9,size=(n,n,1),dtype=np.int16)
    with rasterio.open(tile/"hr.tif","w",driver="GTiff",width=n,height=n,count=3,
                       dtype="uint8",transform=from_origin(x,top,.25,.25),crs=crs) as image:
        image.write(rgb.clip(0,255).astype("uint8").transpose(2,0,1))
    def write(layer, label, rects, hint):
        geometries = [box(x+a,top-d,x+c,top-b) for a,b,c,d in rects]
        rows = [dict(candidate_id=f"test-{layer}-{i}",source_id=str(i),source="Synthetic QA",
                     source_version="1",confidence=None,needs_check=1,hint_only=hint,
                     note="Synthetic practice fixture",**{"class":label}) for i in range(len(rects))]
        gpd.GeoDataFrame(rows,geometry=geometries,crs=crs).to_file(tile/"prelabels.gpkg",layer=layer)
    write("built_open_buildings","built",roofs,0)
    write("paved_osm","paved",[(0,90,200,104),(76,0,86,90),(76,104,86,200)],0)
    write("shadow_rgb","shadow_full",[(3,4,15,18)],1)
    return tile


def qgis_python():
    configured = os.environ.get("GEOWATCH_QGIS_PYTHON")
    if configured:
        return configured
    mac = Path("/Applications/QGIS.app/Contents/MacOS/python")
    if mac.is_file():
        return str(mac)
    pytest.importorskip("qgis.core", reason="PyQGIS required for project round-trip")
    return sys.executable


def test_qgis_project_round_trip(tmp_path):
    exe = qgis_python()
    tile = make_scene(tmp_path)
    initial = {f.name: hashlib.sha256(f.read_bytes()).digest() for f in tile.iterdir()}
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT))
    run = subprocess.run([exe,str(GENERATOR),str(tile)],env=env,capture_output=True,text=True)
    assert run.returncode == 0, run.stderr
    with zipfile.ZipFile(tile/"label_project.qgz") as archive:
        tree=ET.fromstring(archive.read(next(s for s in archive.namelist() if s.endswith(".qgs"))))
    layers=tree.findall("projectlayers/maplayer")
    assert len(layers)==6
    assert all(v.findtext("datasource").startswith("./") for v in layers)
    assert tree.find("projectCrs/spatialrefsys/authid").text=="EPSG:32734"
    by_name={v.findtext("layername"):v for v in layers}
    final=by_name["Final labels"]
    assert final.find("renderer-v2").get("attr")=="label"
    assert final.find("fieldConfiguration/field[@name='label']/editWidget").get("type")=="ValueMap"
    assert "prelabel_kept" in final.find("labeling/settings/text-style").get("fieldName")
    assert tree.find(".//layer-tree-group[@name='Hints only']").get("checked")=="Qt::Unchecked"
    assert tree.find(".//layer-tree-group[@name='Hints only']/layer-tree-layer[@name='shadow rgb']") is not None
    assert tree.find(".//snapping-settings").get("enabled")=="1"
    assert "Whole tile" in ET.tostring(tree.find("Bookmarks"),encoding="unicode")
    assert initial == {f.name:hashlib.sha256(f.read_bytes()).digest() for f in tile.iterdir() if f.suffix!=".qgz"}
    run = subprocess.run([exe,str(GENERATOR),str(tile)],env=env,capture_output=True,text=True)
    assert run.returncode and "FileExistsError" in run.stderr
