"""Query OSM features from a local Geofabrik extract. Coordinates are WGS84."""
import fcntl, hashlib, json, sqlite3, subprocess, tempfile
from pathlib import Path
import osmium
from shapely import from_wkb,to_wkb
from shapely.geometry import box, mapping

def classes(t):
    result=[]
    if t.get('natural')=='water' or t.get('landuse') in ('reservoir','basin') or 'water' in t: result.append('water_bodies')
    if t.get('waterway') and t['waterway'] not in ('dam','weir','dyke'):result.append('waterways')
    if t.get('waterway') in ('drain','ditch','canal'):result.append('drains_canals')
    if t.get('man_made') in ('embankment','dyke','dike','levee') or t.get('embankment') not in (None,'no') or t.get('waterway')=='dyke':result.append('embankments')
    if t.get('railway') and t.get('bridge') not in (None,'no'):result.append('rail_bridges')
    if t.get('building') not in (None,'no'):result.append('buildings')
    return result

def _populate(conn, small):
    factory=osmium.geom.WKBFactory()
    def store(kind,oid,t,geom):
        cats=classes(t)
        if not cats:return
        g=from_wkb(bytes.fromhex(geom()))
        w,s,e,n=g.bounds
        conn.execute('INSERT OR REPLACE INTO features VALUES(?,?,?,?,?)',(kind,oid,json.dumps(cats),json.dumps(dict(t)),to_wkb(g)))
    class Handler(osmium.SimpleHandler):
        def node(self,o):store('node',o.id,o.tags,lambda:factory.create_point(o))
        def way(self,o):
            if len(o.nodes)>=2:store('way',o.id,o.tags,lambda:factory.create_linestring(o))
        def area(self,o):store('way' if o.from_way() else 'relation',o.orig_id(),o.tags,lambda:factory.create_multipolygon(o))
    Handler().apply_file(str(small),locations=True)
    for rowid,b in conn.execute('SELECT rowid,geom FROM features'):
        w,s,e,n=from_wkb(b).bounds
        conn.execute('INSERT INTO spatial VALUES(?,?,?,?,?)',(rowid,w,e,s,n))

def query(bbox, pbf, cache, *,padding=.01):
    """Return a GeoJSON collection. Reuse the R-tree for nearby queries within the cached envelope."""
    w,s,e,n=map(float,bbox)
    if not (-180<=w<e<=180 and -90<=s<n<=90 and padding>=0):raise ValueError('Invalid bounding box')
    path=Path(pbf).resolve();stat=path.stat()
    version=hashlib.sha256(f'v1:{path}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()[:24]
    folder=Path(cache)/version;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'index.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        db=None
        for entry in folder.glob('*.sqlite'):
            with sqlite3.connect(entry) as con:
                a,b,c,d=con.execute('select * from bounds').fetchone()
            if a<=w and b<=s and c>=e and d>=n:db=entry;break
        if db is None:
            bounds=[max(-180,w-padding),max(-90,s-padding),min(180,e+padding),min(90,n+padding)]
            db=folder/(hashlib.sha256(repr(bounds).encode()).hexdigest()[:20]+'.sqlite')
            with tempfile.TemporaryDirectory(dir=folder) as tmp:
                cut=Path(tmp)/'cut.osm.pbf';build=Path(tmp)/'index.sqlite'
                subprocess.run(['osmium','extract','--strategy=smart','-b',','.join(map(str,bounds)),'-o',str(cut),str(path)],check=True)
                with sqlite3.connect(build) as con:
                    con.executescript('CREATE TABLE features(kind,id,categories,tags,geom,UNIQUE(kind,id)); CREATE VIRTUAL TABLE spatial USING rtree(id,w,e,s,n); CREATE TABLE bounds(w,s,e,n);')
                    con.execute('insert into bounds values(?,?,?,?)',bounds);_populate(con,cut)
                build.rename(db)
    target=box(w,s,e,n);features=[]
    with sqlite3.connect(db) as con:
        for k,i,c,t,b in con.execute('SELECT kind,features.id,categories,tags,geom FROM features JOIN spatial ON features.rowid=spatial.id WHERE spatial.w<=? AND spatial.e>=? AND spatial.s<=? AND spatial.n>=?',(e,w,n,s)):
            g=from_wkb(b)
            if target.intersects(g):features.append({'type':'Feature','id':f'{k}/{i}','properties':{'classes':json.loads(c),'tags':json.loads(t)},'geometry':mapping(g)})
    return {'type':'FeatureCollection','features':features,'attribution':'© OpenStreetMap contributors, ODbL 1.0'}
