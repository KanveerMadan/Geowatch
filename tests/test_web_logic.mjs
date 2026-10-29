/*
 * Phase 4: the new frontend's logic (web/src/lib), checked under node.
 * Trust-badge mapping, contract parsing, never-show-0-for-missing, the area
 * limit, coordinate search and the job API's plain-language states.
 *
 * Run:  node tests/test_web_logic.mjs
 */
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const lib = (f) => import(join(here, '..', 'web', 'src', 'lib', f))
const C = await lib('contract.js')
const G = await lib('geo.js')
const S = await lib('stages.js')

let n = 0
const test = (name, fn) => { fn(); n += 1 }

const out = (value, status = 'available', label = 'experimental', extra = {}) => ({
  value, status, validation_status: label, coverage: { observed_fraction: 1, basis: 'x' },
  data_sources: ['s'], model_version: {}, ...extra,
})

// ── trust badges ──
test('every pipeline label maps to its own badge', () => {
  for (const k of ['validated', 'experimental', 'placeholder', 'failed', 'retired']) {
    const t = C.trustOf(out(0.1, 'available', k))
    assert.equal(t.key, k)
    assert.ok(t.label && t.explain.length > 20)
  }
})
test('an unknown label is never promoted to a known one', () => {
  assert.equal(C.trustOf(out(0.1, 'available', 'great')).key, 'unlabelled')
  assert.equal(C.trustOf(undefined).key, 'unlabelled')
})
test('validated carries a scope note, others do not', () => {
  assert.equal(C.trustOf(out(1, 'available', 'validated', { validation_scope: 'Hanoi, Kolonnawa' })).scope,
    'Hanoi, Kolonnawa')
  assert.match(C.trustOf(out(1, 'available', 'validated')).scope, /not stated/)
  assert.equal(C.trustOf(out(1)).scope, null)
})
test('worst label wins, by the contract precedence', () => {
  assert.equal(C.worstTrust([out(1, 'available', 'validated'), out(1, 'available', 'failed'),
    out(1, 'available', 'placeholder')]), 'failed')
  assert.equal(C.worstTrust([]), null)
})

// ── never 0 for missing ──
test('a measured zero is 0.0%; absent is never a number', () => {
  assert.equal(C.fmtFraction(out(0)).display, '0.0%')
  for (const st of ['not_computed', 'insufficient_observation', 'timeout', 'failed', 'unavailable']) {
    const f = C.fmtFraction(out(null, st))
    assert.equal(f.measured, false)
    assert.ok(!/\d/.test(f.display), `${st} rendered as ${f.display}`)
  }
  assert.equal(C.fmtFraction(undefined).measured, false)
  assert.equal(C.fmtFraction(null).display, 'Not measured')
})
test('a measured share too small for the precision shown is never a zero', () => {
  assert.equal(C.fmtFraction(out(0.0002)).display, '<0.1%')
  assert.equal(C.fmtPct0(0.002), '<1%')
  assert.equal(C.fmtPct0(0), '0%')
})
test('a number with a non-available status is not shown as measured', () => {
  assert.equal(C.readOutput(out(0.4, 'timeout')).measured, false)
  assert.equal(C.readOutput(out(NaN)).measured, false)
})
test('rows come from the result, measured first; absent keeps its reason', () => {
  const rows = C.fractionRows({
    paved: out(null, 'not_computed', 'placeholder', { reason: 'needs item 21' }),
    built: out(0.42), water: out(0),
  })
  assert.deepEqual(rows.map((r) => r.key), ['built', 'water', 'paved'])
  assert.equal(rows[2].display, 'Not yet measured')
  assert.equal(rows[2].reason, 'needs item 21')
  assert.equal(C.fractionRows({ new_thing: out(0.1) })[0].name, 'New thing')
})
test('the summary names measured and absent fractions, no zero for absent', () => {
  const s = C.groundSummary({ built: out(0.42), vegetation: out(0.1), bare: out(null, 'not_computed') })
  assert.match(s, /built 42%/)
  assert.match(s, /Bare ground is not yet measured/)
  // A measured share under 1% never reads as a zero.
  assert.match(C.groundSummary({ water: out(0.003) }), /water under 1%/)
  assert.match(C.groundSummary({ water: out(0) }), /water 0%/)
  assert.equal(C.groundSummary({}), 'Nothing could be measured for this area yet.')
})
test('stacked bar: absent is not a segment; overlap is scaled and flagged', () => {
  const a = C.stackSegments({ built: 0.3, vegetation: 0.2, water: null }, ['built', 'vegetation', 'water'])
  assert.deepEqual(a.segments.map((s) => s.key), ['built', 'vegetation'])
  assert.deepEqual(a.absent, ['water'])
  assert.equal(a.overlap, false)
  assert.ok(Math.abs(a.rest - 0.5) < 1e-9)
  const b = C.stackSegments({ built: 0.8, vegetation: 0.6 }, ['built', 'vegetation'])
  assert.equal(b.overlap, true)
  assert.ok(Math.abs(b.segments.at(-1).start + b.segments.at(-1).width - 1) < 1e-9)
})

