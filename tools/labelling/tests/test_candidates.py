import json
from pathlib import Path

import numpy as np
import pyogrio
import pytest
import rasterio
from affine import Affine
from rasterio.io import MemoryFile
from shapely.geometry import Polygon, box

from tools.labelling import generate as gen
from tools.labelling.candidate_imagery import _imagery_candidates, rgb_masks
from tools.labelling.candidate_sources import _map_elements, _osm_features, _suggest


def test_buffer_width_unpaved_and_closed_roundabout():
    pts = [{"lon":0,"lat":0},{"lon":10,"lat":0}]
    road = dict(type="way",id=1,version=3,tags={"highway":"residential","width":"12 ft"},geometry=pts)
    mapped = _osm_features([road],lambda x,y:(x,y))
    assert mapped[0]["geometry"].area == pytest.approx(10 * 12 * .3048)
    assert mapped[0]["source_id"] == "way/1" and mapped[0]["needs_check"] == 1
    for tags in ({"highway":"residential","surface":"compacted"},{"highway":"footway"},{"highway":"primary","tunnel":"yes"}):
        assert not _osm_features([{**road,"tags":tags}],lambda x,y:(x,y))
    ring = pts+[{"lon":10,"lat":10},{"lon":0,"lat":10},pts[0]]
    roundabout = {**road, "tags":{"highway":"residential","width":"2"}, "geometry":ring}
    polygon = _osm_features([roundabout],lambda x,y:(x,y))[0]["geometry"]
    assert not polygon.covers(box(4,4,6,6))


def test_osm_relation_holes_and_incomplete_rings():
    nodes = [{"type":"node","id":i,"lon":x,"lat":y} for i,(x,y) in
             enumerate([(0,0),(6,0),(6,6),(0,6),(2,2),(4,2),(4,4),(2,4)],start=1)]
    ways = [{"type":"way","id":91,"nodes":[1,2,3,4,1]},{"type":"way","id":92,"nodes":[5,6,7,8,5]}]
    relation = {"type":"relation","id":93,"tags":{"type":"multipolygon","natural":"water"},
                "members":[{"role":"outer","type":"way","ref":91},{"role":"inner","type":"way","ref":92}]}
    good, skipped = _map_elements(nodes+ways+[relation])
    assert skipped == 0
    rows = _osm_features(good, lambda x,y:(x,y))
    assert len(rows)==1 and rows[0]["geometry"].area==32
    partial, skipped = _map_elements(nodes+ways[:1]+[relation])
    assert skipped==1 and not _osm_features(partial,lambda x,y:(x,y))


def test_texture_hints_shadow_and_unobserved_pixels_are_separate():
    rgb = np.zeros((3,15,15), dtype="uint8")
    rgb[:, :5, :] = np.array([30,20,25])[:,None,None]
    rgb[:, 5:10, :] = np.array([45,125,45])[:,None,None]
    rgb[:, 10:, :] = np.array([60,90,110])[:,None,None]
    valid = np.ones((15,15), dtype=bool)
    valid[:,0] = False
    masks = rgb_masks(rgb,valid)
    assert masks["hint_shadow_rgb"][2,2] and not masks["vegetation_rgb"][2,2]
    assert masks["vegetation_rgb"][7,2] and masks["hint_water_rgb"][13,7]
    assert not any(m[:,0].any() for m in masks.values())
    with MemoryFile() as mf:
        with mf.open(driver="GTiff",width=15,height=15,count=3,dtype="uint8", crs="EPSG:32642",
                     transform=Affine.translation(320000,2500000)*Affine.scale(1,-1),photometric="RGB") as src:
            src.write(rgb)
            src.write_mask(valid.astype("uint8")*255)
            rows, receipt=_imagery_candidates(src,"test")
    assert receipt["mask_valid_cells"]==210
    assert any(r["class"]=="vegetation" and not r["hint_only"] for r in rows)
    assert all(r["hint_only"] and r["needs_check"] for r in rows if r["class"] in ("water","shadow_full"))


