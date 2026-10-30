import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { color } from '../design/tokens.js'
import { boxRing } from '../lib/geo.js'

// The report's maps are pictures: Esri imagery under the layer, the box
// outlined. Each renders once, is copied to an <img> (prints reliably, and
// frees its WebGL context), then the map is removed.
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const IDLE_TIMEOUT_MS = 20000
const PAD_PX = 18

// One at a time: browsers cap live WebGL contexts.
let queue = Promise.resolve()

export default function StaticMap({ bbox, addLayers, label, height = 300 }) {
  const box = useRef(null)
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    queue = queue.then(() => new Promise((done) => {
      if (cancelled || !box.current) return done()
      const map = new maplibregl.Map({
        container: box.current,
        style: {
          version: 8,
          sources: { esri: { type: 'raster', tiles: [ESRI], tileSize: 256, maxzoom: 19 } },
          layers: [{ id: 'esri', type: 'raster', source: 'esri', paint: { 'raster-saturation': -0.25 } }],
        },
        bounds: [[bbox[0], bbox[1]], [bbox[2], bbox[3]]],
        fitBoundsOptions: { padding: PAD_PX },
        interactive: false,
        attributionControl: false,
        preserveDrawingBuffer: true,
        fadeDuration: 0,
      })
      const finish = (ok) => {
        clearTimeout(timer)
        if (!cancelled) {
          if (ok) {
            try { setSrc(map.getCanvas().toDataURL('image/png')) } catch { setFailed(true) }
          } else setFailed(true)
        }
        map.remove()
        done()
      }
      const timer = setTimeout(() => finish(map.loaded()), IDLE_TIMEOUT_MS)
      map.on('load', () => {
        addLayers?.(map)
        map.addSource('aoi', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: boxRing(bbox) } } })
        map.addLayer({ id: 'aoi-casing', type: 'line', source: 'aoi', paint: { 'line-color': '#000', 'line-width': 4, 'line-opacity': 0.4 } })
        map.addLayer({ id: 'aoi', type: 'line', source: 'aoi', paint: { 'line-color': color.select, 'line-width': 1.5 } })
        map.once('idle', () => finish(true))
      })
      map.on('error', () => { /* a missing tile is not fatal; the timeout bounds it */ })
    }))
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <figure className="rmap" style={{ height }}>
      {src ? <img src={src} alt={label} /> : <div ref={box} className="rmap-live" aria-hidden="true" />}
      {!src && !failed && <span className="rmap-wait">Drawing the map…</span>}
      {failed && <span className="rmap-wait">The map could not be drawn.</span>}
    </figure>
  )
}
