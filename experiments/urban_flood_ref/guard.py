"""Metadata-only approval gate. Data readers must accept only a unit ID."""
from datetime import date, timedelta
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from . import upstream_registry as registry

HERE = Path(__file__).resolve().parent
PIN = 'e2545ed7b0f515682fdd5cc745d7934bdee9d20efd01d3b4f0a7274b3afab0e1'
CUTOFF = date(2022, 1, 1)
# Storm-wide aliases cross borders and exceed a point-proximity test.
ROUND3_STORMS = {'bernd_2021', 'western_europe_july_2021'}


def activation(row):
    return set(re.findall(r'EMSR\d+', ' '.join(row.get('products', [])).upper()))


def connected(a, b):
    return bool(activation(a) & activation(b) or registry.links(a, b))


@lru_cache(maxsize=1)
def metadata():
    path = HERE / 'registry_snapshot.json'
    if hashlib.sha256(path.read_bytes()).hexdigest() != PIN:
        raise ValueError('registry does not match flood-final preregistration')
    upstream = registry.load(str(path))['units']
    sites = json.loads((HERE/'sites.json').read_text()) + json.loads((HERE/'historic_sites.json').read_text())
    if len({s['unit'] for s in sites}) != len(sites):
        raise ValueError('duplicate approved site identity')
    return upstream, sites, json.loads((HERE/'round3_exclusions.json').read_text())


@lru_cache(maxsize=1)
def excluded():
    upstream, _, _ = metadata()
    blocked = {u['event_id'] for u in upstream if u['role'] != 'dev'}
    # Follow physical links across aliases, including shared basins and storms.
    while True:
        old = set(blocked)
        sources = [u for u in upstream if u['event_id'] in old]
        blocked.update(u['event_id'] for u in upstream if any(connected(u, v) for v in sources))
        if blocked == old:
            return tuple(u for u in upstream if u['event_id'] in blocked)


def authorize(unit):
    upstream, sites, round3 = metadata()
    record = next((s for s in sites if s['unit'] == unit), None)
    if record is None:
        raise ValueError('unit is outside the reviewed allowlist')
    if record['incident'] in ROUND3_STORMS:
        raise ValueError('storm also listed by round 3')
    when = date.fromisoformat(record['date'])
    if not record['country'] or record['country'] in {'US', 'PR', 'VI', 'GU', 'MP', 'AS'} or when >= CUTOFF:
        raise ValueError('historical non-US events only')
    original = next((u for u in upstream if u['event_id'] == unit), None)
    if original and (original['role'] != 'dev' or when.isoformat() != original['date'] or
                     record['bbox'] not in registry._boxes(original)):
        raise ValueError('development registry disagrees with site identity')
    if not original and not (record.get('basins') or unit.startswith('usf_weihui_') and record['incident']=='henan_jul_2021'):
        raise ValueError('new site needs reviewed basin metadata')
    w,s,e,n = record['bbox']
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90 and e-w <= .15 and n-s <= .15):
        raise ValueError('invalid or unbounded tile')
    # Covers the slight outward expansion caused by snapping to the UTM grid.
    padded = [w-.002, s-.002, e+.002, n+.002]
    probe = dict(original or {}, event_id=unit, role='dev', storm_cluster=record['incident'],
                 products=record['products'], geometry={'type':'boxes','boxes':[{'bbox':padded}]})
    if record.get('basins'):
        probe['basins'] = record['basins']
    intersections = record.get('basin_intersections', {})
    if any(x['event_id']==unit or connected(probe,x) or any(
            x.get('basins',{}).get(key) in intersections.get(key,[]) for key in ('hybas_6','main_bas'))
           for x in excluded()):
        raise ValueError('reserved event or linked site')
    for x in round3:
        if x['product'] in activation(probe):
            raise ValueError('round 3 candidate activation')
        if abs((when-date.fromisoformat(x['date'])).days) > 30:
            continue
        if ((x['point'] and registry._km_point_to_box(x['point'],padded) <= 20)
                or (x['bbox'] and registry._intersects(x['bbox'],padded))):
            raise ValueError('round 3 candidate incident')
    return json.loads(json.dumps(record))


def authorize_window(unit, first, last):
    site = authorize(unit)
    anchor = date.fromisoformat(site['date'])
    start, end = date.fromisoformat(str(first)[:10]), date.fromisoformat(str(last)[:10])
    if not anchor-timedelta(days=370) <= start <= end <= min(anchor+timedelta(days=21), CUTOFF-timedelta(days=1)):
        raise ValueError('acquisition outside the historical event window')
    return site


if __name__ == '__main__':
    for entry in metadata()[1]:
        try:
            print(authorize(entry['unit'])['unit'], 'eligible')
        except ValueError as error:
            print(entry['unit'], 'excluded:', error)
