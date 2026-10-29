/*
 * Notes about the area being viewed, in plain language: road-map coverage,
 * how much of it the imagery saw, where the buildings come from. Each note
 * has a main sentence and, one click deeper, the figures behind it. Built
 * only from this result, never from other places.
 */
import { fmtPct0, readOutput } from './contract.js'

// Fixed 2026-10-29: below this observed share the imagery note warns.
export const LOW_OBSERVED_SHARE = 0.6

const pct = fmtPct0
const num2 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })

export function areaNotes(result) {
  const o = result?.outputs ?? {}
  const notes = []

  const cov = o.osm_coverage
  if (cov) {
    const regime = cov.coverage_regime_flag
    let text, tone
    if (regime === 'adequate') {
      text = 'Road map looks complete here.'
      tone = 'ok'
    } else if (regime === 'not_measurable') {
      text = 'Road map coverage could not be judged here: road-access results hidden.'
      tone = 'warn'
    } else {
      text = cov.topology_metrics_suppressed
        ? 'Road map incomplete here: road-access results hidden.'
        : 'Road map looks incomplete here: road-based results are less reliable.'
      tone = 'warn'
    }
    const r = readOutput(cov)
    notes.push({
      id: 'roads', tone, text, trust: cov,
      details: [
        r.measured && ['Narrow-path density, percentile among reference places', `${Math.round(r.value)}`],
        typeof cov.narrow_pedestrian_km_per_km2 === 'number'
          && ['Narrow paths per square kilometre', `${num2.format(cov.narrow_pedestrian_km_per_km2)} km`],
        cov.reference_set_size && ['Reference places compared against', String(cov.reference_set_size)],
        ...(cov.regime_reasons ?? []).map((x) => ['Why', x]),
      ].filter(Boolean),
    })
  }

  const of = o.observability?.observed_fraction
  if (of) {
    const r = readOutput(of)
    const cloud = readOutput(o.observability?.cloud_nodata)
    const text = !r.measured
      ? 'How much of this area the imagery saw could not be measured.'
      : r.value < LOW_OBSERVED_SHARE
        ? `Clouds or shadow hid much of this area: imagery saw ${pct(r.value)} of it clearly, so vegetation and water are less reliable.`
        : `Imagery saw ${pct(r.value)} of this area clearly enough to measure.`
    notes.push({
      id: 'imagery', tone: r.measured && r.value >= LOW_OBSERVED_SHARE ? 'ok' : 'warn', text, trust: of,
      details: [
        r.measured && ['Share of the area seen clearly', pct(r.value)],
        cloud.measured && ['Observations lost to cloud or no data', pct(cloud.value)],
        result.imagery?.source_image_count != null && ['Satellite scenes used', String(result.imagery.source_image_count)],
        result.request?.window && ['Imagery window', `${result.request.window.start} to ${result.request.window.end}`],
      ].filter(Boolean),
    })
  }

  const fp = result?.footprint_source
  if (fp) {
    const text = {
      open_buildings_v3: 'Buildings come from Google Open Buildings footprints.',
      osm_building: 'Buildings come from OpenStreetMap, which may miss some here.',
      none: 'No building footprints exist for this area, so built cover is not measured.',
    }[fp] ?? 'Building footprints come from an unnamed source.'
    notes.push({ id: 'buildings', tone: fp === 'open_buildings_v3' ? 'ok' : 'warn', text, details: [] })
  }
  return notes
}

/** Every data source the given outputs name, once. */
export function sourcesOf(outputs) {
  const all = Object.values(outputs ?? {}).flatMap((x) => x?.data_sources ?? [])
  return [...new Set(all.filter((s) => !s.startsWith('none')))]
}
