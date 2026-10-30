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
const F = await lib('flood.js')
const CH = await lib('change.js')
const O = await lib('overlay.js')

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

// ── Flood tab (Step B) ──
const hz = {
  pluvial: out(0.33, 'available', 'failed', { tier: 'low', per_unit: true, map: {} }),
  fluvial: out(0.41, 'available', 'experimental', { tier: 'moderate', per_unit: true }),
  coastal: out(null, 'not_applicable', 'failed'),
  flash_flood: out(0.29, 'available', 'experimental', { tier: 'low', per_unit: true }),
  waterlogging: out(null, 'timeout', 'experimental'),
}
test('one flood row per type in the result, absent never a number', () => {
  const rows = F.floodRows(hz)
  assert.deepEqual(rows.map((r) => r.key), Object.keys(hz))
  const c = rows.find((r) => r.key === 'coastal')
  assert.equal(c.measured, false); assert.equal(c.value, null); assert.equal(c.tierText, 'Does not apply here')
  assert.equal(c.mapped, false)
  assert.equal(rows.find((r) => r.key === 'waterlogging').tierText, 'Timed out')
  assert.equal(rows.find((r) => r.key === 'pluvial').trust.key, 'failed')
})
test('the flood summary leads with trusted readings and names the failed one', () => {
  const s = F.floodSummary(hz)
  assert.match(s, /^River flooding is the highest here, at moderate\./)
  assert.match(s, /Surface-water flooding is shown but failed validation, so it is not for decisions\./)
  assert.match(s, /Coastal flooding does not apply here\./)
  assert.match(s, /Waterlogging: timed out\./)
  assert.doesNotMatch(s, /\d/)
})
test('the default flood layer is a mapped type that did not fail', () => {
  assert.equal(F.defaultFloodLayer(hz), 'fluvial')
  assert.equal(F.defaultFloodLayer({ pluvial: hz.pluvial, coastal: hz.coastal }), 'pluvial')
  assert.equal(F.defaultFloodLayer({ coastal: hz.coastal }), null)
})
test('tiers follow the contract breaks', () => {
  assert.equal(F.tierOf(0), 'very_low'); assert.equal(F.tierOf(0.2), 'low'); assert.equal(F.tierOf(0.79), 'high')
  assert.equal(F.tierOf(1), 'very_high'); assert.equal(F.tierOf(null), null)
})
test('wards rank by score, unmeasured wards follow unranked', () => {
  const f = (id, v, st = 'available') => ({ properties: { unit_id: id, unit_name: `W${id}`, area_m2: 2e6, flood_fluvial: v, flood_fluvial_status: st } })
  const { ranked, unranked } = F.rankWards({ features: [f('a', 0.2), f('b', null, 'insufficient_observation'), f('c', 0.7), f('d', 0)] }, 'fluvial')
  assert.deepEqual(ranked.map((r) => [r.id, r.rank]), [['c', 1], ['a', 2], ['d', 3]])
  assert.equal(ranked[2].value, 0)                         // a measured zero is ranked
  assert.deepEqual(unranked.map((r) => [r.id, r.value, r.status]), [['b', null, 'insufficient_observation']])
  assert.equal(F.wardUnitType({ wards: { grid: {}, 'ward:mumbai': {} } }), 'ward:mumbai')
  assert.equal(F.wardUnitType({ wards: { grid: {} } }), null)
})

// ── Change tab (Step B) ──
const chg = {
  built: out({ increase: 10, decrease: 25, no_detectable_change: 815 }, 'available', 'experimental',
    { counts_all: { increase: 10, decrease: 25, no_detectable_change: 815, insufficient_observation: 5, epoch_unreliable: 0 }, epochs: { a: 2021, b: 2023 } }),
  vegetation: out({ increase: 48, decrease: 24, no_detectable_change: 778 }, 'available', 'placeholder',
    { epochs: { a: { window: ['2021-07-30', '2021-10-28'] }, b: { window: ['2026-07-30', '2026-10-28'] } } }),
  paved: out(null, 'not_computed', 'placeholder'),
}
test('change rows count cells and keep their compared years', () => {
  const rows = CH.changeRows(chg)
  assert.deepEqual(rows.map((r) => r.key), ['built', 'vegetation', 'paved'])
  const b = rows[0]
  assert.equal(b.judged, 850); assert.equal(b.cells, 855); assert.equal(b.unjudged, 5); assert.deepEqual(b.years, [2021, 2023])
  assert.deepEqual(rows[1].years, [2021, 2026])
  assert.equal(rows[2].measured, false); assert.equal(rows[2].text, 'Not yet measured')
})
test('the change summary names the fraction with most change and what is not measured', () => {
  const s = CH.changeSummary(chg)
  assert.match(s, /^Most change here is in vegetation: 72 of 850 cells \(8%\) changed between 2021 and 2026, 48 up and 24 down\./)
  assert.match(s, /Built: 10 up, 25 down \(2021 and 2023\)\./)
  assert.match(s, /Paved change is not yet measured\./)
})
test('an unjudged cell is never "no change"', () => {
  assert.equal(CH.cellChange({ water: 'increase' }, 'water'), 'increase')
  assert.equal(CH.cellChange({ water: 'no_detectable_change' }, 'water'), 'none')
  assert.equal(CH.cellChange({ water: 'insufficient_observation' }, 'water'), 'unjudged')
  assert.equal(CH.cellChange({ water: 'epoch_unreliable' }, 'water'), 'unjudged')
  assert.equal(CH.cellChange({}, 'water'), 'unjudged')
})
test('before stays before after', () => {
  const ys = [2017, 2018, 2019, 2020, 2021]
  assert.deepEqual(CH.orderPair([2018, 2020], 'before', 2020, ys), [2020, 2021])
  assert.deepEqual(CH.orderPair([2018, 2020], 'after', 2017, ys), [2017, 2018])
  assert.deepEqual(CH.orderPair([2018, 2020], 'before', 2030, ys), [2020, 2021])
  assert.deepEqual(CH.orderPair([2018, 2020], 'after', 2019, ys), [2018, 2019])
})

