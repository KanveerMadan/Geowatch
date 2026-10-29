/*
 * Reading the analysis result contract (analysis/contract.py). Every output
 * is {value, status, validation_status, coverage, data_sources, model_version}.
 *
 * Two rules this module exists to keep:
 *   1. Absent is never zero (item 36): a null value with an absent status is
 *      "not measured" plus its reason; only status "available" is a number.
 *   2. Every number carries its trust label, mapped here in one place.
 */

// Worst first: an output takes the worst label that applies (contract.py).
export const TRUST_ORDER = ['retired', 'failed', 'placeholder', 'experimental', 'validated']

export const TRUST = {
  validated: {
    label: 'Validated',
    explain: 'Tested against independent reference data, under criteria fixed in advance, and passed.',
  },
  experimental: {
    label: 'Experimental',
    explain: 'A real method that has not yet been tested against independent data. Use with care.',
  },
  placeholder: {
    label: 'Placeholder',
    explain: 'A stand-in until the proper method is built. Indicative only.',
  },
  failed: {
    label: 'Failed',
    explain: 'Tested against independent data and did not pass the bar set in advance. Shown for transparency, not for decisions.',
  },
  retired: {
    label: 'Retired',
    explain: 'From the retired land-cover pipeline. Not maintained and not validated.',
  },
}

const UNLABELLED = {
  key: 'unlabelled',
  label: 'Unlabelled',
  explain: 'This number carries no trust label, so treat it as unverified.',
}

/** The badge for an output (or a bare label). A validated output shows its
 *  scope note; an unknown label is never promoted to a known one. */
export function trustOf(outputOrLabel) {
  const o = outputOrLabel && typeof outputOrLabel === 'object' ? outputOrLabel : null
  const key = o ? o.validation_status : outputOrLabel
  const t = TRUST[key]
  if (!t) return { ...UNLABELLED, scope: null }
  const scope = key === 'validated' ? (o?.validation_scope ?? 'Scope of the validation not stated.') : null
  return { key, ...t, scope }
}

/** The worst label among outputs, for a section badge. */
export function worstTrust(outputs) {
  const keys = outputs.map((o) => o?.validation_status).filter((k) => TRUST[k])
  if (!keys.length) return null
  return keys.reduce((a, b) => (TRUST_ORDER.indexOf(a) <= TRUST_ORDER.indexOf(b) ? a : b))
}

const ABSENT_TEXT = {
  not_computed: 'Not yet measured',
  insufficient_observation: 'Not enough clear imagery',
  insufficient_evidence: 'Not enough evidence',
  timeout: 'Timed out',
  failed: 'Could not be measured',
  unavailable: 'Unavailable',
  not_applicable: 'Does not apply here',
}

/** {measured, value, status, text, reason}. `text` is what the main UI says
 *  when absent; `reason` is the contract's reason, for the details view. */
export function readOutput(o) {
  if (!o || typeof o !== 'object') {
    return { measured: false, value: null, status: 'missing', text: 'Not measured', reason: 'No output for this.' }
  }
  const measured = o.status === 'available' && typeof o.value === 'number' && Number.isFinite(o.value)
  if (measured) return { measured: true, value: o.value, status: o.status, text: null, reason: null }
  return {
    measured: false,
    value: null,
    status: o.status ?? 'missing',
    text: ABSENT_TEXT[o.status] ?? 'Not measured',
    reason: o.reason ?? null,
  }
}

// Locale-aware; one decimal for figures, whole numbers in sentences.
const PCT1 = new Intl.NumberFormat(undefined, { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 })
const PCT0 = new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 0 })
// A measured share too small for the precision shown says so: never a zero.
export const fmtPct1 = (v) => (v > 0 && v < 0.0005 ? `<${PCT1.format(0.001)}` : PCT1.format(v))
export const fmtPct0 = (v) => (v > 0 && v < 0.005 ? `<${PCT0.format(0.01)}` : PCT0.format(v))

/** A fraction in [0, 1] as a percentage: 0 is "0.0%", absent is never a number. */
export function fmtFraction(o) {
  const r = readOutput(o)
  if (!r.measured) return { ...r, display: r.text }
  return { ...r, display: fmtPct1(r.value) }
}

// Display names only; which fractions exist is read from the result (item 58).
const NAMES = {
  built: 'Built',
  vegetation: 'Vegetation',
  water: 'Water',
  impervious_total: 'Impervious',
  paved: 'Paved',
  bare: 'Bare ground',
}

export function humanize(key) {
  if (NAMES[key]) return NAMES[key]
  const s = String(key).replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** The Ground tab's rows, in the result's order: measured first, then absent. */
export function fractionRows(fractions) {
  const rows = Object.entries(fractions ?? {}).map(([key, o]) => ({
    key,
    name: humanize(key),
    ...fmtFraction(o),
    trust: trustOf(o),
    sources: o?.data_sources ?? [],
    coverage: o?.coverage?.observed_fraction ?? null,
    method: o?.method ?? null,
  }))
  return [...rows.filter((r) => r.measured), ...rows.filter((r) => !r.measured)]
}

// A measured share under 1% must not round to a zero.
const pct = (v) => (v > 0 && v < 0.01 ? 'under 1%' : fmtPct0(v))

/** One plain sentence about what covers the area, from measured fractions. */
export function groundSummary(fractions) {
  const rows = fractionRows(fractions)
  const m = rows.filter((r) => r.measured)
  const absent = rows.filter((r) => !r.measured).map((r) => r.name.toLowerCase())
  if (!m.length) return 'Nothing could be measured for this area yet.'
  const phrase = (r) => `${r.name.toLowerCase()} ${pct(r.value)}`
  const list = m.length === 1 ? phrase(m[0]) : `${m.slice(0, -1).map(phrase).join(', ')} and ${phrase(m.at(-1))}`
  let s = `Ground cover here: ${list}.`
  if (absent.length) {
    const names = absent.length === 1 ? absent[0] : `${absent.slice(0, -1).join(', ')} and ${absent.at(-1)}`
    s += ` ${names.charAt(0).toUpperCase()}${names.slice(1)} ${absent.length === 1 ? 'is' : 'are'} not yet measured.`
  }
  return s
}

/** Stacked-bar segments for a cell's measured fractions. The stand-in
 *  fractions come from different sources and can overlap (footprints vs
 *  imagery), so when they sum past 1 the bar is scaled to the sum and says so. */
export function stackSegments(props, keys) {
  const vals = keys
    .map((k) => ({ key: k, value: typeof props?.[k] === 'number' ? props[k] : null }))
  const measured = vals.filter((v) => v.value !== null && v.value > 0)
  const sum = measured.reduce((a, v) => a + v.value, 0)
  const scale = Math.max(1, sum)
  let start = 0
  const segments = measured.map((v) => {
    const seg = { key: v.key, value: v.value, start: start / scale, width: v.value / scale }
    start += v.value
    return seg
  })
  return {
    segments,
    overlap: sum > 1 + 1e-9,
    rest: Math.max(0, 1 - sum),
    absent: vals.filter((v) => v.value === null).map((v) => v.key),
  }
}
