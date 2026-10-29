import { useEffect, useRef } from 'react'
import { color } from '../design/tokens.js'
import { areaState, bboxAreaKm2, bboxOf, bboxPolygon, fmtKm2 } from '../lib/geo.js'
import { setDraft } from '../map/layers.js'

const TONE = { ok: color.select, warn: color.warn, over: color.danger }
const LASSO_MIN_STEP_PX = 4

/**
 * Rectangle (drag) or lasso (freehand) on the map, with a live km² readout
 * by the pointer: white, amber near the limit, red over it. The analysis
 * runs on a box, so a lasso resolves to its bounding box, and the readout
 * is always the box's area. Esc cancels. Pointer events cover mouse, pen
 * and touch. Updates go straight to the DOM and the map, not React state.
 */
export default function DrawTool({ map, mode, maxKm2, onDone, onCancel, onUseView }) {
  const readout = useRef(null)

  useEffect(() => {
    if (!map || !mode) return
    const box = map.getCanvasContainer()
    const canvas = map.getCanvas()
    map.dragPan.disable()
    map.boxZoom.disable()
    map.dragRotate.disable()
    canvas.style.cursor = 'crosshair'
    let start = null
    let pts = []
    let lastPx = null

    const ll = (e) => {
      const r = canvas.getBoundingClientRect()
      const p = map.unproject([e.clientX - r.left, e.clientY - r.top])
      return [p.lng, p.lat]
    }
    const show = (e, bbox) => {
      const km2 = bboxAreaKm2(bbox)
      const st = areaState(km2, maxKm2)
      const el = readout.current
      if (el) {
        el.hidden = false
        el.dataset.state = st
        el.style.transform = `translate(${e.clientX + 14}px, ${e.clientY + 14}px)`
        el.firstChild.textContent = fmtKm2(km2)
        el.lastChild.textContent = st === 'over' ? `over the ${maxKm2} km² limit` : st === 'warn' ? 'near the limit' : ''
      }
      return st
    }

    const down = (e) => {
      if (e.button !== 0) return
      e.preventDefault()
      box.setPointerCapture?.(e.pointerId)
      start = ll(e)
      pts = [start]
      lastPx = [e.clientX, e.clientY]
    }
    const move = (e) => {
      if (!start) return
      const p = ll(e)
      let geom, bbox
      if (mode === 'rect') {
        bbox = bboxOf([start, p])
        geom = bboxPolygon(bbox)
      } else {
        if (Math.hypot(e.clientX - lastPx[0], e.clientY - lastPx[1]) >= LASSO_MIN_STEP_PX) {
          pts.push(p)
          lastPx = [e.clientX, e.clientY]
        }
        bbox = bboxOf(pts)
        geom = { type: 'Polygon', coordinates: [[...pts, pts[0]]] }
      }
      setDraft(map, geom, TONE[show(e, bbox)])
    }
    const up = (e) => {
      if (!start) return
      const bbox = mode === 'rect' ? bboxOf([start, ll(e)]) : bboxOf(pts)
      start = null
      if (readout.current) readout.current.hidden = true
      setDraft(map, null)
      if (bbox[2] - bbox[0] > 0 && bbox[3] - bbox[1] > 0) onDone(bbox, mode)
    }
    const key = (e) => { if (e.key === 'Escape') onCancel() }

    box.addEventListener('pointerdown', down)
    box.addEventListener('pointermove', move)
    box.addEventListener('pointerup', up)
    window.addEventListener('keydown', key)
    return () => {
      box.removeEventListener('pointerdown', down)
      box.removeEventListener('pointermove', move)
      box.removeEventListener('pointerup', up)
      window.removeEventListener('keydown', key)
      map.dragPan.enable()
      map.boxZoom.enable()
      map.dragRotate.enable()
      canvas.style.cursor = ''
      setDraft(map, null)
    }
  }, [map, mode, maxKm2, onDone, onCancel])

  if (!mode) return null
  return (
    <>
      <div className="draw-hint" role="status">
        <span>{mode === 'rect' ? 'Drag to draw a rectangle.' : 'Drag to draw freehand. The analysis uses its bounding box.'} Esc to cancel.</span>
        <button type="button" className="link-btn" onClick={onUseView}>Use the area in view</button>
      </div>
      <div ref={readout} className="area-readout" hidden aria-hidden="true"><span /><small /></div>
    </>
  )
}
