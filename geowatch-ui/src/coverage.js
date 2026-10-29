/*
 * OSM coverage reading — build item 20, the UI half.
 *
 * Item 20's score reached every vector output but nothing rendered it, so the
 * system knew it was in a low-coverage regime and never said so. Each
 * analysis result carries the coverage block for ITS OWN AOI
 * (result.outputs.osm_coverage, analysis/run.py). The panel shows that one
 * block, for the AOI being viewed. The reference AOIs it was ranked against
 * are calibration, never displayed.
 *
 * THIS MODULE READS, IT NEVER RE-DERIVES. Same rule as applicability.js:
 * there are no thresholds here and no list of regimes. Whether to warn is the
 * block's own `low_coverage_warning`; what is hidden is its own
 * `topology_metrics_suppressed`; a partial fetch is any status the block
 * marks `partial_fetch`. The only judgements made here are presentation:
 *
 *   - a block without `low_coverage_warning: false` warns. A missing field
 *     must never mean "no warning" (the C46 banner rule).
 *   - `not_measurable` (or `scored: false`) shows no number at all. The block
 *     may still carry densities computed from the clauses that were fetched,
 *     and printing one would read as a measurement.
 *   - the headline is plain language. Percentiles and densities are details,
 *     never the main text.
 *
 * Kept as plain JS, separate from App.jsx, so node can test it.
 */

import { humanize, MISSING } from './render.js'

export const NOT_MEASURABLE = 'not measurable'

function finite(v) {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/** The coverage block of an /api/analyze response or a bare result, or null. */
export function coverageBlockOf(res) {
  return res?.result?.outputs?.osm_coverage ?? res?.outputs?.osm_coverage ?? null
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

/** The view of one AOI's coverage block, or null when there is no block. */
export function coverageView(block) {
  if (!block || typeof block !== 'object') return null
  const regime = typeof block.coverage_regime_flag === 'string' ? block.coverage_regime_flag : null
  const measurable = regime !== null && regime !== 'not_measurable' && block.scored !== false
  const warning = block.low_coverage_warning !== false || regime === null
  const hidden = block.topology_metrics_suppressed === true
  const partialFetch = partialFetches(block)
  const missing = [...new Set(partialFetch.flatMap(p => p.missingClauses))]
  const conf = block.footprint_metrics_confidence ?? null

  const state = !measurable ? 'Road map could not be checked' : warning ? 'Road map incomplete' : 'Road map adequate'
  const effect = hidden ? 'street-network results hidden' : warning ? 'results may be affected' : 'nothing hidden'
  const notes = []
  if (missing.length) notes.push(`Some road types could not be downloaded: ${missing.map(c => humanize(c).toLowerCase()).join(', ')}.`)
  if (conf && conf !== 'normal') notes.push('Building figures are less certain here.')

  return {
    headline: `${state}: ${effect}`,
    notes,
    warning,
    measurable,
    regimeLabel: regime ? humanize(regime) : 'No coverage regime reported',
    percentile: measurable ? finite(block.value ?? block.osm_density_percentile) : null,
    narrowDensity: measurable ? finite(block.narrow_pedestrian_km_per_km2) : null,
    reasons: Array.isArray(block.regime_reasons) ? block.regime_reasons : [],
    validationStatus: block.validation_status ?? null,
    partialFetch,
  }
}

/** The percentile as text: the number, NOT_MEASURABLE, or MISSING. */
export function percentileText(view) {
  if (!view.measurable) return NOT_MEASURABLE
  return view.percentile === null ? MISSING : `${view.percentile}`
}

/** Pedestrian-path density as text, under the same rule. */
export function densityText(view) {
  if (!view.measurable) return NOT_MEASURABLE
  return view.narrowDensity === null ? MISSING : `${view.narrowDensity}`
}
