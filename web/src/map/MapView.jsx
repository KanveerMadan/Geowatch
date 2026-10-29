import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { color, motion } from '../design/tokens.js'
import { addLayers } from './layers.js'

// OpenFreeMap: free vector tiles with no key, OpenStreetMap data.
const BASE_STYLE = 'https://tiles.openfreemap.org/styles/dark'

// The base map stays quiet so data layers carry the contrast: land a step
// above the canvas, water a step below, roads and borders as hairlines.
const BASE_PAINT = [
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

function quietBase(map) {
  for (const [id, prop, value] of BASE_PAINT) if (map.getLayer(id)) map.setPaintProperty(id, prop, value)
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
export default function MapView({ onReady, spinning, reducedMotion }) {
  const el = useRef(null)
  const mapRef = useRef(null)
  const spinRef = useRef(spinning)
  spinRef.current = spinning && !reducedMotion

  useEffect(() => {
    const map = new maplibregl.Map({
      container: el.current,
      style: BASE_STYLE,
      center: [20, 12],
      zoom: motion.globe.idleZoom,
      attributionControl: { compact: true },
      maxPitch: 70,
    })
    mapRef.current = map
    // The base style names a few POI icons it ships no sprite for; draw none.
    map.on('styleimagemissing', (e) => {
      if (!map.hasImage(e.id)) map.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) })
    })
    map.on('style.load', () => {
      map.setProjection({ type: 'globe' })
      quietBase(map)
      addLayers(map)
      onReady(map)
    })
    // Keyboard users get the map's own handlers once it has focus.
    map.getCanvas().setAttribute('aria-label', 'Map. Arrow keys pan, plus and minus zoom.')

    let raf, last = performance.now(), held = false
    const hold = () => { held = true }
    const release = () => { held = false }
    map.on('mousedown', hold); map.on('touchstart', hold)
    map.on('mouseup', release); map.on('touchend', release)
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
    return () => { cancelAnimationFrame(raf); map.remove() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <div ref={el} className="map" />
}
