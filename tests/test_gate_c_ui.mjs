/*
 * C24 regression tests — the frontend never read `product_validation_status`.
 *
 * 04_FINDINGS_LEDGER.md C24 [S], build item 42: zero occurrences in App.jsx,
 * "so exposure is surfaced with no screening/experimental marker — the exact
 * outcome the Gate C waiver text was written to prevent. The susceptibility
 * panel does carry such a marker, in the same file — so the discipline exists;
 * it just was not applied here."
 *
 * Item 42 therefore says copy that exact pattern rather than invent one. These
 * tests check that the copy is faithful, not merely that something renders:
 * the same StatusPill-in-the-header mechanism, and the susceptibility panel's
 * own caveat-span style object, unchanged.
 *
 * Fixture is generated from the real backend, including a layer that actually
 * took the not_calculated path — the inland-AOI case C23 says never occurred on
 * the real runs.
 *
 * Run:  node tests/test_gate_c_ui.mjs
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const APP = join(here, '..', 'geowatch-ui', 'src', 'App.jsx')
const src = readFileSync(APP, 'utf8')
const fixture = JSON.parse(readFileSync(join(here, 'fixtures', 'result_gate_c.json'), 'utf8'))

const tests = []
const test = (n, f) => tests.push([n, f])

/* ── C24's literal claim ─────────────────────────────────────────────── */

test('product_validation_status is read in App.jsx', () => {
  const n = (src.match(/product_validation_status/g) || []).length
  assert.ok(n > 0, `C24 counted zero occurrences; still ${n}`)
})

test('the exposure panel reads the layer field, never a hardcoded string', () => {
  assert.match(src, /layer\.product_validation_status/,
    'exposure must read the value from the layer')
  assert.ok(!/['"]waived_pending_real_user_validation['"]\s*[,}]/.test(
    src.replace(/waived_pending_real_user_validation: \{[^}]*\}/g, '')
       .replace(/waived_pending_real_user_validation:\s*\n?\s*'\(not yet[^']*'/g, '')),
    'the waiver string must not be hardcoded as a value; read it from the data')
})

test('the risk panel reads the inherited field', () => {
  assert.match(src, /r\.exposure_product_validation_status/,
    'risk must surface the Gate C status it inherited from exposure')
})

/* ── "copy that exact pattern, do not invent a new one" ─────────────── */

test('the waiver renders through the same StatusPill mechanism as susceptibility', () => {
  // SecHazard: <ReportCard ... status={s.status}> -> StatusPill in the header.
  assert.match(src, /<ReportCard key=\{key\} title=\{info\.label\} status=\{s\.status\}>/,
    'precondition: the susceptibility pattern still looks the way C24 described')
  assert.match(src, /status=\{layer\.product_validation_status \|\| 'unavailable'\}/,
    'exposure must use the same status= prop on ReportCard')
})

test('the caveat span is the susceptibility span, unchanged', () => {
  // The susceptibility panel's experimental marker.
  const suscSpan = /fontFamily: FONTS\.body, fontSize: 11, color: C\.textDim \}\}>\(early-stage estimate/
  assert.match(src, suscSpan, 'precondition: the original marker still exists')
  // GateCNote must reuse that exact style object, not a lookalike.
  const gateCNote = src.slice(src.indexOf('function GateCNote'), src.indexOf('function GateCNote') + 420)
  assert.match(gateCNote, /fontFamily: FONTS\.body, fontSize: 11, color: C\.textDim/,
    'GateCNote must use the susceptibility caveat style verbatim')
})

test('the status vocabulary was extended, not replaced', () => {
  // 'waived_pending_real_user_validation' was ALREADY in STATUS_META before
  // item 42 -- the vocabulary existed and simply had nothing feeding it. A new
  // parallel vocabulary would have been the "invent a new pattern" failure.
  assert.match(src, /waived_pending_real_user_validation: \{ label: 'Validation pending', color: C\.amber \}/,
    'the pre-existing STATUS_META entry must be kept as-is')
  assert.match(src, /not_applicable_no_exposure_product: \{ label:/,
    'the no-product state must join the same STATUS_META table')
})

/* ── behaviour against real backend output ──────────────────────────── */

test('a layer that took the not_calculated path still carries the waiver', () => {
  const fluvial = fixture.exposure.by_evidence_layer.fluvial
  assert.equal(fluvial.status, 'not_calculated', 'precondition: this is C23s path')
  assert.equal(fluvial.product_validation_status, 'waived_pending_real_user_validation')
  assert.notEqual(fluvial.product_validation_status, undefined,
    'undefined here is what made waived indistinguishable from passed')
})

test('every risk layer in the fixture reports a Gate C status', () => {
  for (const [key, r] of Object.entries(fixture.risk.by_evidence_layer)) {
    assert.ok(r.exposure_product_validation_status,
      `risk/${key} dropped Gate C status`)
  }
})

test('every rendered status value has a STATUS_META entry', () => {
  // Otherwise statusMeta() falls back to de-underscoring the raw slug, and the
  // user reads a database value instead of a sentence.
  const seen = new Set()
  for (const l of Object.values(fixture.exposure.by_evidence_layer)) {
    if (l.product_validation_status) seen.add(l.product_validation_status)
  }
  for (const r of Object.values(fixture.risk.by_evidence_layer)) {
    if (r.exposure_product_validation_status) seen.add(r.exposure_product_validation_status)
  }
  assert.ok(seen.size > 0, 'fixture must exercise at least one value')
  for (const s of seen) {
    assert.ok(src.includes(`${s}: {`), `STATUS_META has no entry for ${s}`)
  }
})

test('both Gate C states have plain-language wording', () => {
  assert.match(src, /waived_pending_real_user_validation:\s*\n?\s*'\(not yet reviewed by a real user/,
    'the waiver needs a sentence, not a slug')
  assert.match(src, /not_applicable_no_exposure_product:\s*\n?\s*'\(nothing was computed here/,
    'the no-product state needs a sentence too')
})

test('the waived state raises a visible caveat, not just a pill', () => {
  assert.match(src, /layer\.product_validation_status === 'waived_pending_real_user_validation' && \(/,
    'the waiver should also produce the screening caveat the gate text demands')
  assert.match(src, /no planner, NGO or researcher has yet reviewed/,
    'the caveat must say plainly what has not happened')
})

/* ── run ─────────────────────────────────────────────────────────────── */

let passed = 0, failed = 0
for (const [name, fn] of tests) {
  try { fn(); passed++; console.log(`  ok    ${name}`) }
  catch (e) { failed++; console.log(`  FAIL  ${name}\n        ${e.message}`) }
}
console.log(`\n${passed} passed, ${failed} failed, ${tests.length} total`)
process.exit(failed === 0 ? 0 : 1)
