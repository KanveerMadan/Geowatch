/*
 * Build item 20, the UI half: "a low-coverage AOI is visibly flagged
 * end-to-end through to the UI".
 *
 * The report under test is emitted by the REAL backend
 * (vector.coverage_report.build_report over synthetic layers), so the UI is
 * checked against the shapes the API actually serves, not hand-written ones.
 * geowatch-ui/src/coverage.js is tested by behaviour; App.jsx is checked
 * structurally, because it cannot be rendered here without a browser.
 *
 * Run:  node tests/test_coverage_ui.mjs
 */

import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const repo = join(here, '..')
const SRC = join(repo, 'geowatch-ui', 'src')
const {
  coverageRows, partialFetches, percentileText, densityText, warningHeadline, NOT_MEASURABLE,
} = await import(join(SRC, 'coverage.js'))
const coverageSrc = readFileSync(join(SRC, 'coverage.js'), 'utf8')
const app = readFileSync(join(SRC, 'App.jsx'), 'utf8')

/** One report from the backend: very_low, adequate, a partial fetch, a
 *  missing pedestrian clause, and an AOI whose inputs raised. */
function emitReport() {
  const py = `import json, sys
sys.path.insert(0, "tests")
from vector import coverage_report, roads
from vector_synth import BBOX, _fix_ns, _layer, _way, _highways, service_missing_layer

def foot(n):
    return [_fix_ns(_way(100 + k, "footway", 0, 0, 0, [1000 + 3 * k, 1001 + 3 * k, 1002 + 3 * k]))
            for k in range(n)]

def inputs(name, bbox):
    if name == "dense":
        return _layer(foot(9)), None
    if name == "thin":
        return _layer([]), None
    if name == "partial":
        return service_missing_layer(), None
    if name == "no_ped_clause":
        return roads.build_road_layer("t", BBOX, highways=_highways(foot(9), unavailable=["narrow_pedestrian"]),
                                      footprints_4326=[], footprint_source="none"), None
    raise RuntimeError("Earth Engine down")

aois = {n: {"bbox": BBOX} for n in ("dense", "thin", "partial", "no_ped_clause", "broken")}
print(json.dumps(coverage_report.build_report(aois, inputs=inputs)))`
  const out = execFileSync(join(repo, 'geowatch-env', 'bin', 'python'), ['-c', py],
    { cwd: repo, encoding: 'utf8' })
  return JSON.parse(out.trim().split('\n').pop())
}

const REPORT = emitReport()
const rows = Object.fromEntries(coverageRows(REPORT).map(r => [r.aoi, r]))

const tests = []
const test = (n, f) => tests.push([n, f])

/* ── The three the brief names ─────────────────────────────────────── */

test('a very_low AOI renders the warning', () => {
  const r = rows.thin
  assert.equal(r.regime, 'very_low')
  assert.equal(r.warning, true)
  assert.equal(warningHeadline(r), 'OSM coverage very low')
  assert.ok(r.reasons.length > 0 && r.reasons[0].includes('narrow pedestrian density'))
  assert.equal(r.topologySuppressed, true)
})

test('an adequate AOI does not render the warning', () => {
  const r = rows.dense
  assert.equal(r.regime, 'adequate')
  assert.equal(r.warning, false)
  assert.equal(r.measurable, true)
  assert.equal(percentileText(r), `${REPORT.aois[0].coverage.osm_density_percentile}`)
})

test('not_measurable is shown as such, never as a number', () => {
  for (const name of ['no_ped_clause', 'broken']) {
    const r = rows[name]
    assert.equal(r.regime, 'not_measurable', name)
    assert.equal(r.warning, true, name)
    assert.equal(r.measurable, false, name)
    assert.equal(r.percentile, null, name)
    assert.equal(r.narrowDensity, null, name)
    assert.equal(percentileText(r), NOT_MEASURABLE, name)
    assert.equal(densityText(r), NOT_MEASURABLE, name)
    assert.doesNotMatch(percentileText(r) + densityText(r), /\d/, name)
  }
  // The scored-but-unmeasurable block DOES carry numbers from the backend;
  // the point is that none of them is displayed.
  const raw = REPORT.aois.find(a => a.aoi === 'no_ped_clause').coverage
  assert.equal(typeof raw.osm_density_percentile, 'number')
  assert.match(rows.broken.reasons[0], /RuntimeError: Earth Engine down/)
})

/* ── Partial fetch ─────────────────────────────────────────────────── */

