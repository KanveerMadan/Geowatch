/*
 * Gallery cards, from web/src/generated/gallery.json (python -m
 * product.site_data reads product/gallery_cities.json and each city's stored
 * run record). A card shows the values and labels stored with the result.
 */
import { fmtPct0, humanize } from './contract.js'
import { TIER_TEXT, floodName } from './flood.js'
import { reportHref } from './link.js'
import { exploreHref } from './route.js'

const ABSENT = {
  not_computed: 'Not yet measured', not_applicable: 'Does not apply here', timeout: 'Timed out',
  insufficient_observation: 'Not enough clear imagery', insufficient_evidence: 'Not enough evidence',
  failed: 'Could not be measured', unavailable: 'Unavailable',
}

/** A headline value as {display, measured}: absent is words, never 0. */
export function headlineValue(v, kind) {
  const measured = v.status === 'available' && typeof v.value === 'number' && Number.isFinite(v.value)
  if (!measured) return { measured: false, display: ABSENT[v.status] ?? 'Not measured' }
  if (kind === 'flood') return { measured: true, display: TIER_TEXT[v.tier] ?? '—', tier: v.tier }
  return { measured: true, display: fmtPct0(v.value) }
}

export function cardModel(c) {
  return {
    ...c,
    reportHref: `${reportHref(c.result_id, c.name)}`,
    exploreHref: exploreHref(c.bbox),
    ground: c.fractions.map((f) => ({ ...f, name: humanize(f.key), ...headlineValue(f, 'fraction') })),
    floods: c.flood.map((f) => ({ ...f, name: floodName(f.key), ...headlineValue(f, 'flood') })),
    observed: typeof c.observed_fraction === 'number' ? fmtPct0(c.observed_fraction) : 'Not measured',
    date: c.run_utc.slice(0, 10),
  }
}
