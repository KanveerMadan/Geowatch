/* Geometry for the search and draw tools. Plain functions, tested under node. */

const R_KM = 6371.0088 // mean Earth radius
const rad = (d) => (d * Math.PI) / 180

// Fixed 2026-10-29: the readout turns amber from this share of the limit.
export const WARN_SHARE = 0.8
// A searched place smaller than this gets the default box instead of its own.
export const MIN_PLACE_KM2 = 0.25
export const DEFAULT_BOX_KM = 3

/** Area of a lon/lat box on the sphere, km². Exact for a spherical Earth;
 *  the server's geodesic check (api.compute_aoi_geodesics) is the authority. */
export function bboxAreaKm2([w, s, e, n]) {
  return R_KM * R_KM * Math.abs(rad(e - w)) * Math.abs(Math.sin(rad(n)) - Math.sin(rad(s)))
}

/** 'ok' | 'warn' | 'over' against the server's limit. */
export function areaState(km2, maxKm2) {
  if (!(maxKm2 > 0)) return 'ok'
  if (km2 > maxKm2) return 'over'
  if (km2 >= WARN_SHARE * maxKm2) return 'warn'
  return 'ok'
}

/** A km-by-km box centred on a point. */
export function boxAround(lat, lon, km = DEFAULT_BOX_KM) {
  const dLat = (km / 2 / R_KM) * (180 / Math.PI)
  const dLon = dLat / Math.max(Math.cos(rad(lat)), 1e-6)
  return [lon - dLon, lat - dLat, lon + dLon, lat + dLat].map((v) => Math.round(v * 1e6) / 1e6)
}

/** The box to analyse for a found place: its own extent when that is a
 *  sensible size, else the default box around its centre. */
export function boxForPlace({ lat, lon, bbox }, maxKm2) {
  if (bbox) {
    const a = bboxAreaKm2(bbox)
    if (a >= MIN_PLACE_KM2 && a <= maxKm2) return bbox
  }
  return boxAround(lat, lon)
}

/** Bounding box [w, s, e, n] of drawn points [[lon, lat], ...]. */
export function bboxOf(points) {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity
  for (const [x, y] of points) {
    w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y)
  }
  return [w, s, e, n]
}

export function bboxPolygon([w, s, e, n]) {
  return { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }
}

/**
 * Coordinates typed into search: "lat, lon" (the order maps apps use),
 * with optional N/S/E/W suffixes, which then also fix the order.
 * Returns {lat, lon} or null.
 */
export function parseCoordinates(text) {
  const t = String(text).trim().toUpperCase().replace(/°/g, ' ')
  const m = t.match(/^(-?\d+(?:\.\d+)?)\s*([NSEW])?\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*([NSEW])?$/)
  if (!m) return null
  let [a, ha, b, hb] = [parseFloat(m[1]), m[2], parseFloat(m[3]), m[4]]
  if ((ha && a < 0) || (hb && b < 0)) return null
  const signed = (v, h) => (h === 'S' || h === 'W' ? -v : v)
  let lat, lon
  if ((ha === 'E' || ha === 'W') && (!hb || hb === 'N' || hb === 'S')) {
    lon = signed(a, ha); lat = signed(b, hb)
  } else {
    if ((ha === 'N' || ha === 'S') && (hb === 'N' || hb === 'S')) return null
    lat = signed(a, ha); lon = signed(b, hb)
  }
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  return { lat, lon }
}

const KM1 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 })
const KM0 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })
const HA = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })
/** Areas under 1 km² read in hectares, so a 100 m cell is "1 ha", not "0.0 km²". */
export function fmtArea(km2) {
  return km2 < 1 ? `${HA.format(km2 * 100)}\u00a0ha` : fmtKm2(km2)
}

export function fmtKm2(km2) {
  return `${(km2 < 10 ? KM1 : KM0).format(km2)}\u00a0km²`
}
