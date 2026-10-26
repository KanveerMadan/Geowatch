/*
 * C8 / build item 53 — the frontend half. App.jsx rendered INFORM's
 * `raw_score` into "x / 10" with no type check (the ledger's App.jsx:568/572,
 * now further down the file), so a bad cell displayed to the user as a score.
 *
 * The guard lives in geowatch-ui/src/inform.js. It checks type only; range is
 * the backend's job (see that module's header).
 *
 * Run:  node tests/test_inform_ui.mjs
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const appSrc = readFileSync(join(here, '..', 'geowatch-ui', 'src', 'App.jsx'), 'utf8')

// Imported defensively, so that against the pre-item-53 tree each test
// reports its own failure instead of the whole file dying on import.
let inform = null
try {
  inform = await import(join(here, '..', 'geowatch-ui', 'src', 'inform.js'))
} catch (e) {
  inform = null
}
const need = () => { assert.ok(inform, 'geowatch-ui/src/inform.js must exist'); return inform }

let passed = 0
const tests = []
const test = (name, fn) => tests.push([name, fn])

test('a real score renders as a number', () => {
  assert.equal(need().formatInformNumber(5.4), '5.4')
  assert.equal(need().formatInformNumber(3.21, 2), '3.21')
})

for (const [label, bad] of [
  ['null', null], ['undefined', undefined], ['text', 'x'],
  ['numeric-looking text', '5.0'], ['NaN', NaN], ['Infinity', Infinity],
  ['object', { v: 1 }], ['bool', true],
]) {
  test(`a ${label} score renders as missing, never as a value`, () => {
    assert.equal(need().formatInformNumber(bad), need().MISSING)
    assert.equal(need().formatInformFraction(bad), need().MISSING)
  })
}

test('missing-indicator fraction renders as a percentage', () => {
  assert.equal(need().formatInformFraction(0.12), '12.0%')
})

test('App.jsx passes no raw INFORM value straight into a Metric', () => {
  assert.doesNotMatch(appSrc, /value=\{v\.dimensions\?\.\w+\?\.raw_score\}/,
    'raw_score must go through the inform.js guard')
  assert.doesNotMatch(appSrc, /lack_of_reliability_score\?\.toFixed/,
    'optional-chained toFixed renders "—" for null but passes strings through unformatted')
})

test('App.jsx reads the guard', () => {
  assert.match(appSrc, /from '\.\/inform'/)
})

let failed = 0
for (const [name, fn] of tests) {
  try { fn(); passed++; console.log(`  ok    ${name}`) }
  catch (e) { failed++; console.log(`  FAIL  ${name}\n        ${e.message}`) }
}
console.log(`\n${passed} passed, ${failed} failed, ${tests.length} total`)
process.exit(failed === 0 ? 0 : 1)