// ── geometry ──
test('box area is ellipsoidal at the equator and shrinks with latitude', () => {
  const eq = G.bboxAreaKm2([0, -0.05, 0.1, 0.05])
  assert.ok(Math.abs(eq - 123.1) < 0.2, eq)       // 11.13 km x 11.06 km on WGS84
  assert.ok(G.bboxAreaKm2([0, 59.95, 0.1, 60.05]) < eq * 0.51)
})
test('area state: ok, warn from 80%, over past the limit', () => {
  assert.equal(G.areaState(10, 100), 'ok')
  assert.equal(G.areaState(80, 100), 'warn')
  assert.equal(G.areaState(100, 100), 'warn')
  assert.equal(G.areaState(100.01, 100), 'over')
})
test('the default box is about DEFAULT_BOX_KM square anywhere', () => {
  for (const lat of [0, 45, -33.9, 64]) {
    const a = G.bboxAreaKm2(G.boxAround(lat, 10))
    assert.ok(Math.abs(a - G.DEFAULT_BOX_KM ** 2) < 0.1, `${lat}: ${a}`)
  }
})
test('a place uses its own extent only when it is a sensible size', () => {
  const small = [36.77, -1.322, 36.8, -1.3]
  assert.deepEqual(G.boxForPlace({ lat: -1.31, lon: 36.78, bbox: small }, 100), small)
  const city = G.boxForPlace({ lat: 6.5, lon: 3.4, bbox: [2.7, 6.3, 4.4, 6.8] }, 100)
  assert.ok(G.bboxAreaKm2(city) < 10)
  const tiny = G.boxForPlace({ lat: 6.5, lon: 3.4, bbox: [3.4, 6.5, 3.4001, 6.5001] }, 100)
  assert.ok(G.bboxAreaKm2(tiny) > 1)
})
test('coordinates: lat,lon by default; hemispheres respected; junk refused', () => {
  assert.deepEqual(G.parseCoordinates('19.04, 72.85'), { lat: 19.04, lon: 72.85 })
  assert.deepEqual(G.parseCoordinates('-1.31 36.78'), { lat: -1.31, lon: 36.78 })
  assert.deepEqual(G.parseCoordinates('33.9S, 18.4E'), { lat: -33.9, lon: 18.4 })
  assert.deepEqual(G.parseCoordinates('18.4E 33.9S'), { lat: -33.9, lon: 18.4 })
  assert.deepEqual(G.parseCoordinates('51.5°N, 0.12°W'), { lat: 51.5, lon: -0.12 })
  for (const bad of ['Lagos', '95, 10', '10, 190', '10N 20N', '-10S 5E', '1,2,3', '']) {
    assert.equal(G.parseCoordinates(bad), null, bad)
  }
})
test('lasso points become their bounding box', () => {
  assert.deepEqual(G.bboxOf([[1, 2], [3, -1], [2, 5]]), [1, -1, 3, 5])
})