def test_clean_priority_clip_snap_disjoint_and_receipt(tmp_path):
    transform = Affine.translation(100.15,210.47)*Affine.scale(.5,-.5)
    bounds=(100.15,200.47,110.15,210.47)
    def row(source,id,geom):
        return _suggest("built_"+source,"built",source,id,"v1",geom,"inspect",.88 if source=="open_buildings" else None)
    raw=[row("microsoft","b",box(99,201,104,205)),row("open_buildings","a",box(99.5,200,104,205)),
         row("microsoft","c",box(105,205,109,209))]
    out, duplicates = gen.clean_candidates(raw,bounds,transform,"abc")
    assert duplicates=={"built_microsoft":1}
    assert [r["source"] for r in out]==["open_buildings","microsoft"]
    assert all(box(*bounds).covers(r["geometry"]) and r["geometry"].is_valid for r in out)
    for r in out:
        x,y=r["geometry"].exterior.xy
        np.testing.assert_allclose((np.array(x)-transform.c)/.5, np.rint((np.array(x)-transform.c)/.5), atol=1e-7)
        np.testing.assert_allclose((np.array(y)-transform.f)/.5, np.rint((np.array(y)-transform.f)/.5), atol=1e-7)
    target=tmp_path/"prelabels.gpkg"
    gen._write(target,"EPSG:32642",out,{"tile_id":"abc","counts":{"built_open_buildings":1}})
    info=pyogrio.read_info(target,layer="built_open_buildings")
    assert json.loads(info["dataset_metadata"]["item21_receipt"])["tile_id"]=="abc"
    assert set(pyogrio.list_layers(target)[:,0])==set(gen.LAYERS)
    assert list(pyogrio.read_dataframe(target,layer="built_open_buildings")["candidate_id"])==[out[0]["candidate_id"]]


def test_gate_precedes_source_or_pixel_access(tmp_path,monkeypatch):
    calls=[]
    def refuse(path):
        calls.append("guard")
        raise ValueError("held out")
    monkeypatch.setattr(gen,"authorize_tile",refuse)
    monkeypatch.setattr(gen,"vector_sources",lambda *a:pytest.fail("vector fetch before guard"))
    monkeypatch.setattr(gen.rasterio,"open",lambda *a:pytest.fail("image read before guard"))
    with pytest.raises(ValueError,match="held out"):gen.generate(tmp_path)
    assert calls==["guard"] and not (tmp_path/"prelabels.gpkg").exists()


def test_vector_query_entrypoint_refuses_unregistered_heldout_and_makes_no_cache(tmp_path):
    from tools.labelling.candidate_sources import vector_sources
    from tools.labelling.guard import TileRefused
    heldout=tmp_path/"makoko"
    heldout.mkdir()
    with pytest.raises(TileRefused):
        vector_sources(heldout,tmp_path/"untouched")
    assert not (tmp_path/"untouched").exists()


def test_generate_in_private_practice_copy_and_preserve_existing_files(tmp_path,monkeypatch):
    """Set ITEM21_PRACTICE_COPY to a private practice tile to exercise real image/metadata geometry."""
    import hashlib
    import os
    import shutil
    available=os.getenv("ITEM21_PRACTICE_COPY")
    if not available:
        pytest.skip("set ITEM21_PRACTICE_COPY to an existing practice tile for the offline smoke test")
    source=Path(available).resolve()
    assert source.name.startswith("PRACTICE_")
    target=tmp_path/"practice"/source.name
    target.mkdir(parents=True)
    for name in ("hr.tif","tile.geojson","cells.geojson","metadata.json","labels.gpkg"):
        shutil.copyfile(source/name,target/name)
    def checksums():
        return {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in target.iterdir() if f.name!="prelabels.gpkg"}
    before=checksums()
    monkeypatch.setattr(gen,"vector_sources",lambda *a:([],{"osm":{"status":"offline_test"}}))
    receipt=gen.generate(target,cache=tmp_path/"cache")
    assert (target/"prelabels.gpkg").is_file() and receipt["sources"]["tile_rgb"]["status"]=="available"
    with pytest.raises(FileExistsError):
        gen.generate(target,cache=tmp_path/"cache")
    assert before==checksums()
