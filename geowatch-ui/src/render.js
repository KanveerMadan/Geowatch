/*
 * Pure-renderer helpers — build item 58.
 *
 * The frontend renders result.json and computes nothing. Each helper here
 * replaces something App.jsx used to decide for itself:
 *
 *   humanize     replaces CAT_LABELS, a hardcoded category table. Every
 *                entry in it was the key in sentence case, so deriving it
 *                changes no label, and a new category is no longer blank.
 *   hazardKeys   replaces iterating SUSC_INFO, which silently dropped any
 *                hazard the backend emitted that the table did not list.
 *   isUnpaved    replaces UNPAVED_HIGHWAY_TYPES, a copy of osm_dem.py's
 *                set. roads.geojson now carries the backend's own flag.
 *   segmentGrid  replaces `?? 291 / ?? 257`, which was exactly Dharavi's
 *                tile_dimensions: a result missing the field would have
 *                been projected through Dharavi's grid, anywhere on Earth.
 *
 * Missing input always yields "missing" (null, [], false or MISSING), never a
 * substitute value. Kept as plain JS so node can test it without a browser.
 */

export const MISSING = '—'

export function humanize(key) {
  if (typeof key !== 'string' || key === '') return MISSING
  const s = key.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function hazardKeys(susceptibility) {
  return Object.keys(susceptibility || {})
}

export function isUnpaved(feature) {
  return feature?.properties?.unpaved === true
}

export function segmentGrid(result) {
  const w = result?.tile_dimensions?.width
  const h = result?.tile_dimensions?.height
  const ok = v => typeof v === 'number' && Number.isFinite(v) && v > 0
  return ok(w) && ok(h) ? { width: w, height: h } : null
}