test('partial_fetch statuses are surfaced where the backend marks them', () => {
  const r = rows.partial
  const fields = r.partialFetch.map(p => p.field).sort()
  assert.ok(fields.includes('footprints_per_road_km.fetch'), fields)
  assert.ok(fields.includes('road_length_fetch.all'), fields)
  assert.ok(fields.includes('road_length_fetch.broad_pedestrian'), fields)
  // arterial/pedestrian reads no service clause, so it stays complete.
  assert.ok(!fields.includes('arterial_to_pedestrian_ratio.fetch'), fields)
  for (const p of r.partialFetch) {
    assert.deepEqual(p.missingClauses, ['service'])
    assert.match(p.note, /LOWER BOUND/)
  }
  assert.deepEqual(rows.dense.partialFetch, [])
})

test('partialFetches finds the status at any depth and nowhere else', () => {
  assert.deepEqual(partialFetches({ a: { b: { status: 'partial_fetch', missing_clauses: ['x'] } }, c: { status: 'complete' } }),
    [{ field: 'a.b', missingClauses: ['x'], note: null }])
  assert.deepEqual(partialFetches(null), [])
})

/* ── Reads, never re-derives ───────────────────────────────────────── */

test('a block without the warning field still warns', () => {
  const [r] = coverageRows({ aois: [{ aoi: 'old', coverage: { coverage_regime_flag: 'adequate' } }] })
  assert.equal(r.warning, true)
  const [none] = coverageRows({ aois: [{ aoi: 'x', coverage: {} }] })
  assert.equal(none.warning, true)
  assert.equal(none.measurable, false)
  assert.equal(warningHeadline(none), 'OSM coverage: no regime reported')
})

test('the warning follows the backend flag, not the regime name', () => {
  const [r] = coverageRows({ aois: [{ aoi: 'x', coverage: { coverage_regime_flag: 'some_new_regime', low_coverage_warning: true } }] })
  assert.equal(r.warning, true)
  assert.equal(r.regimeLabel, 'Some new regime')
})

test('coverage.js holds no thresholds and no regime list', () => {
  const code = coverageSrc.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
  assert.doesNotMatch(code, /\b\d+\.\d+\b/, 'no decimal constants')
  assert.doesNotMatch(code, /[<>]=?\s*\d/, 'no numeric comparisons')
  for (const regime of ['adequate', 'very_low', "'low'"]) assert.ok(!code.includes(regime), regime)
})

test('no report means no rows, not a default', () => {
  assert.deepEqual(coverageRows(null), [])
  assert.deepEqual(coverageRows({}), [])
})

test('rows keep the backend order', () => {
  assert.deepEqual(coverageRows(REPORT).map(r => r.aoi), REPORT.aois.map(a => a.aoi))
})

/* ── App.jsx wiring ────────────────────────────────────────────────── */

test('App.jsx fetches the report through the authenticated helper', () => {
  assert.match(app, /from '\.\/coverage'/)
  assert.equal((app.match(/apiFetch\('\/api\/vector\/coverage'\)/g) || []).length, 1)
  assert.match(app, /<CoveragePanel report=\{coverageReport\} error=\{coverageError\} \/>/)
})

test('App.jsx renders the warning, not-measurable and partial-fetch states', () => {
  assert.match(app, /\{row\.warning && \(\s*<div role="alert" data-testid="coverage-warning"/)
  assert.match(app, /data-testid="coverage-not-measurable"/)
  assert.match(app, /row\.partialFetch\.map\(/)
  assert.match(app, /data-testid="coverage-partial-fetch"/)
  // The number only appears on the measurable branch.
  assert.match(app, /\{row\.measurable\s*\? <>pctl \{percentileText\(row\)\}/)
})

test('App.jsx re-derives nothing about coverage', () => {
  for (const s of ['coverage_regime_flag', 'low_coverage_warning', 'osm_density_percentile',
                   'narrow_pedestrian_km_per_km2', "'very_low'", "'not_measurable'"]) {
    assert.ok(!app.includes(s), `App.jsx reads ${s} directly`)
  }
})

let failed = 0
for (const [name, fn] of tests) {
  try { fn(); console.log(`  ok    ${name}`) }
  catch (e) { failed++; console.log(`  FAIL  ${name}\n        ${e.message.split('\n')[0]}`) }
}
console.log(`\n${tests.length - failed} passed, ${failed} failed, ${tests.length} total`)
process.exit(failed ? 1 : 0)
