/*
 * Build item 36 (C33) — absent and measured-zero are distinguishable end to
 * end. The backend contract forbids a null value without an absent status
 * (tests/test_result_contract.py); this checks the renderer keeps them apart.
 *
 * Run:  node tests/test_measured_vs_absent_ui.mjs
 */
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const { fmtMeasured, MISSING } = await import(join(here, '..', 'geowatch-ui', 'src', 'render.js'))

const zero = fmtMeasured({ value: 0, status: 'available' })
assert.equal(zero.text, '0.0%')
assert.equal(zero.absent, false)

const notComputed = fmtMeasured({ value: null, status: 'not_computed' })
assert.equal(notComputed.text, MISSING)
assert.equal(notComputed.absent, true)
assert.equal(notComputed.reason, 'Not computed')

const dark = fmtMeasured({ value: null, status: 'insufficient_observation' })
assert.equal(dark.reason, 'Insufficient observation')
assert.notEqual(dark.text, zero.text)

assert.equal(fmtMeasured({ value: 0.25, status: 'available' }).text, '25.0%')
assert.equal(fmtMeasured({ value: 3, status: 'available' }, { percent: false, digits: 0 }).text, '3')
assert.equal(fmtMeasured(undefined).text, MISSING)
assert.equal(fmtMeasured({ value: NaN, status: 'available' }).absent, true)

console.log('measured vs absent: all checks passed')
