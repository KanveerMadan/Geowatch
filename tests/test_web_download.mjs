/*
 * Downloads with provenance (web/src/lib/download.js), checked under node:
 * public unit types only, every output's value/status/label/coverage/sources,
 * absent never 0, provenance and licence notes in both formats, and CSV
 * injection neutralised.
 *
 * Run:  node tests/test_web_download.mjs
 */
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const D = await import(join(here, '..', 'web', 'src', 'lib', 'download.js'))

let n = 0
const test = (name, fn) => { fn(); n += 1 }

const mv = { code_commit: 'c0ffee', artifact_hash: 'a', version_id: 'v123' }
const out = (value, status, label, sources, extra = {}) => ({
  value, status, validation_status: label, coverage: { observed_fraction: value === null ? 0 : 0.9, basis: 'b' },
  data_sources: sources, model_version: mv, ...extra,
})
const result = {
  result_id: 'r' + 'a'.repeat(24), created_utc: '2026-10-31T09:00:27+00:00', model_version: mv,
  request: { bbox: [1, 2, 3, 4], window: { start: '2026-08-01', end: '2026-10-30' } },
}
const units = [
  { unit_type: 'ward:x', unit_index: 0, unit_id: 'W1', unit_name: '=HYPERLINK("x")', area_m2: 1000,
    geometry: { type: 'Polygon', coordinates: [[[1, 2], [3, 2], [3, 4], [1, 2]]] },
    outputs: {
      fractions: {
        built: out(0, 'available', 'experimental', ['GOOGLE/Research/open-buildings/v3/polygons']),
        paved: out(null, 'not_computed', 'placeholder', ['none: not computed'], { reason: 'needs item 21' }),
      },
      susceptibility: {
        fluvial: out(0.81, 'available', 'validated', ['MERIT/Hydro/v1_0_1 (hnd, upa)'],
          { tier: 'very_high', validated_scope: { regions: ['Hanoi', 'Kolonnawa'], events: ['e'], input_versions: { a: 1 } } }),
        pluvial: out(0.4, 'available', 'failed', ['projects/sat-io/open-datasets/FABDEM']),
      },
    } },
]

test('only wards and the 100 m grid are public', () => {
  assert.deepEqual(D.PUBLIC_UNIT_TYPES(['grid', 'footprint', 'path', 'ward:mumbai']), ['grid', 'ward:mumbai'])
})
test('every output becomes one record with its label, coverage and sources', () => {
  const rows = D.unitRecords(result, units)
  assert.equal(rows.length, 4)
  for (const r of rows) {
    assert.equal(r.result_id, result.result_id)
    assert.equal(r.model_version, 'v123')
    assert.ok(r.validation_status && r.data_sources && r.coverage_basis)
  }
  const fl = rows.find((r) => r.output === 'susceptibility.fluvial')
  assert.match(fl.validated_scope, /Hanoi; Kolonnawa/)
})
test('absent is null with its status; a measured zero stays 0', () => {
  const rows = D.unitRecords(result, units)
  assert.equal(rows.find((r) => r.output === 'fractions.paved').value, null)
  assert.equal(rows.find((r) => r.output === 'fractions.paved').status, 'not_computed')
  assert.equal(rows.find((r) => r.output === 'fractions.built').value, 0)
  const gj = D.toGeoJSON(result, units)
  assert.equal(gj.features[0].properties['fractions.paved'], null)
  assert.equal(gj.features[0].properties['fractions.built'], 0)
})
test('GeoJSON carries provenance, licence notes and per-output fields', () => {
  const gj = D.toGeoJSON(result, units)
  assert.equal(gj.type, 'FeatureCollection')
  assert.equal(gj.geowatch.result_id, result.result_id)
  assert.equal(gj.geowatch.model_version, 'v123')
  assert.ok(gj.geowatch.licence_notes.some((l) => l.includes('FABDEM') && l.includes('Non-commercial')))
  assert.ok(gj.geowatch.licence_notes.some((l) => l.includes('MERIT Hydro')))
  const p = gj.features[0].properties
  for (const k of ['susceptibility.fluvial', 'susceptibility.fluvial_status', 'susceptibility.fluvial_validation',
    'susceptibility.fluvial_coverage', 'susceptibility.fluvial_sources', 'susceptibility.fluvial_tier']) assert.ok(k in p, k)
  assert.equal(p.result_id, result.result_id)
})
test('CSV has provenance lines, a header, one row per output, formulas neutralised', () => {
  const csv = D.toCSV(result, units)
  const lines = csv.trim().split('\n')
  assert.match(lines[0], /^# GeoWatch result ra{24}, model version v123/)
  assert.ok(lines.some((l) => l.startsWith('# licence: FABDEM')))
  const header = lines.find((l) => l.startsWith('result_id,'))
  assert.ok(header.includes('validation_status') && header.includes('coverage_observed_fraction') && header.includes('data_sources'))
  const body = lines.slice(lines.indexOf(header) + 1)
  assert.equal(body.length, 4)
  assert.ok(body.every((l) => l.includes(`"'=HYPERLINK(""x"")"`)))
})
test('an unknown source is named, not silently licensed', () => {
  const notes = D.licenceNotes(['some/new/source', 'none: not computed', 'open_buildings_v3 footprints, item 19 layer x'])
  assert.match(notes[0], /licence not recorded/)
  assert.equal(notes.length, 2)
  assert.match(notes[1], /Open Buildings/)
})
test('file names say result and unit type', () => {
  assert.equal(D.downloadName(result, 'ward:datameet_mumbai', 'csv'), `geowatch_${result.result_id}_wards_datameet_mumbai.csv`)
})

console.log(`web download: ${n} passed`)
