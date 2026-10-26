/*
 * Build item 58 — the frontend renders result.json and computes nothing.
 *
 * Each test names one of the item's removals. The helpers in
 * geowatch-ui/src/render.js are tested by behaviour; App.jsx is checked
 * structurally, because it cannot be rendered here without a browser.
 *
 * The one the item called out by name: `?? 291 / ?? 257` was exactly
 * Dharavi's tile_dimensions. A result missing the field would have been
 * projected through Dharavi's grid, anywhere in the world, silently.
 *
 * Run:  node tests/test_pure_renderer_ui.mjs
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const app = readFileSync(join(here, '..', 'geowatch-ui', 'src', 'App.jsx'), 'utf8')

let render = null
try {
  render = await import(join(here, '..', 'geowatch-ui', 'src', 'render.js'))
} catch (e) {
  render = null
}
const need = () => { assert.ok(render, 'geowatch-ui/src/render.js must exist'); return render }

let passed = 0
const tests = []
const test = (name, fn) => tests.push([name, fn])

/* ── the Dharavi fallback ── */

test('a result without tile_dimensions has no segment grid', () => {
  assert.equal(need().segmentGrid({}), null)
  assert.equal(need().segmentGrid({ tile_dimensions: { width: 291 } }), null)
  assert.equal(need().segmentGrid({ tile_dimensions: { width: 0, height: 10 } }), null)
  assert.equal(need().segmentGrid({ tile_dimensions: { width: '291', height: 257 } }), null)
})

test('a result with tile_dimensions uses exactly them', () => {
  assert.deepEqual(need().segmentGrid({ tile_dimensions: { width: 1059, height: 1001 } }),
    { width: 1059, height: 1001 })
})

test('App.jsx carries no Dharavi grid fallback', () => {
  assert.doesNotMatch(app, /\?\?\s*291/)
  assert.doesNotMatch(app, /\?\?\s*257/)
})

/* ── hardcoded category lists ── */

test('category labels are derived from the key, for any key', () => {
  assert.equal(need().humanize('dense_informal_roofing'), 'Dense informal roofing')
  assert.equal(need().humanize('some_future_class'), 'Some future class')
  assert.equal(need().humanize(null), need().MISSING)
})

test('App.jsx holds no category label table', () => {
  assert.doesNotMatch(app, /CAT_LABELS/)
})

test('every hazard the backend emits is rendered, not only the known five', () => {
  assert.deepEqual(need().hazardKeys({ pluvial: {}, volcanic: {} }), ['pluvial', 'volcanic'])
  assert.deepEqual(need().hazardKeys(undefined), [])
  assert.doesNotMatch(app, /Object\.entries\(SUSC_INFO\)/)
})

test('road styling reads the backend unpaved flag, not a private highway list', () => {
  assert.equal(need().isUnpaved({ properties: { unpaved: true } }), true)
  assert.equal(need().isUnpaved({ properties: { highway: 'track' } }), false,
    'a road with no flag (pre-item-58 run) must not be classified client-side')
  assert.doesNotMatch(app, /UNPAVED_HIGHWAY_TYPES/)
})

/* ── recomputed aggregates ── */

test('App.jsx does not recount segments by category', () => {
  assert.doesNotMatch(app, /segments \|\| \[\]\)\.filter/)
  assert.doesNotMatch(app, /informalCount/)
})

/* ── missing renders as missing ── */

test('a missing count is not shown as zero', () => {
  assert.doesNotMatch(app, /standing_water_segment_count \?\? 0/)
  assert.doesNotMatch(app, /'0\.0%'/)
})

test('a missing hazard class is not shown as "unknown"', () => {
  assert.doesNotMatch(app, /aoi_mean_class \|\| 'unknown'/)
})

test('a missing architecture is not filled with a model name', () => {
  assert.doesNotMatch(app, /architecture \|\| 'GeoWatchResNetSeg'/)
})

/* ── invented thresholds and facts ── */

test('no invented unknown_pct threshold', () => {
  assert.doesNotMatch(app, /unknown_pct\s*>\s*\d/)
})

test('fold count and population year come from the result', () => {
  assert.doesNotMatch(app, /one of its 11 training cities/)
  assert.doesNotMatch(app, /data available is from 2020/)
})

/* ── truncated caveats ── */

test('caveat lists are rendered whole', () => {
  assert.doesNotMatch(app, /items\.slice\(/)
})

/* ── hardcoded Q1-2024 window ── */

test('the analyze request carries no hardcoded date window', () => {
  assert.doesNotMatch(app, /2024-01-01/)
  assert.doesNotMatch(app, /2024-03-31/)
})

let failed = 0
for (const [name, fn] of tests) {
  try { fn(); passed++; console.log(`  ok    ${name}`) }
  catch (e) { failed++; console.log(`  FAIL  ${name}\n        ${e.message}`) }
}
console.log(`\n${passed} passed, ${failed} failed, ${tests.length} total`)
process.exit(failed === 0 ? 0 : 1)
