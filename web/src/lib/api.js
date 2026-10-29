/*
 * The GeoWatch API. VITE_* values are inlined into the bundle, so the key is
 * a development shared secret for a localhost tool, not client
 * authentication (the same caveat as C40 and the old UI's api.js).
 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'
const KEY = import.meta.env.VITE_GEOWATCH_API_KEY

// Fixed 2026-10-29: how often a running job is asked for news.
export const JOB_POLL_MS = 1500
const REQUEST_TIMEOUT_MS = 30000

export class ApiError extends Error {
  constructor(status, detail) {
    super(`HTTP ${status}`)
    this.status = status
    this.detail = detail // kept for the details view; the UI never prints it raw
  }
}

async function call(path, { method = 'GET', body, signal } = {}) {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  const r = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { ...(KEY ? { 'X-API-Key': KEY } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  })
  if (!r.ok) {
    let detail = null
    try { detail = (await r.json()).detail } catch { /* not JSON */ }
    throw new ApiError(r.status, detail)
  }
  return r.json()
}

export const getLimits = () => call('/')

export const startJob = ([west, south, east, north], label) =>
  call('/api/jobs', { method: 'POST', body: { west, south, east, north, aoi_label: label } })

export const getJob = (id, signal) => call(`/api/jobs/${id}`, { signal })

export const getFeatures = (resultId, unitType, signal) =>
  call(`/api/results/${resultId}/features/${unitType}`, { signal })

export const getBuildings = (resultId) => call(`/api/results/${resultId}/buildings`)

export const getWard = (resultId, unitType, unitId) =>
  call(`/api/results/${resultId}/wards/${unitType}/${encodeURIComponent(unitId)}`)

/** A label the API's whitelist accepts, from a place name. */
export function aoiLabel(name) {
  const s = String(name ?? 'area').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '').slice(0, 40)
  return s || 'area'
}
