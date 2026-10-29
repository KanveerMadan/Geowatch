/*
 * The job API (GET /api/jobs/{id}) in plain language. Stage keys come from
 * the server; an unknown one is shown under its own name, never dropped.
 */

export const STAGE_TEXT = {
  ee_init: 'Connecting to satellite archives',
  road_layer: 'Reading roads and buildings',
  s2_composite: 'Reading satellite imagery',
  observability: 'Checking for cloud and shadow',
  dem: 'Reading terrain',
  waterways: 'Reading rivers and drains',
  context: 'Reading rainfall, terrain and coast',
  hydro_rasters: 'Reading flood inputs',
  change: 'Comparing with five years earlier',
}

// Display order; the run's own order agrees.
const ORDER = Object.keys(STAGE_TEXT)

/** The context:* stages are shown as one row, taking the worst outcome. */
const RANK = { failed: 0, timeout: 1, running: 2, ok: 3 }

export function stageRows(job) {
  const stages = job?.stages ?? {}
  const merged = {}
  for (const [k, v] of Object.entries(stages)) {
    const key = k.startsWith('context:') ? 'context' : k
    const prev = merged[key]
    if (!prev || (RANK[v.status] ?? 2) < (RANK[prev.status] ?? 2)) merged[key] = v
  }
  const keys = [...ORDER, ...Object.keys(merged).filter((k) => !ORDER.includes(k))]
  const running = job && (job.status === 'running' || job.status === 'queued')
  return keys
    .filter((k) => merged[k] || running)
    .map((k) => ({
      key: k,
      text: STAGE_TEXT[k] ?? k.replace(/_/g, ' '),
      state: merged[k] ? stateOf(merged[k].status) : 'waiting',
    }))
}

function stateOf(status) {
  return { ok: 'done', running: 'running', failed: 'failed', timeout: 'timeout' }[status] ?? 'running'
}

// Which stage an output group waits on.
const GROUP_STAGE = {
  fractions: 's2_composite',
  observability: 'observability',
  estimate_quality: 'observability',
  susceptibility: 'hydro_rasters',
  change: 'change',
  osm_coverage: null, // only in the final result
  aggregation: null,
}

/** 'waiting' | 'ready' | 'failed' for one output group of a job. */
export function groupState(job, group) {
  if (!job) return 'waiting'
  if (job.result?.outputs?.[group] || job.partial?.[group]) return 'ready'
  if (job.status === 'failed' || job.status === 'complete') return 'failed'
  const st = GROUP_STAGE[group] && job.stages?.[GROUP_STAGE[group]]
  if (st && (st.status === 'failed' || st.status === 'timeout')) return 'failed'
  return 'waiting'
}

/** The outputs available so far: the final result's, else the partial groups. */
export function outputsOf(job) {
  return job?.result?.outputs ?? job?.partial ?? {}
}

/** Plain-language reason a job stopped, from its stages. Never the raw error. */
export function failureText(job) {
  const st = job?.stages ?? {}
  const bad = (k) => st[k] && (st[k].status === 'failed' || st[k].status === 'timeout')
  if (bad('ee_init')) return 'The satellite archive did not answer. Try again in a minute.'
  if (bad('road_layer')) {
    return st.road_layer.status === 'timeout'
      ? 'Reading the road and building map took too long for this area. Try again, or a smaller area.'
      : 'The road and building map service did not answer. Try again in a minute.'
  }
  if (bad('s2_composite')) return 'Satellite imagery for this area could not be read. Try again in a minute.'
  return 'The analysis stopped before it could report anything. Try again.'
}

/** Why an incomplete (unstored) result is incomplete, in plain words. */
export function gapText(job) {
  const gaps = job?.not_stored_because
  if (!gaps || !Object.keys(gaps).length) return null
  const names = [...new Set(Object.keys(gaps).map((k) => (k.startsWith('context:') ? 'context' : k)))]
    .map((k) => (STAGE_TEXT[k] ?? k).toLowerCase())
  const timedOut = Object.values(gaps).includes('timeout')
  return `${timedOut ? 'Some steps timed out' : 'Some steps did not finish'} (${names.join(', ')}). The results below are partial; retry to complete them.`
}
