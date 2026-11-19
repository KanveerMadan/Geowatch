/*
 * Downloads from a stored area result, with provenance: GeoJSON and CSV of
 * its public units. Every row or feature carries each output's value,
 * status, validation label, coverage and data sources, plus the result id,
 * the model version and the licence notes of the sources it used.
 *
 * Public means wards and the 100 m grid only (product decision 2026-11-20):
 * footprint and path units are per building and per street segment, and
 * building-level detail goes only to named partners (eviction risk). No
 * raster is ever offered.
 */

export const PUBLIC_UNIT_TYPES = (types) =>
  types.filter((t) => t === 'grid' || t.startsWith('ward:'))

export const PAGE_LIMIT = 1000 // api.py WARD_PAGE_MAX

// Licence notes by data source, as understood on 2026-11-20. Matched on the
// source string the result names; a source not listed here says so, and the
// reader is sent to the source's own terms.
export const LICENCES = [
  ['open-buildings', 'Google Open Buildings v3: CC BY 4.0 or ODbL 1.0, at the user’s choice.'],
  ['open_buildings', 'Google Open Buildings v3: CC BY 4.0 or ODbL 1.0, at the user’s choice.'],
  ['OpenStreetMap', 'OpenStreetMap: ODbL 1.0, © OpenStreetMap contributors.'],
  ['OSM', 'OpenStreetMap: ODbL 1.0, © OpenStreetMap contributors.'],
  ['COPERNICUS/S2', 'Sentinel-2: contains modified Copernicus Sentinel data, free and open use with attribution.'],
  ['COPERNICUS/DEM', 'Copernicus DEM GLO-30: © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA; free use with attribution.'],
  ['MERIT/Hydro', 'MERIT Hydro: CC BY-NC 4.0 or ODbL 1.0. The CC BY-NC option forbids commercial use.'],
  ['FABDEM', 'FABDEM: CC BY-NC-SA 4.0. Non-commercial use only; derived work shares alike.'],
  ['CHIRPS', 'CHIRPS (UCSB Climate Hazards Center): free to use; cite Funk et al. (2015) and check the Center’s terms.'],
  ['IMERG', 'GPM IMERG: NASA open data, free use with citation.'],
  ['shoreline', 'Global shoreline (sat-io open datasets): see the dataset’s own licence.'],
]

export const GEOWATCH_TERMS = 'GeoWatch outputs are derived from the sources listed. Their terms apply to this file; where a source is non-commercial (FABDEM, MERIT Hydro under CC BY-NC), so is any use of outputs built on it. GeoWatch has not yet chosen a licence for its own contribution. These notes are a summary as of November 2026; each source’s own terms govern.'

/** The licence notes for a set of source strings, deduplicated, in order. */
export function licenceNotes(sources) {
  const out = []
  for (const s of sources) {
    if (/^none:/i.test(s)) continue          // "none: not computed" names no source
    const hit = LICENCES.find(([k]) => s.toLowerCase().includes(k.toLowerCase()))
    const note = hit ? hit[1] : `${s}: licence not recorded here; see the source’s own terms.`
    if (!out.includes(note)) out.push(note)
  }
  return out
}

const isOutput = (o) => o && typeof o === 'object' && 'value' in o && 'validation_status' in o

/** [[path, output], ...] for every output under a unit's `outputs`. */
export function flattenOutputs(node, path = []) {
  if (isOutput(node)) return [[path.join('.'), node]]
  if (!node || typeof node !== 'object') return []
  return Object.entries(node).flatMap(([k, v]) => flattenOutputs(v, [...path, k]))
}

const scopeNote = (o) => {
  const sc = o.validated_scope
  if (!sc) return ''
  return typeof sc === 'string' ? sc : `validated for: ${(sc.regions ?? []).join('; ')}`
}

/** One record per (unit, output): the CSV's rows, and the source of truth
 *  for the GeoJSON's properties. Absent stays null with its status. */
