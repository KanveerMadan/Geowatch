/*
 * OSM coverage reading — build item 20, the UI half.
 *
 * Item 20's score reached every vector output but nothing rendered it, so the
 * system knew it was in a low-coverage regime and never said so. The backend
 * report (GET /api/vector/coverage, vector/coverage_report.py) carries one
 * coverage block per AOI.
 *
 * THIS MODULE READS, IT NEVER RE-DERIVES. Same rule as applicability.js:
 * there are no thresholds here and no list of regimes. Whether to warn is the
 * block's own `low_coverage_warning`; the reasons are the block's own
 * `regime_reasons`; a partial fetch is any status the block marks
 * `partial_fetch`. The only judgements made here are presentation:
 *
 *   - a block without `low_coverage_warning: false` warns. A missing field
 *     must never mean "no warning" (the C46 banner rule).
 *   - `not_measurable` (or `scored: false`) shows no number at all. The block
 *     may still carry densities computed from the clauses that were fetched,
 *     and printing one would read as a measurement.
 *
 * Kept as plain JS, separate from App.jsx, so node can test it.
 */

import { humanize, MISSING } from './render.js'

export const NOT_MEASURABLE = 'not measurable'

function finite(v) {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/** Every `{status: 'partial_fetch'}` in a block, wherever the backend put it. */
export function partialFetches(block, path = []) {
  if (!block || typeof block !== 'object') return []
  const here = block.status === 'partial_fetch'
    ? [{
        field: path.join('.') || '(block)',
        missingClauses: Array.isArray(block.missing_clauses) ? block.missing_clauses : [],
        note: block.note || null,
      }]
    : []
  return here.concat(
    Object.entries(block).flatMap(([k, v]) =>
      v && typeof v === 'object' && !Array.isArray(v) ? partialFetches(v, [...path, k]) : [])
  )
}

/** One display row per AOI, in the order the backend sent them. */
export function coverageRows(report) {
  const aois = Array.isArray(report?.aois) ? report.aois : []
  return aois.map(entry => {
    const block = entry?.coverage || {}
    const regime = typeof block.coverage_regime_flag === 'string' ? block.coverage_regime_flag : null
    const measurable = regime !== null && regime !== 'not_measurable' && block.scored !== false
    return {
      aoi: entry?.aoi ?? MISSING,
      morphology: entry?.morphology ?? null,
      regime,
      regimeLabel: regime ? humanize(regime) : 'No coverage regime reported',
      warning: block.low_coverage_warning !== false || regime === null,
      measurable,
      percentile: measurable ? finite(block.osm_density_percentile) : null,
      narrowDensity: measurable ? finite(block.narrow_pedestrian_km_per_km2) : null,
      reasons: Array.isArray(block.regime_reasons) ? block.regime_reasons : [],
      topologySuppressed: block.topology_metrics_suppressed === true,
      footprintConfidence: block.footprint_metrics_confidence ?? null,
      validationStatus: block.validation_status ?? null,
      partialFetch: partialFetches(block),
    }
  })
}

/** The percentile as text: the number, NOT_MEASURABLE, or MISSING. */
export function percentileText(row) {
  if (!row.measurable) return NOT_MEASURABLE
  return row.percentile === null ? MISSING : `${row.percentile}`
}

/** Pedestrian-path density as text, under the same rule. */
export function densityText(row) {
  if (!row.measurable) return NOT_MEASURABLE
  return row.narrowDensity === null ? MISSING : `${row.narrowDensity}`
}

/** The warning headline for a row that warns. */
export function warningHeadline(row) {
  return row.regime
    ? `OSM coverage ${row.regimeLabel.toLowerCase()}`
    : 'OSM coverage: no regime reported'
}
