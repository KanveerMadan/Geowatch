/*
 * The map's own layers, added once over the base style and driven from
 * React through these functions. Paint values come from the tokens.
 */
import { color, motion } from '../design/tokens.js'
import { bboxPolygon, boxRing } from '../lib/geo.js'
import { TIER_BREAKS } from '../lib/flood.js'

const EMPTY = { type: 'FeatureCollection', features: [] }
// A uniform extrusion height, metres: footprints carry no measured height.
export const FOOTPRINT_DISPLAY_HEIGHT_M = 6

function hatchImage() {
  const size = 16
  const c = document.createElement('canvas')
  c.width = c.height = size
  const g = c.getContext('2d')
  g.strokeStyle = color.data.notMeasured
  g.lineWidth = 2
  for (const o of [-size, 0, size]) {
    g.beginPath(); g.moveTo(o, size); g.lineTo(o + size, 0); g.stroke()
  }
  return g.getImageData(0, 0, size, size)
}

export function addLayers(map) {
  if (map.getSource('aoi')) return
  map.addImage('hatch', hatchImage(), { pixelRatio: 2 })
  for (const id of ['aoi', 'draft', 'scan', 'cells', 'footprints']) {
    map.addSource(id, { type: 'geojson', data: EMPTY, ...(id === 'cells' ? { promoteId: 'unit_id' } : {}) })
  }
  map.addLayer({
    id: 'footprints-3d', type: 'fill-extrusion', source: 'footprints', minzoom: 13,
    layout: { visibility: 'none' },
    paint: {
      'fill-extrusion-color': '#d4d7dd',
      'fill-extrusion-height': FOOTPRINT_DISPLAY_HEIGHT_M,
      'fill-extrusion-opacity': 1,
      'fill-extrusion-vertical-gradient': true,
    },
  })
  map.addLayer({ id: 'cells-fill', type: 'fill', source: 'cells', paint: { 'fill-opacity': 0, 'fill-color': color.data.built } })
  map.addLayer({ id: 'cells-hatch', type: 'fill', source: 'cells', paint: { 'fill-pattern': 'hatch', 'fill-opacity': 0 } })
  map.addLayer({ id: 'cells-glow', type: 'line', source: 'cells', paint: { 'line-opacity': 0, 'line-color': color.data.built } })
  map.addLayer({
    id: 'cells-hover', type: 'line', source: 'cells',
    paint: {
      'line-color': color.select,
      'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2,
        ['boolean', ['feature-state', 'hover'], false], 1.2, 0],
      'line-opacity': 0.95,
    },
  })
  // Outlines are LineStrings of their own: a polygon's outline is cut where
  // tiles clip it, which dropped whole edges on a tilted map.
  const isLine = ['==', ['geometry-type'], 'LineString']
  map.addLayer({ id: 'aoi-casing', type: 'line', source: 'aoi', filter: isLine, paint: { 'line-color': '#000', 'line-width': 4, 'line-opacity': 0.35 } })
  map.addLayer({ id: 'aoi-line', type: 'line', source: 'aoi', filter: isLine, paint: { 'line-color': color.select, 'line-width': 1.5, 'line-opacity': 0.95 } })
  map.addLayer({
    id: 'draft-fill', type: 'fill', source: 'draft', filter: ['==', ['geometry-type'], 'Polygon'],
    paint: { 'fill-color': ['get', 'tone'], 'fill-opacity': 0.08 },
  })
  map.addLayer({
    id: 'draft-line', type: 'line', source: 'draft', filter: isLine,
    paint: { 'line-color': ['get', 'tone'], 'line-width': 1.5, 'line-dasharray': [2, 1.5] },
  })
  map.addLayer({
    id: 'scan-trail', type: 'fill', source: 'scan', filter: ['==', ['geometry-type'], 'Polygon'],
    paint: { 'fill-color': color.select, 'fill-opacity': ['get', 'o'], 'fill-antialias': false },
  })
  map.addLayer({
    id: 'scan-line', type: 'line', source: 'scan', filter: ['==', ['geometry-type'], 'LineString'],
    paint: { 'line-color': color.select, 'line-width': 1.5, 'line-opacity': 0.9 },
  })
}

// The shown outline is built from the same [w, s, e, n] the analysis gets.
const outline = (ring, properties = {}) => ({
  type: 'FeatureCollection',
  features: [
    { type: 'Feature', properties, geometry: { type: 'Polygon', coordinates: [ring] } },
    { type: 'Feature', properties, geometry: { type: 'LineString', coordinates: ring } },
  ],
})

export function setAoi(map, bbox) {
  map.getSource('aoi')?.setData(bbox ? outline(boxRing(bbox)) : EMPTY)
}