export function unitRecords(result, units) {
  const rid = result.result_id
  const mv = result.model_version ?? {}
  const rows = []
  for (const u of units) {
    for (const [path, o] of flattenOutputs(u.outputs)) {
      rows.push({
        result_id: rid,
        unit_type: u.unit_type,
        unit_id: u.unit_id ?? u.unit_index,
        unit_name: u.unit_name ?? '',
        area_m2: u.area_m2,
        output: path,
        value: o.status === 'available' ? o.value : null,
        status: o.status,
        validation_status: o.validation_status,
        validated_scope: scopeNote(o),
        tier: o.tier ?? '',
        coverage_observed_fraction: o.coverage?.observed_fraction ?? null,
        coverage_basis: o.coverage?.basis ?? '',
        data_sources: (o.data_sources ?? []).join('; '),
        reason: o.reason ?? '',
        model_version: mv.version_id ?? o.model_version?.version_id ?? '',
        code_commit: mv.code_commit ?? o.model_version?.code_commit ?? '',
      })
    }
  }
  return rows
}

function provenance(result, units) {
  const sources = [...new Set(units.flatMap((u) => flattenOutputs(u.outputs)
    .flatMap(([, o]) => o.data_sources ?? [])))]
  return {
    result_id: result.result_id,
    model_version: result.model_version?.version_id,
    code_commit: result.model_version?.code_commit,
    created_utc: result.created_utc,
    bbox: result.request?.bbox,
    imagery_window: result.request?.window,
    data_sources: sources,
    licence_notes: [...licenceNotes(sources), GEOWATCH_TERMS],
    labels: 'validated / experimental / placeholder / failed. A null value is not measured, never zero: its status says why.',
  }
}

/** A FeatureCollection: per unit, each output as <path>, <path>_status,
 *  <path>_validation, <path>_coverage, <path>_sources; provenance at the
 *  top and repeated on each feature's result_id and model_version. */
export function toGeoJSON(result, units) {
  const prov = provenance(result, units)
  const features = units.map((u) => {
    const props = { result_id: prov.result_id, model_version: prov.model_version, unit_type: u.unit_type,
      unit_id: u.unit_id ?? u.unit_index, unit_name: u.unit_name ?? null, area_m2: u.area_m2 }
    for (const [path, o] of flattenOutputs(u.outputs)) {
      props[path] = o.status === 'available' ? o.value : null
      props[`${path}_status`] = o.status
      props[`${path}_validation`] = o.validation_status
      props[`${path}_coverage`] = o.coverage?.observed_fraction ?? null
      props[`${path}_sources`] = (o.data_sources ?? []).join('; ')
      if (o.tier) props[`${path}_tier`] = o.tier
    }
    return { type: 'Feature', geometry: u.geometry ?? null, properties: props }
  })
  return { type: 'FeatureCollection', geowatch: prov, features }
}

const CSV_COLUMNS = ['result_id', 'unit_type', 'unit_id', 'unit_name', 'area_m2', 'output', 'value', 'status',
  'validation_status', 'validated_scope', 'tier', 'coverage_observed_fraction', 'coverage_basis', 'data_sources',
  'reason', 'model_version', 'code_commit']

const cell = (v) => {
  if (v === null || v === undefined) return ''
  const s = String(v)
  // Quote when needed; neutralise spreadsheet formulas (CSV injection).
  const safe = /^[=+\-@\t\r]/.test(s) && !/^-?\d/.test(s) ? `'${s}` : s
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe
}

/** Long CSV, one row per unit and output, preceded by # provenance lines. */
export function toCSV(result, units) {
  const prov = provenance(result, units)
  const head = [
    `# GeoWatch result ${prov.result_id}, model version ${prov.model_version}, code ${prov.code_commit}`,
    `# created ${prov.created_utc}; bbox ${(prov.bbox ?? []).join(',')}; imagery ${prov.imagery_window?.start}..${prov.imagery_window?.end}`,
    `# ${prov.labels}`,
    ...prov.licence_notes.map((l) => `# licence: ${l}`),
  ]
  const rows = unitRecords(result, units).map((r) => CSV_COLUMNS.map((c) => cell(r[c])).join(','))
  return [...head, CSV_COLUMNS.join(','), ...rows].join('\n') + '\n'
}

/** A file name that says what it is. */
export function downloadName(result, unitType, ext) {
  const t = unitType.replace(/^ward:/, 'wards_').replace(/[^a-z0-9_-]+/gi, '_')
  return `geowatch_${result.result_id}_${t}.${ext}`
}
