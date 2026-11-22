import geopandas as gpd
from shapely.geometry import box, Polygon
from tools.labelling.guard import TileSpec
from tools.labelling.validate import inspect_labels
from labelling.common import load_config


def test_full_tile_provenance_and_coverage():
    tile=TileSpec(None,'practice','test',None,'EPSG:32734',(0,0,200,200))
    sources=dict(source='Open Buildings',source_id='a',source_version='v3',candidate_id='built:a')
    a=box(0,0,125,200)
    b=box(125,0,200,200)
    record=dict(label='built',shadow_partial=False,rooftop_solar=False)
    table=gpd.GeoDataFrame([{**record,**sources,'provenance':'prelabel_kept','geometry':a},
                            {**record,'provenance':'hand_drawn','geometry':b}], crs=tile.crs)
    candidates={'built:a':{**sources,'class':'built','geometry':a,'hint_only':False}}
    r=inspect_labels(table,tile,candidates,load_config())
    assert r['errors']==[] and r['fractions']['scored_cells']==400
    assert r['by_class']['built']['prelabel_kept']['area_share']==.625
    assert r['by_class']['built']['prelabel_kept']['polygon_share']==.5
    assert r['warnings']
    table.loc[0,'label']='paved'
    assert any('differs' in e for e in inspect_labels(table,tile,candidates,load_config())['errors'])
    table.loc[0,'provenance']='prelabel_edited'
    assert not inspect_labels(table,tile,candidates,load_config())['errors']
    candidates['built:a']['hint_only']=True
    assert any('display-only' in e for e in inspect_labels(table,tile,candidates,load_config())['errors'])


def test_exact_topology_and_unknown_legacy_origin():
    tile=TileSpec(None,'practice','test',None,'EPSG:32734',(0,0,200,200))
    table=gpd.GeoDataFrame([dict(label='bare',geometry=box(0,0,100.1,198)),
                           dict(label='water',geometry=box(100,0,200,200)),
                           dict(label='built',geometry=Polygon([(0,0),(5,5),(5,0),(0,5)]))],crs=tile.crs)
    r=inspect_labels(table,tile,{},load_config())
    assert r['overlap_excess_m2']>0 and r['uncovered_m2']>0
    assert r['provenance']['unknown']['polygons']==3
    assert any('invalid' in e for e in r['errors']) and r['fractions'] is None


def test_sun_resolver_receives_only_private_copies(tmp_path,monkeypatch):
    import json,sqlite3
    from labelling import sun_geometry
    from tools.labelling.validate import sun_record
    tile=TileSpec(tmp_path,'lima','test',None,'EPSG:32718',(0,0,200,200))
    meta={'labeller':'example'}
    (tmp_path/'metadata.json').write_text(json.dumps(meta))
    with sqlite3.connect(tmp_path/'sun.gpkg') as db:
        db.execute('CREATE TABLE lines (id INTEGER)')
    before={f.name:f.read_bytes() for f in tmp_path.iterdir()}
    def resolve(p,cfg):
        from pathlib import Path
        assert Path(p)!=tmp_path
        (Path(p)/'metadata.json').write_text(json.dumps(dict(meta,sun_geometry_n_buildings=3)))
    monkeypatch.setattr(sun_geometry,'run',resolve)
    assert sun_record(tile,meta,{})['sun_geometry_n_buildings']==3
    assert {f.name:f.read_bytes() for f in tmp_path.iterdir()}==before
