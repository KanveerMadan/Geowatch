import { humanize } from './contract.js'

export const dynamicWorldCredit = 'This dataset is produced for the Dynamic World Project by Google in partnership with National Geographic Society and the World Resources Institute. Contains modified Copernicus Sentinel data.'

export const historyStates = {
  change_detected: 'Change detected',
  candidate_change: 'Candidate change',
  no_change_detected: 'No change detected',
  insufficient_observation: 'Insufficient observations',
}

export const signalNames = {
  dw_water: 'Water class score', dw_trees: 'Tree class score', dw_grass: 'Grass class score',
  dw_flooded_vegetation: 'Flooded vegetation class score', dw_crops: 'Crop class score',
  dw_shrub_and_scrub: 'Shrub and scrub class score', dw_built: 'Built class score',
  dw_bare: 'Bare ground class score', dw_snow_and_ice: 'Snow and ice class score',
  ndvi: 'Greenness (NDVI)', mndwi: 'Open-water signal (MNDWI)',
  ndbi: 'Built-surface signal (NDBI)', vv_db: 'Radar VV (dB)',
  vh_db: 'Radar VH (dB)', building_presence: 'Building presence score',
}

export const signalName = (signal) => signalNames[signal] ?? humanize(signal)
export const stateName = (state) => historyStates[state] ?? (state ? humanize(state) : 'Unknown')
export const num = (n) => Number.isFinite(n)
  ? new Intl.NumberFormat(undefined, { maximumSignificantDigits: 4 }).format(n) : '—'
export const periodText = (period) => period?.length === 2
  ? `${period[0]} to before ${period[1]}` : 'Unavailable'

export function summaryOf(wrapper) {
  return wrapper?.value ?? wrapper?.summary ?? null
}

export function historyText(wrapper) {
  const summary = summaryOf(wrapper)
  if (!summary?.counts) return wrapper?.reason || 'Change history is unavailable for this area.'
  const total = Object.values(summary.counts).reduce((sum, count) => sum + count, 0)
  if (!total) return wrapper?.reason || 'No reporting cells were assessed in this area.'
  const judged = total - (summary.counts.insufficient_observation ?? 0)
  if (!judged) return `All ${total} reporting cells have insufficient observations.`
  const n = summary.event_count
  const events = Number.isFinite(n) ? `${n} signal ${n === 1 ? 'episode' : 'episodes'} recorded. ` : ''
  return `${events}${judged} of ${total} cells had enough observations to assess change.`
}

export function historyMark(props) {
  return ({
    change_detected: 'detected', candidate_change: 'candidate', no_change_detected: 'none',
    increase: 'increase', decrease: 'decrease', unchanged: 'none',
  })[props?.state] ?? 'unjudged'
}

export function compareError(query, summary) {
  const dates = [query.before_start, query.before_end, query.after_start, query.after_end]
  if (dates.some((s) => !/^\d{4}-\d{2}-\d{2}$/.test(s ?? ''))) return 'Select all four dates.'
  if (dates[0] >= dates[1] || dates[2] >= dates[3]) return 'Each period must end after it starts.'
  if (dates[1] > dates[2]) return 'The first period must end by the start of the second.'
  if (dates[0] < summary.training_period?.[0] || dates[3] > summary.period?.[1]) return 'Both periods must fall within the stored observation history.'
  if (!(summary.signals ?? []).includes(query.signal)) return 'Select a signal available in this history.'
  return ''
}

export function initialComparison(summary, window) {
  const [min, max] = [summary.training_period?.[0], summary.period?.[1]]
  const start = window?.start ?? summary.period?.[0] ?? ''
  const end = window?.end ?? max ?? ''
  // Shift by whole calendar years to retain the season, including leap years.
  const shift = (s, yrs) => {
    if (!s) return ''
    const d = new Date(s + 'T00:00:00Z'), month = d.getUTCMonth()
    d.setUTCFullYear(d.getUTCFullYear() - yrs)
    if (month !== d.getUTCMonth()) d.setUTCDate(0)
    return d.toISOString().slice(0, 10)
  }
  const yrs = min && start ? Math.max(1, Number(start.slice(0, 4)) - Number(min.slice(0, 4))) : 1
  return {
    before_start: shift(start, yrs) >= min ? shift(start, yrs) : (min ?? ''),
    before_end: shift(end, yrs), after_start: start, after_end: end,
    signal: summary.signals?.includes('ndvi') ? 'ndvi' : (summary.signals?.[0] ?? ''),
  }
}

export function previousDay(s) {
  const d = new Date(s + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() - 1)
  return d.toISOString().slice(0, 10)
}

export function replayError(q, summary) {
  if ([q.start, q.end, q.as_of].some((s) => !/^\d{4}-\d{2}-\d{2}$/.test(s ?? ''))) return 'Select the interval and evidence date.'
  if (q.start >= q.end) return 'The interval must end after it starts.'
  if (q.start < summary.training_period[0] || q.end > summary.period[1] || q.as_of >= summary.period[1])
    return 'Select dates within the stored history.'
  if (q.as_of < q.start) return 'The evidence cutoff must be on or after the start date.'
  if (q.mode === 'prospective' && q.as_of >= q.end) return 'Prospective evidence ends before the interval closes.'
  return ''
}
