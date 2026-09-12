/*
 * C31 — the behavioural half of item 43's acceptance.
 *
 * "Changing a colour in the backend changes the rendered legend with NO
 * frontend edit." That is a statement about behaviour, so asserting that the
 * code looks right is not enough: the test below actually mutates the backend
 * palette, re-emits it, and checks what the frontend resolver returns — without
 * touching a line of frontend code between the two reads.
 *
 * Also asserted: the frontend holds no competing palette, and a run produced
 * before item 43 still renders (from a frozen legacy shim that must never be
 * "corrected" into a second live source).
 *
 * Run:  node tests/test_palette_ui.mjs
 */

import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const repo = join(here, '..')
const APP = join(repo, 'geowatch-ui', 'src', 'App.jsx')
const {
  categoryColor, legendEntries, paletteOf, hasPalette, isLegacyRender, NO_COLOR,
} = await import(join(repo, 'geowatch-ui', 'src', 'palette.js'))

const load = n => JSON.parse(readFileSync(join(here, 'fixtures', `result_${n}.json`), 'utf8'))
const MODERN = load('clean')
const LEGACY = load('pre_item40')
const appSrc = readFileSync(APP, 'utf8')

/** Emit the palette from the real backend, optionally overriding one colour. */
function emitPalette(override) {
  const py = override
    ? `import json
from configs.palette import CATEGORY_COLORS_RGB, palette_for_result
CATEGORY_COLORS_RGB[${JSON.stringify(override.category)}] = ${JSON.stringify(override.rgb)}
print(json.dumps(palette_for_result()))`
    : `import json
from configs.palette import palette_for_result
print(json.dumps(palette_for_result()))`
  const out = execFileSync(join(repo, 'geowatch-env', 'bin', 'python'), ['-c', py],
    { cwd: repo, encoding: 'utf8' })
  return JSON.parse(out)
}

const tests = []
const test = (n, f) => tests.push([n, f])

/* ── THE ACCEPTANCE CRITERION ───────────────────────────────────────── */

test('ACCEPTANCE: a backend colour change moves the legend, no frontend edit', () => {
  const before = readFileSync(APP, 'utf8')

  const baseline = emitPalette()
  const changed = emitPalette({ category: 'dense_vegetation', rgb: [1, 2, 3] })

  const resultBefore = { landcover: { palette: baseline } }
  const resultAfter = { landcover: { palette: changed } }

  assert.equal(categoryColor(resultBefore, 'dense_vegetation'), '#3cb450',
    'baseline colour should be the canonical one')
  assert.equal(categoryColor(resultAfter, 'dense_vegetation'), '#010203',
    'the legend colour must follow the backend')

  // The legend itself, not just the resolver.
  const entry = legendEntries(resultAfter).find(e => e.category === 'dense_vegetation')
  assert.equal(entry.color, '#010203', 'legendEntries must reflect the change')

  // The whole point: nothing on this side moved.
  assert.equal(readFileSync(APP, 'utf8'), before,
    'App.jsx changed during the test — the acceptance criterion is zero frontend edits')
})

test('every emitted category resolves, including unknown', () => {
  const palette = emitPalette()
  const result = { landcover: { palette } }
  for (const name of Object.keys(palette.colors)) {
    assert.equal(categoryColor(result, name), palette.colors[name], `${name} mismatched`)
  }
  assert.equal(categoryColor(result, 'unknown'), palette.colors.unknown,
    'the unknown row must resolve from the emitted palette (item 43)')
})

/* ── No competing source ────────────────────────────────────────────── */

test('App.jsx no longer defines a colour map', () => {
  assert.ok(!appSrc.includes('const CAT_COLORS = {'),
    'a hardcoded palette is back in App.jsx')
})

test('App.jsx contains none of the canonical colour values', () => {
  // Not even correct copies: a correct copy still drifts at the next edit,
  // which is precisely how 0 of 8 happened.
  const palette = emitPalette()
  for (const [name, hex] of Object.entries(palette.colors)) {
    assert.ok(!appSrc.includes(hex), `${name}'s value ${hex} is hardcoded in App.jsx`)
  }
})