// ── swipe overlay geometry ──
test('the overlay square lands on the four projected corners', () => {
  const quad = [[100, 50], [420, 80], [400, 390], [90, 360]]
  const L = 1000
  const near = (a, b) => assert.ok(Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6, `${a} vs ${b}`)
  near(O.applyHomography(L, quad, [0, 0]), quad[0]); near(O.applyHomography(L, quad, [L, 0]), quad[1])
  near(O.applyHomography(L, quad, [L, L]), quad[2]); near(O.applyHomography(L, quad, [0, L]), quad[3])
})
test('unit coordinates are Mercator across the box, north up', () => {
  const u = O.toUnit([36.77, -1.322, 36.8, -1.3])
  assert.deepEqual(u([36.77, -1.3]).map((v) => +v.toFixed(9)), [0, 0])
  assert.deepEqual(u([36.8, -1.322]).map((v) => +v.toFixed(9)), [1, 1])
  const cells = O.unitCells({ features: [{ id: 3, properties: {}, geometry: { type: 'Polygon', coordinates: [[[36.77, -1.3], [36.78, -1.3], [36.78, -1.31], [36.77, -1.31], [36.77, -1.3]]] } }] }, [36.77, -1.322, 36.8, -1.3])
  assert.equal(O.cellAt(cells, u([36.775, -1.305])).id, 3)
  assert.equal(O.cellAt(cells, u([36.79, -1.305])), null)
  assert.match(O.pathOf(cells), /^M0 0L0\.33333 0L/)
})

test('ward ranking is offered only where a boundary layer holds the area', () => {
  const layers = [{ boundary_layer_id: 'mumbai', bbox: [72.77, 18.89, 72.99, 19.27] }, { boundary_layer_id: 'x', bbox: null }]
  assert.equal(G.boundaryFor([72.83, 19.03, 72.86, 19.06], layers).boundary_layer_id, 'mumbai')
  assert.equal(G.boundaryFor([36.77, -1.32, 36.8, -1.3], layers), null)
  assert.equal(G.boundaryFor([36.77, -1.32, 36.8, -1.3], null), null)
})

test('a fraction with every cell unjudged is never "no change"', () => {
  const cloudy = {
    built: chg.built,
    vegetation: out({ increase: 0, decrease: 0, no_detectable_change: 0 }, 'available', 'placeholder',
      { counts_all: { increase: 0, decrease: 0, no_detectable_change: 0, insufficient_observation: 0, epoch_unreliable: 2700 } }),
  }
  const r = CH.changeRows(cloudy).find((x) => x.key === 'vegetation')
  assert.equal(r.judged, 0); assert.equal(r.unjudged, 2700)
  const s = CH.changeSummary(cloudy)
  assert.doesNotMatch(s, /Vegetation: no detectable change/)
  assert.match(s, /Vegetation: could not be judged \(one of the two years was too cloudy to compare\)\./)
})
test('flood summary sentences start with a capital and nothing else does', () => {
  const s = F.floodSummary({ fluvial: hz.fluvial, flash_flood: out(0.7, 'available', 'experimental', { tier: 'high' }), waterlogging: out(0.9, 'available', 'experimental', { tier: 'very_high' }) })
  assert.match(s, /^Waterlogging is the highest here, at very high\. Flash flooding high; river flooding moderate\.$/)
})

console.log(`test_web_logic: ${n} passed`)
