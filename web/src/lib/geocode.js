/*
 * Place search through Nominatim (OpenStreetMap), within its usage policy
 * (operations.osmfoundation.org/policies/nominatim):
 *   - searches run on submit only: the policy forbids autocomplete;
 *   - at most one request per second, enforced here;
 *   - repeated queries are answered from a cache;
 *   - results are attributed to OpenStreetMap where they are shown.
 * Browsers send the page as Referer, which identifies the application.
 */
const ENDPOINT = 'https://nominatim.openstreetmap.org/search'
const MIN_INTERVAL_MS = 1000
const RESULT_LIMIT = 6
const TIMEOUT_MS = 10000

const cache = new Map()
let last = 0

export async function searchPlaces(query) {
  const q = query.trim()
  if (!q) return []
  if (cache.has(q)) return cache.get(q)
  const wait = last + MIN_INTERVAL_MS - Date.now()
  if (wait > 0) await new Promise((r) => setTimeout(r, wait))
  last = Date.now()
  const url = `${ENDPOINT}?${new URLSearchParams({ q, format: 'jsonv2', limit: String(RESULT_LIMIT), addressdetails: '0' })}`
  const r = await fetch(url, { headers: { 'Accept-Language': navigator.language || 'en' }, signal: AbortSignal.timeout(TIMEOUT_MS) })
  if (!r.ok) throw new Error(`geocoder ${r.status}`)
  const rows = (await r.json()).map((p) => {
    const [s, n, w, e] = (p.boundingbox ?? []).map(Number)
    const parts = String(p.display_name ?? '').split(',').map((x) => x.trim())
    return {
      id: `${p.osm_type}${p.osm_id}`,
      name: p.name || parts[0],
      region: parts.slice(1).filter(Boolean).slice(-3).join(', '),
      lat: Number(p.lat),
      lon: Number(p.lon),
      bbox: [w, s, e, n].every(Number.isFinite) ? [w, s, e, n] : null,
    }
  })
  cache.set(q, rows)
  return rows
}