// ── job states ──
const job = (status, stages = {}, extra = {}) => ({ status, stages, partial: {}, result: null, ...extra })
test('stages: context sub-stages fold into one row with the worst outcome', () => {
  const rows = S.stageRows(job('running', {
    road_layer: { status: 'ok' }, 'context:hand': { status: 'ok' }, 'context:rain': { status: 'timeout' },
    s2_composite: { status: 'running' },
  }))
  const by = Object.fromEntries(rows.map((r) => [r.key, r.state]))
  assert.equal(by.context, 'timeout')
  assert.equal(by.s2_composite, 'running')
  assert.equal(by.change, 'waiting')
})
test('an unknown stage is shown, not dropped', () => {
  const rows = S.stageRows(job('complete', { brand_new: { status: 'ok' } }))
  assert.ok(rows.some((r) => r.key === 'brand_new' && r.text === 'brand new'))
})
test('group state: ready from partial, failed from its stage, waiting otherwise', () => {
  assert.equal(S.groupState(job('running', {}, { partial: { fractions: {} } }), 'fractions'), 'ready')
  assert.equal(S.groupState(job('running', { s2_composite: { status: 'timeout' } }), 'fractions'), 'failed')
  assert.equal(S.groupState(job('running'), 'fractions'), 'waiting')
  assert.equal(S.groupState(job('failed'), 'fractions'), 'failed')
})
test('failure text is plain language and never echoes the raw error', () => {
  const raw = 'RuntimeError: road layer failed: HTTPError 502 https://overpass'
  const j = job('failed', { road_layer: { status: 'failed', error: raw } }, { error: { message: raw } })
  const t = S.failureText(j)
  assert.match(t, /road and building map/)
  assert.ok(!t.includes('Error') && !t.includes('http') && !t.includes('502'))
})
test('an unstored result names its gaps in plain words', () => {
  const t = S.gapText({ not_stored_because: { 'context:hand': 'timeout', 'context:rain': 'failed' } })
  assert.match(t, /timed out/)
  assert.match(t, /rainfall, terrain and coast/)
  assert.equal(S.gapText({ not_stored_because: null }), null)
})

// ── the URL: what is shared is what is shown; clearing removes the area ──
const L = await lib('link.js')
test('a bbox link opens that box; invalid boxes are dropped', () => {
  assert.deepEqual(L.parseLink('?bbox=36.77,-1.322,36.8,-1.3').bbox, [36.77, -1.322, 36.8, -1.3])
  for (const bad of ['?bbox=1,2,3', '?bbox=5,0,1,1', '?bbox=0,-95,1,1', '?bbox=a,b,c,d', '']) {
    assert.equal(L.parseLink(bad).bbox, null, bad)
  }
  assert.equal(L.parseLink('?job=../x').jobId, null)
  assert.equal(L.parseLink('?tab=nope').tab, 'ground')
})
test('a link round-trips the box, a running job and the tab', () => {
  const view = { bbox: [36.77, -1.322, 36.8, -1.3], jobId: 'j' + 'a'.repeat(24), jobDone: false, tab: 'flood' }
  const back = L.parseLink(L.linkQuery(view))
  assert.deepEqual(back, { bbox: view.bbox, jobId: view.jobId, tab: 'flood' })
  assert.equal(L.parseLink(L.linkQuery({ ...view, jobDone: true })).jobId, null)
})
test('clearing the area clears it from the URL, job included', () => {
  assert.equal(L.linkQuery({ bbox: null, jobId: 'j' + 'a'.repeat(24), jobDone: false, tab: 'ground' }), '')
  assert.equal(L.linkQuery({ bbox: null, tab: 'change' }), '?tab=change')
})
test('a new area replaces the old one in the URL', () => {
  const a = L.linkQuery({ bbox: [1, 1, 2, 2], tab: 'ground' })
  const b = L.linkQuery({ bbox: [3, 3, 4, 4], tab: 'ground' })
  assert.equal(L.parseLink(b).bbox[0], 3)
  assert.ok(!b.includes('1.00000'), a)
})
test('a box opened from a link is never called "Drawn area"', () => {
  const p = L.linkPlace([36.77, -1.322, 36.8, -1.3])
  assert.equal(p.name, 'Selected area')
  assert.equal(p.region, '1.311° S, 36.785° E')
})

console.log(`test_web_logic: ${n} passed`)