test('every colour consumer reads through the resolver', () => {
  // Four sites used CAT_COLORS before item 43. None may reach for a map again.
  assert.ok(!/CAT_COLORS\[/.test(appSrc), 'a consumer still indexes a local colour map')
  assert.match(appSrc, /categoryColor\(result,/, 'consumers must call the resolver')
  assert.match(appSrc, /legendEntries\(result\)/, 'the legend must come from the result')
  assert.match(appSrc, /colorFor=\{cat => categoryColor\(result, cat\)\}/,
    'map components must be handed the resolver, not a palette')
})

/* ── Legacy runs still render, without becoming a second source ─────── */

test('a run predating item 43 still renders colours', () => {
  assert.equal(hasPalette(LEGACY), false, 'precondition: fixture has no palette')
  assert.equal(isLegacyRender(LEGACY), true)
  assert.equal(categoryColor(LEGACY, 'dense_vegetation'), '#5ed99b',
    'archived runs should render with the colours they were produced under')
})

test('the legacy shim is never consulted for a modern run', () => {
  assert.equal(hasPalette(MODERN), true)
  assert.equal(categoryColor(MODERN, 'dense_vegetation'), '#3cb450',
    'a run with a palette must never fall back to the old values')
  // Even for a category the palette does not list: falling back per-category
  // would render half a legend from each source, which is C31 again, finer.
  assert.equal(categoryColor(MODERN, 'a_category_that_does_not_exist'), NO_COLOR)
})

test('unknown category and missing result degrade safely', () => {
  assert.equal(categoryColor(MODERN, null), NO_COLOR)
  assert.equal(categoryColor(undefined, 'dense_vegetation'), '#5ed99b',
    'no result at all falls back to legacy, not to a crash')
  assert.equal(paletteOf({ landcover: {} }), null)
  assert.equal(paletteOf({ landcover: { palette: { source: 'x' } } }), null,
    'a palette block with no colors map is not a palette')
})

/* ── The API key wiring (live breakage from item 70) ────────────────── */

test('no raw fetch() remains for API calls', () => {
  const rawFetches = [...appSrc.matchAll(/(?<!api)fetch\(`\$\{API\}/g)]
  assert.equal(rawFetches.length, 0,
    'an API call bypasses apiFetch and will 401')
})

test('every API call goes through the authenticated helper', () => {
  assert.match(appSrc, /apiFetch\('\/api\/analyze'/, 'analyze must be authenticated')
  assert.match(appSrc, /apiFetch\(`\/runs\/\$\{runId\}\/osm\/roads\.geojson`\)/)
  assert.match(appSrc, /apiFetch\(`\/runs\/\$\{runId\}\/osm\/waterways\.geojson`\)/)
})

test('the image overlay is fetched with credentials, not as a bare <img>', () => {
  // <img> cannot carry a header, and /runs is behind the key since item 70, so
  // a plain URL would silently 401 and the overlay would just not appear.
  assert.match(appSrc, /useAuthedImage\(landcoverImagePath\(result\)\)/)
  const api = readFileSync(join(repo, 'geowatch-ui', 'src', 'api.js'), 'utf8')
  assert.match(api, /createObjectURL/, 'image bytes must be fetched and blob-wrapped')
  assert.match(appSrc, /revokeObjectURL/, 'the blob URL must be revoked or it leaks')
})

test('the key is read from the environment, never hardcoded', () => {
  const api = readFileSync(join(repo, 'geowatch-ui', 'src', 'api.js'), 'utf8')
  assert.match(api, /import\.meta\.env\?\.VITE_GEOWATCH_API_KEY/)
  assert.ok(!/API_KEY\s*=\s*['"][A-Za-z0-9_-]{10,}['"]/.test(api),
    'a literal key must never be committed')
})

test('a missing key produces a visible, actionable message', () => {
  // Before item 43 every request 401'd and the surfaced error said nothing
  // about a key at all.
  assert.match(appSrc, /isKeyMissing\(\) && \(/, 'a missing key must be visible up front')
  assert.match(appSrc, /VITE_GEOWATCH_API_KEY/, 'the message must name the variable')
  assert.match(appSrc, /res\.status === 401/, '401 must be handled distinctly')
})

test('.env.example exists and carries no value', () => {
  const ex = readFileSync(join(repo, 'geowatch-ui', '.env.example'), 'utf8')
  assert.match(ex, /VITE_GEOWATCH_API_KEY=\s*$/m, 'the example must ship empty')
  assert.match(ex, /INLINES/, 'the example must warn that the value reaches the bundle')
})

/* ── run ─────────────────────────────────────────────────────────────── */

let passed = 0, failed = 0
for (const [name, fn] of tests) {
  try { fn(); passed++; console.log(`  ok    ${name}`) }
  catch (e) { failed++; console.log(`  FAIL  ${name}\n        ${e.message}`) }
}
console.log(`\n${passed} passed, ${failed} failed, ${tests.length} total`)
process.exit(failed === 0 ? 0 : 1)
