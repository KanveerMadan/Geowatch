/*
 * The page URL carries the view: ?bbox=w,s,e,n opens an area, ?job=<id>
 * reattaches to a running analysis, ?tab= picks the tab. Built and read only
 * here, so what is shared is what is shown.
 */
export const TAB_IDS = ['ground', 'flood', 'change']

/** {bbox | null, jobId | null, tab} from a search string. Invalid parts are dropped. */
export function parseLink(search) {
  const q = new URLSearchParams(search)
  const b = (q.get('bbox') ?? '').split(',').map(Number)
  const bbox = b.length === 4 && b.every(Number.isFinite) && b[0] < b[2] && b[1] < b[3]
    && b[1] >= -90 && b[3] <= 90 && b[0] >= -180 && b[2] <= 180 ? b : null
  const job = q.get('job')
  return { bbox, jobId: job && /^j[0-9a-f]{24}$/.test(job) ? job : null, tab: TAB_IDS.includes(q.get('tab')) ? q.get('tab') : 'ground' }
}

/** The search string for the current view; '' when there is nothing to keep. */
export function linkQuery({ bbox, jobId, jobDone, tab }) {
  const q = new URLSearchParams()
  if (bbox) q.set('bbox', bbox.map((v) => v.toFixed(5)).join(','))
  if (bbox && jobId && !jobDone) q.set('job', jobId)
  if (tab && tab !== 'ground') q.set('tab', tab)
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** How a box opened from a link is named: never "Drawn area". */
export function linkPlace([w, s, e, n]) {
  const lat = (s + n) / 2, lon = (w + e) / 2
  const fmt = (v, pos, neg) => `${Math.abs(v).toFixed(3)}° ${v >= 0 ? pos : neg}`
  return { name: 'Selected area', region: `${fmt(lat, 'N', 'S')}, ${fmt(lon, 'E', 'W')}` }
}
