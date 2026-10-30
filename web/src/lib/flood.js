/*
 * The Flood tab, read from the result contract's `susceptibility` group:
 * one row and one map layer per flood type, in the contract's order. Which
 * types exist is read from the result (item 58); the names and the one-line
 * meanings below are display text only.
 *
 * A failed label is shown, never hidden: the row, the map and the ranking
 * all carry it, and the summary says so in words.
 */
import { readOutput, trustOf } from './contract.js'

export const TIERS = ['very_low', 'low', 'moderate', 'high', 'very_high']
export const TIER_TEXT = { very_low: 'Very low', low: 'Low', moderate: 'Moderate', high: 'High', very_high: 'Very high' }
// The contract's breaks (configs/*_constants.py, one set for all five types).
export const TIER_BREAKS = [0.2, 0.4, 0.6, 0.8]

const TYPES = {
  pluvial: { name: 'Surface water', long: 'surface-water flooding', term: 'pluvial', blurb: 'Heavy rain collecting where it falls, because it cannot drain or soak in.' },
  fluvial: { name: 'River', long: 'river flooding', term: 'fluvial', blurb: 'Rivers and streams overflowing onto the low ground beside them.' },
  coastal: { name: 'Coastal', long: 'coastal flooding', term: 'coastal', blurb: 'Sea water reaching low land near the shore.' },
  flash_flood: { name: 'Flash flood', long: 'flash flooding', term: 'flash flood', blurb: 'Fast runoff from steep ground after intense rain.' },
  waterlogging: { name: 'Waterlogging', long: 'waterlogging', term: 'waterlogging', blurb: 'Flat, low ground where water stands for days after rain.' },
}

export function floodName(key) {
  return TYPES[key]?.name ?? String(key).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

export function tierOf(score) {
  if (typeof score !== 'number' || !Number.isFinite(score)) return null
  const i = TIER_BREAKS.findIndex((b) => score < b)
  return TIERS[i === -1 ? TIERS.length - 1 : i]
}

/** One row per flood type in the result, in the result's order. */
export function floodRows(susceptibility) {
  return Object.entries(susceptibility ?? {}).map(([key, o]) => {
    const r = readOutput(o)
    const t = TYPES[key]
    const tier = r.measured ? (o.tier ?? tierOf(r.value)) : null
    return {
      key,
      name: floodName(key),
      long: t?.long ?? key.replace(/_/g, ' '),
      term: t?.term ?? key.replace(/_/g, ' '),
      blurb: t?.blurb ?? null,
      ...r,
      tier,
      tierText: tier ? TIER_TEXT[tier] : r.text,
      trust: trustOf(o),
      // A map exists only where the type was computed per pixel; an AOI-wide
      // scalar is never painted as if it varied across the area.
      mapped: !!o?.per_unit || (key === 'pluvial' && !!o?.map),
      spatial: !!o?.spatial,
      verdict: o?.tier2_verdict ?? null,
      limitations: o?.limitations ?? [],
      sources: (o?.data_sources ?? []).filter((s) => !s.startsWith('none')),
      reason: r.reason,
    }
  })
}

const list = (xs) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`)
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)

/** One plain paragraph: the highest trusted reading first, then what is
 *  only shown for transparency, then what was not measured. */
export function floodSummary(susceptibility) {
  const rows = floodRows(susceptibility)
  const usable = rows.filter((r) => r.measured && r.trust.key !== 'failed' && r.trust.key !== 'retired')
  const failed = rows.filter((r) => r.measured && r.trust.key === 'failed')
  const absent = rows.filter((r) => !r.measured)
  const parts = []
  if (usable.length) {
    const byTier = [...usable].sort((a, b) => TIERS.indexOf(b.tier) - TIERS.indexOf(a.tier))
    const top = byTier.filter((r) => r.tier === byTier[0].tier)
    const rest = byTier.filter((r) => r.tier !== byTier[0].tier)
    parts.push(`${cap(list(top.map((r) => r.long)))} ${top.length > 1 ? 'are' : 'is'} the highest here, at ${TIER_TEXT[top[0].tier].toLowerCase()}.`)
    if (rest.length) {
      const groups = TIERS.slice().reverse().map((t) => rest.filter((r) => r.tier === t)).filter((g) => g.length)
      parts.push(cap(`${groups.map((g) => `${list(g.map((r) => r.long))} ${TIER_TEXT[g[0].tier].toLowerCase()}`).join('; ')}.`))
    }
  } else if (!failed.length) {
    parts.push('No flood type could be measured for this area yet.')
  }
  if (failed.length) {
    parts.push(`${cap(list(failed.map((r) => r.long)))} ${failed.length > 1 ? 'are' : 'is'} shown but failed validation, so ${failed.length > 1 ? 'they are' : 'it is'} not for decisions.`)
  }
  const na = absent.filter((r) => r.status === 'not_applicable')
  const other = absent.filter((r) => r.status !== 'not_applicable')
  if (na.length) parts.push(`${cap(list(na.map((r) => r.long)))} does not apply here.`)
  if (other.length) parts.push(`${cap(list(other.map((r) => r.long)))}: ${other.map((r) => r.text.toLowerCase()).join(', ')}.`)
  return parts.join(' ')
}

/** The first flood type worth showing on the map: a mapped, trusted one if
 *  any, else any mapped one. */
export function defaultFloodLayer(susceptibility) {
  const rows = floodRows(susceptibility).filter((r) => r.mapped)
  return (rows.find((r) => r.measured && r.trust.key !== 'failed') ?? rows[0])?.key ?? null
}

/** The ward unit type of a result ('ward:<boundary id>'), or null. */
export function wardUnitType(result) {
  return Object.keys(result?.wards ?? {}).find((t) => t.startsWith('ward:')) ?? null
}

/** Wards ranked by one flood type's mean score, highest first; wards with no
 *  measurement follow, unranked. From a features FeatureCollection. */
export function rankWards(fc, key) {
  const prop = `flood_${key}`
  const rows = (fc?.features ?? []).map((f) => {
    const p = f.properties ?? {}
    const v = p[prop]
    const measured = typeof v === 'number' && Number.isFinite(v)
    return {
      id: p.unit_id, name: p.unit_name || `Ward ${p.unit_id}`, areaKm2: (p.area_m2 ?? 0) / 1e6,
      measured, value: measured ? v : null, tier: measured ? tierOf(v) : null,
      status: p[`${prop}_status`] ?? 'missing',
    }
  })
  const ranked = rows.filter((r) => r.measured).sort((a, b) => b.value - a.value)
    .map((r, i) => ({ ...r, rank: i + 1 }))
  return { ranked, unranked: rows.filter((r) => !r.measured) }
}
