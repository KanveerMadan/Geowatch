/* Geometry for the search and draw tools. Plain functions, tested under node. */

// WGS84, as the server measures (pyproj Geod in api.compute_aoi_geodesics).
const A_KM = 6378.137
const E2 = 0.00669437999014
const E = Math.sqrt(E2)
const rad = (d) => (d * Math.PI) / 180
const deg = (r) => (r * 180) / Math.PI

// Fixed 2026-10-29: the readout turns amber from this share of the limit.
export const WARN_SHARE = 0.8
// A searched place smaller than this gets the default box instead of its own.
export const MIN_PLACE_KM2 = 0.25
export const DEFAULT_BOX_KM = 3
// "Point + fixed box": the box side when you click a point.
export const DEFAULT_POINT_BOX_KM = 10
export const MIN_POINT_BOX_KM = 1
// Vertices per box edge when drawn, so edges follow parallels and meridians
// on the globe and on a tilted map, as the analysed box does.
export const EDGE_STEPS = 24

const q = (phi) => {
  const s = Math.sin(phi)
  return s / (1 - E2 * s * s) - (1 / (2 * E)) * Math.log((1 - E * s) / (1 + E * s))
}

/** Area of a lon/lat box on the WGS84 ellipsoid, km² (exact for a box
 *  bounded by parallels and meridians; the server's geodesic-edged polygon
 *  agrees to well under 0.1% at analysis sizes). */
export function bboxAreaKm2([w, s, e, n]) {
  return Math.abs((A_KM * A_KM * (1 - E2) / 2) * rad(e - w) * (q(rad(n)) - q(rad(s))))
}

const radii = (lat) => {
  const s2 = Math.sin(rad(lat)) ** 2
  return { M: (A_KM * (1 - E2)) / (1 - E2 * s2) ** 1.5, N: A_KM / Math.sqrt(1 - E2 * s2) }
}

// Coordinates are rounded to 1e-6° INWARD, so a box is never larger than asked.
const down = (v) => Math.floor(v * 1e6) / 1e6
const up = (v) => Math.ceil(v * 1e6) / 1e6

/** 'ok' | 'warn' | 'over' against the server's limit. */
export function areaState(km2, maxKm2) {
  if (!(maxKm2 > 0)) return 'ok'
  if (km2 > maxKm2) return 'over'
  if (km2 >= WARN_SHARE * maxKm2) return 'warn'
  return 'ok'
}

/** A km-by-km box centred on a point, sized on the ellipsoid at its latitude. */
export function boxAround(lat, lon, km = DEFAULT_BOX_KM) {
  const { M, N } = radii(lat)
  const dLat = deg(km / 2 / M)
  const dLon = deg(km / 2 / (N * Math.max(Math.cos(rad(lat)), 1e-6)))
  return [up(lon - dLon), up(lat - dLat), down(lon + dLon), down(lat + dLat)]
}

/** The largest point-box side the limit allows, in 0.5 km steps. */
export function maxBoxKm(maxKm2) {
  return Math.max(MIN_POINT_BOX_KM, Math.floor(Math.sqrt(maxKm2) * 2) / 2)
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

/** The box's outline, densified so every vertex lies on one of its four
 *  edges: drawn exactly where the analysed box is, in any projection. */
export function boxRing([w, s, e, n], steps = EDGE_STEPS) {
  const ring = []
  const lerp = (a, b, t) => a + (b - a) * t
  for (let i = 0; i < steps; i++) ring.push([lerp(w, e, i / steps), s])
  for (let i = 0; i < steps; i++) ring.push([e, lerp(s, n, i / steps)])
  for (let i = 0; i < steps; i++) ring.push([lerp(e, w, i / steps), n])
  for (let i = 0; i < steps; i++) ring.push([w, lerp(n, s, i / steps)])
  ring.push([w, s])
  return ring
}

export function bboxPolygon(bbox) {
  return { type: 'Polygon', coordinates: [boxRing(bbox)] }
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
