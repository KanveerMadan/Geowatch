/*
 * Phase 4: the drawn box is the analysed box, and a point's fixed box is
 * the size asked, checked against the server's own measure
 * (api.compute_aoi_geodesics, WGS84 geodesic polygon via pyproj).
 *
 * Run:  node tests/test_web_geometry.mjs
 * Needs <repo>/geowatch-env (symlink it into a worktree; do not commit it).
 */
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { execFileSync } from 'node:child_process'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')
const G = await import(join(root, 'web', 'src', 'lib', 'geo.js'))

/** The server's area / width / height for each box, in one Python call. */
function server(boxes) {
  const code = `
import json, sys
import api
print(json.dumps([api.compute_aoi_geodesics(*b) for b in json.loads(sys.argv[1])]))`
  const out = execFileSync(join(root, 'geowatch-env', 'bin', 'python'), ['-c', code, JSON.stringify(boxes)],
    { cwd: root, env: { ...process.env, GEOWATCH_API_KEY: 'test-only' }, encoding: 'utf8' })
  return JSON.parse(out.trim().split('\n').at(-1))
}

let n = 0
const test = (name, fn) => { fn(); n += 1 }
const LATS = [0, 19.04, -1.31, 23.8, 51.5, -33.9, 60, 69.6, -54.8]

// ── point + fixed box ──
const SIZES = [1, 2.5, 5, 10]
const pointBoxes = LATS.flatMap((lat) => SIZES.map((km) => ({ lat, lon: 36.78, km, box: G.boxAround(lat, 36.78, km) })))
const measured = server(pointBoxes.map((p) => p.box))

test('a point box is the size asked, on the server\'s measure, at any latitude', () => {
  pointBoxes.forEach((p, i) => {
    const m = measured[i]
    assert.ok(Math.abs(m.width_km - p.km) < 0.002 * p.km + 0.001, `${p.lat}° ${p.km} km: width ${m.width_km}`)
    assert.ok(Math.abs(m.height_km - p.km) < 0.002 * p.km + 0.001, `${p.lat}° ${p.km} km: height ${m.height_km}`)
  })
})
test('the default 10 x 10 km box is never refused for size: <= 100 km², > 99.5', () => {
  assert.equal(G.DEFAULT_POINT_BOX_KM, 10)
  pointBoxes.forEach((p, i) => {
    if (p.km !== 10) return
    assert.ok(measured[i].area_km2 <= 100, `${p.lat}°: ${measured[i].area_km2} km² would be refused`)
    assert.ok(measured[i].area_km2 > 99.5, `${p.lat}°: ${measured[i].area_km2} km²`)
  })
})
test('a point box is centred on the point', () => {
  for (const p of pointBoxes) {
    const [w, s, e, nn] = p.box
    assert.ok(Math.abs((w + e) / 2 - p.lon) < 2e-6 && Math.abs((s + nn) / 2 - p.lat) < 2e-6)
  }
})
test('box size is adjustable up to the limit, never past it', () => {
  assert.equal(G.maxBoxKm(100), 10)
  assert.equal(G.maxBoxKm(50), 7)
  assert.equal(G.maxBoxKm(0.5), G.MIN_POINT_BOX_KM)
  for (const lat of LATS) {
    assert.notEqual(G.areaState(G.bboxAreaKm2(G.boxAround(lat, 0, G.maxBoxKm(100))), 100), 'over')
  }
})

// ── the readout agrees with the server ──
test('the km² readout matches the server within 0.1%', () => {
  const boxes = pointBoxes.map((p) => p.box)
  boxes.forEach((b, i) => {
    const mine = G.bboxAreaKm2(b)
    assert.ok(Math.abs(mine - measured[i].area_km2) <= 0.001 * measured[i].area_km2 + 0.0002,
      `${b}: ${mine} vs ${measured[i].area_km2}`)
  })
})

// ── the drawn box is the analysed box ──
test('a rectangle is the same box whichever way it is dragged', () => {
  const a = [36.77, -1.32], b = [36.8, -1.3]
  const want = [36.77, -1.32, 36.8, -1.3]
  for (const [p, q] of [[a, b], [b, a], [[a[0], b[1]], [b[0], a[1]]], [[b[0], a[1]], [a[0], b[1]]]]) {
    assert.deepEqual(G.bboxOf([p, q]), want)
  }
})
test('the drawn outline lies exactly on the analysed box, every vertex on an edge', () => {
  for (const bbox of [[36.77, -1.322, 36.8, -1.3], [-0.2, 51.45, -0.05, 51.55], [174.7, -36.9, 174.8, -36.8]]) {
    const ring = G.boxRing(bbox)
    const [w, s, e, nn] = bbox
    assert.deepEqual(ring[0], ring.at(-1))
    assert.equal(ring.length, 4 * G.EDGE_STEPS + 1)
    for (const [x, y] of ring) {
      const onEdge = x === w || x === e || y === s || y === nn
      assert.ok(onEdge && x >= w && x <= e && y >= s && y <= nn, `${x},${y} off the box`)
    }
    assert.deepEqual(G.bboxOf(ring), bbox) // what is shown is what is sent
  }
})
test('edges are densified, so they follow parallels and meridians when projected', () => {
  const ring = G.boxRing([0, 0, 1, 1])
  const south = ring.filter(([, y]) => y === 0)
  assert.ok(south.length > 2 && south.every(([, y]) => y === 0))
})

console.log(`test_web_geometry: ${n} passed`)