/** A draft: a box ([w, s, e, n]) or a lasso ring ([[lon, lat], ...]). */
export function setDraft(map, shape, tone) {
  if (!shape) return map.getSource('draft')?.setData(EMPTY)
  const ring = typeof shape[0] === 'number' ? boxRing(shape) : [...shape, shape[0]]
  map.getSource('draft')?.setData(outline(ring, { tone }))
}

// ── the scan: a line sweeping west to east with a fading trail ──

const TRAIL_STRIPS = 14
const TRAIL_SHARE = 0.18

export function scanFrame(map, bbox, phase) {
  const [w, s, e, n] = bbox
  const x = w + (e - w) * phase
  const strip = ((e - w) * TRAIL_SHARE) / TRAIL_STRIPS
  const features = [{ type: 'Feature', geometry: { type: 'LineString', coordinates: [[x, s], [x, n]] }, properties: {} }]
  for (let i = 0; i < TRAIL_STRIPS; i++) {
    const x1 = x - i * strip
    const x0 = Math.max(w, x1 - strip)
    if (x1 <= w) break
    features.push({
      type: 'Feature',
      properties: { o: 0.1 * (1 - i / TRAIL_STRIPS) ** 1.6 },
      geometry: bboxPolygon([x0, s, x1, n]),
    })
  }
  map.getSource('scan')?.setData({ type: 'FeatureCollection', features })
}

export function clearScan(map) {
  map.getSource('scan')?.setData(EMPTY)
}

// ── cells: one fraction at a time ──

/** Each feature gets _t in [0, 1], its position along the sweep, so cells
 *  resolve in the order the scan passed them. */
export function setCells(map, fc, bbox) {
  const [w, , e] = bbox
  const features = (fc?.features ?? []).map((f) => {
    const ring = f.geometry?.coordinates?.[0] ?? []
    const cx = ring.length ? ring.reduce((a, p) => a + p[0], 0) / ring.length : w
    return { ...f, properties: { ...f.properties, _t: Math.min(1, Math.max(0, (cx - w) / (e - w || 1))) } }
  })
  map.getSource('cells')?.setData({ type: 'FeatureCollection', features })
}

const isNum = (f) => ['==', ['typeof', ['get', f]], 'number']

// The flood ramp as a step on the contract's breaks (lib/flood.js).
const floodColour = (prop) => ['step', ['get', prop],
  color.flood.very_low, TIER_BREAKS[0], color.flood.low, TIER_BREAKS[1], color.flood.moderate,
  TIER_BREAKS[2], color.flood.high, TIER_BREAKS[3], color.flood.very_high]
const FLOOD_OPACITY = 0.78

/** What the cell layers show: {kind: 'fraction' | 'flood', key}. */
export function cellProp(layer) {
  return layer.kind === 'flood' ? `flood_${layer.key}` : layer.key
}

/** Paint the cell layers for `layer` at reveal progress p in [0, 1] and
 *  visibility v in [0, 1] (the tab crossfade). A fraction is its own hue,
 *  deeper with more of it; a flood type is its tier's colour. Either way a
 *  cell with no measurement is the hatch, never the low end of the scale. */
export function paintCells(map, layer, p, v = 1) {
  if (!map.getLayer('cells-fill')) return
  const f = cellProp(layer)
  const flood = layer.kind === 'flood'
  const hue = flood ? floodColour(f) : (color.data[f] ?? color.select)
  const P = p * 1.3
  const r = ['min', 1, ['max', 0, ['/', ['-', P, ['get', '_t']], 0.3]]]
  map.setPaintProperty('cells-fill', 'fill-color', hue)
  map.setPaintProperty('cells-fill', 'fill-opacity',
    ['case', isNum(f), ['*', v, r, flood ? FLOOD_OPACITY : ['interpolate', ['linear'], ['get', f], 0, 0.05, 1, 0.9]], 0])
  map.setPaintProperty('cells-hatch', 'fill-opacity', ['case', isNum(f), 0, ['*', v, r, 0.9]])
  map.setPaintProperty('cells-glow', 'line-color', hue)
  map.setPaintProperty('cells-glow', 'line-width', ['*', ['-', 1, r], motion.reveal.blurPx * 1.5])
  map.setPaintProperty('cells-glow', 'line-blur', ['*', ['-', 1, r], motion.reveal.blurPx])
  map.setPaintProperty('cells-glow', 'line-opacity',
    ['case', ['all', isNum(f), ['>', r, 0]], ['*', v, ['-', 1, r], 0.7], 0])
}

export function setFootprints(map, fc) {
  map.getSource('footprints')?.setData(fc ?? EMPTY)
}

export function showFootprints(map, on) {
  if (map.getLayer('footprints-3d')) map.setLayoutProperty('footprints-3d', 'visibility', on ? 'visible' : 'none')
}
