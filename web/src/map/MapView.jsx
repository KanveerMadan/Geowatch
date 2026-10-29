import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { color, motion } from '../design/tokens.js'
import { addLayers } from './layers.js'

// The dark map: OpenFreeMap, free vector tiles with no key, OpenStreetMap data.
const DARK_STYLE = 'https://tiles.openfreemap.org/styles/dark'

// Satellite, the default: Esri World Imagery with Esri's place labels over
// it. Attribution is the services' own copyrightText (?f=json, read
// 2026-10-29), prefixed "Powered by Esri" as Esri asks. Esri's terms must be
// checked before any public deployment: these are the public tile endpoints.
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services'
const SATELLITE_SOURCES = {
  'esri-imagery': {
    type: 'raster', tileSize: 256, maxzoom: 19,
    tiles: [`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`],
    attribution: 'Powered by <a href="https://www.esri.com">Esri</a> | Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community',
  },
  'esri-labels': {
    type: 'raster', tileSize: 256, maxzoom: 19,
    tiles: [`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`],
    attribution: 'Labels: Esri, HERE, Garmin, © OpenStreetMap contributors, and the GIS user community',
  },
}
const SATELLITE_LAYERS = [
  { id: 'esri-imagery', type: 'raster', source: 'esri-imagery', paint: { 'raster-fade-duration': 200 } },
  { id: 'esri-labels', type: 'raster', source: 'esri-labels', paint: { 'raster-opacity': 0.9, 'raster-fade-duration': 200 } },
]

// The dark map stays quiet so data layers carry the contrast: land a step
// above the canvas, water a step below, roads and borders as hairlines.
const DARK_PAINT = [
  ['background', 'background-color', '#15181d'],
  ['water', 'fill-color', '#08090c'],
  ['waterway', 'line-color', '#08090c'],
  ['landuse_residential', 'fill-color', '#191c22'],
  ['landcover_wood', 'fill-color', '#171c1b'],
  ['landuse_park', 'fill-color', '#171c1b'],
  ['building', 'fill-color', '#1e2228'],
  ['boundary_country_z0-4', 'line-color', '#3a3f48'],
  ['boundary_country_z5-', 'line-color', '#3a3f48'],
  ['boundary_state', 'line-color', '#2a2e35'],
  ['aeroway-runway', 'line-color', '#22262d'],
  ['aeroway-area', 'fill-color', '#1a1d23'],
]

/** One style holding both basemaps: the dark map's layers, then Esri's
 *  above them. Switching is visibility only, so the data layers, sources
 *  and camera are untouched and nothing reloads. */
async function buildStyle() {
  const dark = await (await fetch(DARK_STYLE)).json()
  for (const l of dark.layers) {
    const p = DARK_PAINT.find(([id]) => id === l.id)
    if (p) l.paint = { ...l.paint, [p[1]]: p[2] }
  }
  return {
    style: { ...dark, sources: { ...dark.sources, ...SATELLITE_SOURCES }, layers: [...dark.layers, ...SATELLITE_LAYERS] },
    darkLayerIds: dark.layers.map((l) => l.id),
  }
}

let darkLayerIds = []

export function setBasemap(map, base) {
  const vis = (on) => (on ? 'visible' : 'none')
  for (const id of darkLayerIds) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis(base === 'dark'))
  for (const l of SATELLITE_LAYERS) if (map.getLayer(l.id)) map.setLayoutProperty(l.id, 'visibility', vis(base === 'satellite'))
}

function atmosphere(map) {
  // A thin atmosphere at globe zooms, gone by the time the map is flat.
  map.setSky({
    'sky-color': color.canvas,
    'horizon-color': '#1c2633',
    'fog-color': color.canvas,
    'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 0.9, 5, 0.5, 8, 0],
  })
}

/** The full-screen map. Owns the MapLibre instance and the idle globe spin;
 *  everything else drives it through `onReady(map)`. */
export default function MapView({ onReady, spinning, reducedMotion, basemap }) {
  const el = useRef(null)
  const mapRef = useRef(null)
  const spinRef = useRef(spinning)
  spinRef.current = spinning && !reducedMotion
  const baseRef = useRef(basemap)
  baseRef.current = basemap

  useEffect(() => {
    let map, raf, cancelled = false
    buildStyle().then(({ style, darkLayerIds: ids }) => {
      if (cancelled) return
      darkLayerIds = ids
      map = new maplibregl.Map({
        container: el.current,
        style,
        center: [20, 12],
        zoom: motion.globe.idleZoom,
        attributionControl: { compact: true },
        maxPitch: 70,
      })
      mapRef.current = map
      if (import.meta.env.DEV) window.__map = map // for browser debugging only
      // The dark style names a few POI icons it ships no sprite for; draw none.
      map.on('styleimagemissing', (e) => {
        if (!map.hasImage(e.id)) map.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) })
      })
      map.on('style.load', () => {
        map.setProjection({ type: 'globe' })
        atmosphere(map)
        setBasemap(map, baseRef.current)
        addLayers(map)
        onReady(map)
      })
      // Keyboard users get the map's own handlers once it has focus.
      map.getCanvas().setAttribute('aria-label', 'Map. Arrow keys pan, plus and minus zoom.')

      let last = performance.now(), held = false
      map.on('mousedown', () => { held = true }); map.on('touchstart', () => { held = true })
      map.on('mouseup', () => { held = false }); map.on('touchend', () => { held = false })
      const tick = (now) => {
        const dt = (now - last) / 1000
        last = now
        if (spinRef.current && !held && !map.isMoving()) {
          const c = map.getCenter()
          map.jumpTo({ center: [c.lng + motion.globe.degPerSecond * dt, c.lat] })
        }
        raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)
    })
    return () => { cancelled = true; cancelAnimationFrame(raf); map?.remove() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { if (mapRef.current?.getLayer('esri-imagery')) setBasemap(mapRef.current, basemap) }, [basemap])

  return <div ref={el} className="map" />
}
