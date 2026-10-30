/*
 * The Change tab, read from the contract's `change` group (item 25) and the
 * per-cell verdicts (GET /api/results/{id}/change/features).
 *
 * Each fraction names its own change; there is no combined "something
 * changed". A cell is increase / decrease / no detectable change only where
 * both years were seen well enough; elsewhere it is unjudged, drawn as the
 * not-measured hatch, never as "no change".
 */
import { humanize, readOutput, trustOf } from './contract.js'

export const JUDGED = ['increase', 'decrease', 'no_detectable_change']
const UNJUDGED_TEXT = {
  insufficient_observation: 'Not seen clearly in both years',
  epoch_unreliable: 'One of the two years was too cloudy to compare',
}

/** [year a, year b] a change output compared. Built compares Open Buildings
 *  years; vegetation and water compare two imagery windows. */
export function comparedYears(o) {
  const e = o?.epochs
  if (!e) return null
  const y = (x) => (typeof x === 'number' ? x : Number(String(x?.window?.[1] ?? x?.window?.[0] ?? '').slice(0, 4)))
  const a = y(e.a), b = y(e.b)
  return Number.isFinite(a) && Number.isFinite(b) ? [a, b] : null
}

const share = (k, n) => (n ? k / n : 0)

/** One row per fraction in the change group, measured first. */
export function changeRows(change) {
  const rows = Object.entries(change ?? {}).map(([key, o]) => {
    // A change value is a dict of cell counts, not a number.
    const measured = o?.status === 'available' && !!o?.value && typeof o.value === 'object'
    if (!measured) {
      const r = readOutput(o)
      return { key, name: humanize(key), measured: false, text: r.text, reason: r.reason, trust: trustOf(o) }
    }
    const c = o.value
    const all = o.counts_all ?? c
    const judged = c.increase + c.decrease + c.no_detectable_change
    const cells = Object.values(all).reduce((a, b) => a + b, 0)
    return {
      key, name: humanize(key), measured: true, trust: trustOf(o),
      increase: c.increase, decrease: c.decrease, unchanged: c.no_detectable_change,
      judged, cells, unjudged: cells - judged,
      changed: c.increase + c.decrease, changedShare: share(c.increase + c.decrease, judged),
      years: comparedYears(o), threshold: o.threshold ?? null, noise: o.noise ?? null, k: o.k ?? null,
      method: o.method ?? null, sources: (o.data_sources ?? []).filter((s) => !s.startsWith('none')),
      coverage: o.coverage?.observed_fraction ?? null,
    }
  })
  return [...rows.filter((r) => r.measured), ...rows.filter((r) => !r.measured)]
}

const pctWord = (v) => (v > 0 && v < 0.01 ? 'under 1%' : `${Math.round(v * 100)}%`)
const yrs = (r) => (r.years ? `${r.years[0]} and ${r.years[1]}` : 'the two compared years')

/** One plain paragraph: where most change is, then the rest, then what is
 *  not measured. Counts are 100 m cells. */
export function changeSummary(change) {
  const rows = changeRows(change)
  const m = rows.filter((r) => r.measured)
  const absent = rows.filter((r) => !r.measured)
  if (!m.length) return 'Change could not be measured for this area yet.'
  const parts = []
  const top = [...m].sort((a, b) => b.changedShare - a.changedShare)[0]
  if (top.changed === 0) {
    parts.push(`No detectable change in ${list(m.map((r) => r.name.toLowerCase()))}.`)
  } else {
    parts.push(`Most change here is in ${top.name.toLowerCase()}: ${top.changed} of ${top.judged} cells (${pctWord(top.changedShare)}) changed between ${yrs(top)}, ${top.increase} up and ${top.decrease} down.`)
    for (const r of m.filter((x) => x !== top)) {
      parts.push(r.changed
        ? `${r.name}: ${r.increase} up, ${r.decrease} down (${yrs(r)}).`
        : `${r.name}: no detectable change (${yrs(r)}).`)
    }
  }
  if (absent.length) {
    const names = absent.map((r) => r.name.toLowerCase())
    parts.push(`${cap(list(names))} change ${names.length > 1 ? 'are' : 'is'} not yet measured.`)
  }
  return parts.join(' ')
}

const list = (xs) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`)
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)

/** 'increase' | 'decrease' | 'none' | 'unjudged' for one cell and fraction. */
export function cellChange(props, f) {
  const s = props?.[f]
  if (s === 'increase' || s === 'decrease') return s
  if (s === 'no_detectable_change') return 'none'
  return 'unjudged'
}

export function unjudgedText(status) {
  return UNJUDGED_TEXT[status] ?? 'Not judged'
}

/** A before / after pair kept in order inside `years`: moving one thumb past
 *  the other pushes it along, never swaps them. */
export function orderPair([before, after], which, year, years) {
  const lo = years[0], hi = years.at(-1)
  const y = Math.min(hi, Math.max(lo, year))
  if (which === 'before') return [Math.min(y, hi - 1), Math.max(after, Math.min(y, hi - 1) + 1)]
  return [Math.min(before, Math.max(y, lo + 1) - 1), Math.max(y, lo + 1)]
}
