/*
 * Build item 20, the UI half: the coverage of the AOI being viewed, in plain
 * language, visibly flagged when low.
 *
 * The blocks under test are emitted by the REAL analysis pipeline
 * (analysis.run.run_analysis over synthetic layers, tests/analysis_synth.py),
 * wrapped the way POST /api/analyze returns them, so the UI is checked
 * against the shape the API actually serves. geowatch-ui/src/coverage.js is
 * tested by behaviour; App.jsx is checked structurally, because it cannot be
 * rendered here without a browser.
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
  coverageBlockOf, coverageView, partialFetches, percentileText, densityText, NOT_MEASURABLE,
} = await import(join(SRC, 'coverage.js'))
const coverageSrc = readFileSync(join(SRC, 'coverage.js'), 'utf8')
const app = readFileSync(join(SRC, 'App.jsx'), 'utf8')

/** One /api/analyze response per case: adequate, very_low, a partial fetch,
 *  and a missing pedestrian clause. None is a reference AOI. */
function emitResponses() {
  const py = `import json, sys
sys.path.insert(0, "tests")
from tests import analysis_synth as S
from vector import roads
from vector_synth import BBOX, _fix_ns, _layer, _way, _highways, service_missing_layer

def foot(n):
    return [_fix_ns(_way(100 + k, "footway", 0, 0, 0, [1000 + 3 * k, 1001 + 3 * k, 1002 + 3 * k]))
            for k in range(n)]

layers = {
    "dense": lambda: _layer(foot(9)),
    "thin": lambda: _layer([]),
    "partial": service_missing_layer,
    "no_ped_clause": lambda: roads.build_road_layer(
        "t", BBOX, highways=_highways(foot(9), unavailable=["narrow_pedestrian"]),
        footprints_4326=[], footprint_source="none"),
}
out = {}
for k, f in layers.items():
    r, _ = S.run(deps=S.deps(load_layer=lambda name, bbox, f=f: f()))
    r.pop("_maps")
    out[k] = {"result_id": k, "cached": False, "stored": False, "result": r}
print(json.dumps(out))`
  const out = execFileSync(join(repo, 'geowatch-env', 'bin', 'python'), ['-c', py],
    { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
  return JSON.parse(out.trim().split('\n').pop())
}

const RESPONSES = emitResponses()
const block = name => coverageBlockOf(RESPONSES[name])
const views = Object.fromEntries(Object.keys(RESPONSES).map(k => [k, coverageView(block(k))]))
const mainText = v => [v.headline, ...v.notes].join(' ')

const tests = []
const test = (n, f) => tests.push([n, f])

/* ── One AOI, plain language ───────────────────────────────────────── */

test('the block is read from the analysis response for this AOI', () => {
  for (const k of Object.keys(RESPONSES)) {
    assert.equal(block(k), RESPONSES[k].result.outputs.osm_coverage, k)
  }
  assert.equal(coverageBlockOf(RESPONSES.dense.result), block('dense'), 'a bare result works too')
  assert.equal(coverageBlockOf(null), null)
  assert.equal(coverageView(null), null, 'no AOI viewed: no panel content, not a default')
})

test('a very_low AOI says the road map is incomplete and what is hidden', () => {
  const v = views.thin
  assert.equal(block('thin').coverage_regime_flag, 'very_low')
  assert.equal(v.warning, true)
  assert.equal(v.headline, 'Road map incomplete: street-network results hidden')
})

test('an adequate AOI does not warn', () => {
  const v = views.dense
  assert.equal(block('dense').coverage_regime_flag, 'adequate')
  assert.equal(v.warning, false)
  assert.equal(v.headline, 'Road map adequate: nothing hidden')
  assert.equal(percentileText(v), `${block('dense').value}`)
})

test('not_measurable says so, and never shows a number', () => {
  const v = views.no_ped_clause
  assert.equal(block('no_ped_clause').coverage_regime_flag, 'not_measurable')
  assert.equal(typeof block('no_ped_clause').value, 'number', 'the backend does carry one')
  assert.equal(v.warning, true)
  assert.equal(v.measurable, false)
  assert.equal(v.headline, 'Road map could not be checked: street-network results hidden')
  assert.equal(v.percentile, null)
  assert.equal(v.narrowDensity, null)
  assert.equal(percentileText(v), NOT_MEASURABLE)
  assert.equal(densityText(v), NOT_MEASURABLE)
})

test('a partial fetch is named in plain language', () => {
  const v = views.partial
  assert.ok(v.notes.includes('Some road types could not be downloaded: service.'), v.notes)
  assert.ok(v.partialFetch.length > 0)
  for (const p of v.partialFetch) assert.deepEqual(p.missingClauses, ['service'])
  assert.deepEqual(views.dense.partialFetch, [])
})

test('the main text carries no percentile, density or unit', () => {
  for (const [k, v] of Object.entries(views)) {
    assert.doesNotMatch(mainText(v), /\d|km|percentile|pctl/i, k)
  }
})

test('partialFetches finds the status at any depth and nowhere else', () => {
  assert.deepEqual(partialFetches({ a: { b: { status: 'partial_fetch', missing_clauses: ['x'] } }, c: { status: 'complete' } }),
    [{ field: 'a.b', missingClauses: ['x'], note: null }])
  assert.deepEqual(partialFetches(null), [])
})

/* ── Reads, never re-derives ───────────────────────────────────────── */

test('a block without the warning field still warns', () => {
  assert.equal(coverageView({ coverage_regime_flag: 'adequate' }).warning, true)
  const none = coverageView({})
  assert.equal(none.warning, true)
  assert.equal(none.measurable, false)
  assert.equal(none.headline, 'Road map could not be checked: results may be affected')
})

test('the warning follows the backend flag, not the regime name', () => {
  const v = coverageView({ coverage_regime_flag: 'some_new_regime', low_coverage_warning: true })
  assert.equal(v.warning, true)
  assert.equal(v.regimeLabel, 'Some new regime')
  assert.equal(v.headline, 'Road map incomplete: results may be affected')
})

test('coverage.js holds no thresholds and no regime list', () => {
  const code = coverageSrc.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
  assert.doesNotMatch(code, /\b\d+\.\d+\b/, 'no decimal constants')
  assert.doesNotMatch(code, /[<>]=?\s*\d/, 'no numeric comparisons')
  for (const regime of ["'adequate'", "'very_low'", "'low'"]) assert.ok(!code.includes(regime), regime)
})

/* ── App.jsx wiring ────────────────────────────────────────────────── */

test('App.jsx shows the viewed result, not a stored list of AOIs', () => {
  assert.match(app, /from '\.\/coverage'/)
  assert.match(app, /<CoveragePanel view=\{coverageView\(coverageBlockOf\(result\)\)\} \/>/)
  assert.ok(!app.includes('/api/vector/coverage'), 'App.jsx fetches the stored reference report')
  assert.ok(!app.includes('coverageRows'), 'App.jsx renders rows of AOIs')
})

test('App.jsx puts the headline in the main text and numbers only in the details', () => {
  assert.match(app, /data-testid="coverage-headline"/)
  assert.match(app, /\{view\.headline\}/)
  const panel = app.slice(app.indexOf('function CoveragePanel'), app.indexOf('GATE C WAIVER'))
  const details = panel.slice(panel.indexOf('<Disclosure>'), panel.indexOf('</Disclosure>'))
  assert.ok(details.length > 0, 'details disclosure')
  for (const s of ['percentileText(view)', 'densityText(view)', 'km/km²', 'view.reasons', 'view.partialFetch']) {
    assert.ok(details.includes(s), `${s} inside the details`)
    assert.equal(panel.split(s).length - 1, details.split(s).length - 1, `${s} outside the details`)
  }
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
