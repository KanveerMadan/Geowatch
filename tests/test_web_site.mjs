/*
 * The public site's logic (web/src/lib route / honesty / gallery / tiles),
 * checked under node, plus the rule that the honesty page types no figure
 * of its own: every number comes from generated/honesty.json.
 *
 * Run:  node tests/test_web_site.mjs
 */
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const web = (...p) => join(here, '..', 'web', 'src', ...p)
const lib = (f) => import(web('lib', f))
const R = await lib('route.js')
const H = await lib('honesty.js')
const G = await lib('gallery.js')
const T = await lib('tiles.js')
const L = await lib('link.js')
const honesty = JSON.parse(readFileSync(web('generated', 'honesty.json'), 'utf8'))
const gallery = JSON.parse(readFileSync(web('generated', 'gallery.json'), 'utf8'))

let n = 0
const test = (name, fn) => { fn(); n += 1 }

// ── routes ──
test('paths map to pages', () => {
  assert.equal(R.routeOf('/', '').page, 'landing')
  assert.equal(R.routeOf('/explore', '').page, 'explore')
  assert.equal(R.routeOf('/gallery/', '').page, 'gallery')
  assert.equal(R.routeOf('/honesty', '').page, 'honesty')
  assert.equal(R.routeOf('/nope', '').page, 'notfound')
})
test('old permanent links still open the explorer and the report', () => {
  assert.equal(R.routeOf('/', '?bbox=1,2,3,4').page, 'explore')
  assert.equal(R.routeOf('/', '?job=j' + '0'.repeat(24)).page, 'explore')
  const r = R.routeOf('/explore', '?report=r' + 'a'.repeat(24) + '&name=X')
  assert.equal(r.page, 'report')
  assert.equal(r.report.name, 'X')
  assert.equal(R.routeOf('/', '?report=bad').page, 'landing')
})
test('exploreHref round-trips through the explorer link parser', () => {
  const href = R.exploreHref([72.836, 19.037, 72.862, 19.06])
  assert.deepEqual(L.parseLink(href.split('?')[1]).bbox, [72.836, 19.037, 72.862, 19.06])
})

// ── honesty ──
test('every flood type in the contract appears in exactly one section', () => {
  const s = H.floodSections(honesty)
  const ids = [...s.validated, ...s.experimental, ...s.failed, ...s.notBuilt].map((r) => r.id).sort()
  assert.deepEqual(ids, honesty.flood.map((r) => r.id).sort())
  assert.equal(ids.length, new Set(ids).size)
})
test('a validated type always carries its scope; a failed one its evidence', () => {
  const s = H.floodSections(honesty)
  for (const r of s.validated) assert.ok(r.scope?.regions?.length && r.scope.events.length)
  for (const r of s.failed) assert.ok(r.evidence && r.evidence.auc < honesty.bar.validated_if_auc_at_least)
})
test('evidence sentences say which side of the bar, with the bar read from data', () => {
  const s = H.floodSections(honesty)
  for (const r of s.failed) assert.match(H.evidenceSentence(r, honesty.bar), /below the bar/)
  for (const r of s.validated) assert.match(H.evidenceSentence(r, honesty.bar), /at or above the bar/)
  assert.equal(H.fmtAuc(null), 'not run')
})
test('the honesty page and landing type no figure of their own', () => {
  for (const f of ['Honesty.jsx', 'Landing.jsx', 'Gallery.jsx']) {
    const src = readFileSync(web('site', f), 'utf8').replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '')
    // No decimals (AUCs, shares) and no percentages in the page source.
    assert.doesNotMatch(src, /\b0\.\d{2,}\b|\d+(\.\d+)?\s*%/, f)
  }
})

// ── gallery ──
test('absent headline values are words, never 0', () => {
  for (const c of gallery.cities) {
    const m = G.cardModel(c)
    for (const r of [...m.ground, ...m.floods]) {
      if (r.status !== 'available') {
        assert.equal(r.measured, false)
        assert.doesNotMatch(r.display, /\d/)
      }
      assert.ok(r.label, `${c.key}.${r.key} has no label`)
    }
    assert.match(m.reportHref, /^\?report=r[0-9a-f]{24}/)
  }
})
test('a measured zero stays a zero, and a tiny share is not rounded to it', () => {
  assert.equal(G.headlineValue({ value: 0, status: 'available' }).display, '0%')
  assert.equal(G.headlineValue({ value: 0.001, status: 'available' }).display, '<1%')
  assert.equal(G.headlineValue({ value: null, status: 'not_computed' }).display, 'Not yet measured')
})

// ── tiles ──
test('the tile window covers the thumbnail and frames the box inside it', () => {
  const t = T.tileWindow([72.836, 19.037, 72.862, 19.06], 352, 176)
  assert.ok(t.box.left > 0 && t.box.top > 0 && t.box.left + t.box.width < 352 && t.box.top + t.box.height < 176)
  const minL = Math.min(...t.tiles.map((x) => x.left)), minT = Math.min(...t.tiles.map((x) => x.top))
  const maxR = Math.max(...t.tiles.map((x) => x.left + 256)), maxB = Math.max(...t.tiles.map((x) => x.top + 256))
  assert.ok(minL <= 0 && minT <= 0 && maxR >= 352 && maxB >= 176)
})

console.log(`web site: ${n} passed`)
