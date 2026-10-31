import { useEffect, useRef } from 'react'
import { color } from '../design/tokens.js'
import { MIN_POINT_BOX_KM, areaState, bboxAreaKm2, bboxOf, boxAround, fmtKm2, maxBoxKm } from '../lib/geo.js'
import { setDraft } from '../map/layers.js'

const TONE = { ok: color.select, warn: color.warn, over: color.danger }
const LASSO_MIN_STEP_PX = 4
const CLICK_SLOP_PX = 5        // a press that moves less than this is a click
const OFF_GLOBE_PX = 2         // unproject -> project must land back within this
const LEVEL_MS = 450

const HINT = {
  rect: 'Drag to draw a rectangle.',
  lasso: 'Drag to draw freehand. The analysis uses its bounding box.',
  point: 'Click a point for a square box around it.',
}

/**
 * Three ways to set an area, all ending in a [w, s, e, n] box: the box that
 * is drawn is the box that is analysed.
 *   rect   drag two corners
 *   lasso  drag freehand; its bounding box is used
 *   point  click a point; a boxKm-square box centred on it
 * Drawing levels the map first (north up, no tilt), so a drag on screen is a
 * rectangle on the ground, and ignores points off the globe's edge. A live
 * km² readout follows the pointer: white, amber near the limit, red over
 * it. Esc cancels. Pointer events cover mouse, pen and touch. Updates go
 * straight to the DOM and the map, not React state.
 */
export default function DrawTool({ map, mode, maxKm2, boxKm, onBoxKm, onDone, onCancel, onUseView }) {
  const readout = useRef(null)
  const boxKmRef = useRef(boxKm)
  boxKmRef.current = boxKm

  useEffect(() => {
    if (!map || !mode) return
    const box = map.getCanvasContainer()
    const canvas = map.getCanvas()
    if (map.getPitch() || map.getBearing()) map.easeTo({ pitch: 0, bearing: 0, duration: LEVEL_MS })
    map.dragPan.disable()
    map.boxZoom.disable()
    map.dragRotate.disable()
    map.touchPitch.disable()
    if (mode !== 'point') map.touchZoomRotate.disableRotation()
    canvas.style.cursor = 'crosshair'
    let start = null, startPx = null, lastPx = null, pts = []

    const ll = (e) => {
      const r = canvas.getBoundingClientRect()
      const px = [e.clientX - r.left, e.clientY - r.top]
      const p = map.unproject(px)
      const back = map.project(p)
      if (Math.hypot(back.x - px[0], back.y - px[1]) > OFF_GLOBE_PX) return null
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
    const hide = () => { if (readout.current) readout.current.hidden = true }
    const pointBox = (p) => boxAround(p[1], p[0], boxKmRef.current)

    const down = (e) => {
      if (e.button !== 0 || map.isMoving()) return
      const p = ll(e)
      if (!p) return
      e.preventDefault()
      box.setPointerCapture?.(e.pointerId)
      start = p
      startPx = lastPx = [e.clientX, e.clientY]
      pts = [p]
    }
    const move = (e) => {
      const p = ll(e)
      if (!p) return
      if (mode === 'point') {
        // The box follows the pointer, so its size is seen before the click.
        const b = pointBox(p)
        setDraft(map, b, TONE[show(e, b)])
        return
      }
      if (!start) return
      let shape, bbox
      if (mode === 'rect') {
        bbox = bboxOf([start, p])
        shape = bbox
      } else {
        if (Math.hypot(e.clientX - lastPx[0], e.clientY - lastPx[1]) >= LASSO_MIN_STEP_PX) {
          pts.push(p)
          lastPx = [e.clientX, e.clientY]
        }
        bbox = bboxOf(pts)
        shape = pts
      }
      setDraft(map, shape, TONE[show(e, bbox)])
    }
    const up = (e) => {
      if (!start) return
      const p = ll(e) ?? pts.at(-1)
      const clicked = Math.hypot(e.clientX - startPx[0], e.clientY - startPx[1]) < CLICK_SLOP_PX
      let bbox = null
      if (mode === 'point') bbox = clicked ? pointBox(start) : null
      else if (mode === 'rect') bbox = bboxOf([start, p])
      else bbox = bboxOf(pts)
      start = null
      hide()
      setDraft(map, null)
      if (bbox && bbox[2] > bbox[0] && bbox[3] > bbox[1]) onDone(bbox, mode)
    }
    const leave = () => { if (mode === 'point') { hide(); setDraft(map, null) } }
    const key = (e) => { if (e.key === 'Escape') onCancel() }

    box.addEventListener('pointerdown', down)
    box.addEventListener('pointermove', move)
    box.addEventListener('pointerup', up)
    box.addEventListener('pointerleave', leave)
    window.addEventListener('keydown', key)
    return () => {
      box.removeEventListener('pointerdown', down)
      box.removeEventListener('pointermove', move)
      box.removeEventListener('pointerup', up)
      box.removeEventListener('pointerleave', leave)
      window.removeEventListener('keydown', key)
      map.dragPan.enable()
      map.boxZoom.enable()
      map.dragRotate.enable()
      map.touchPitch.enable()
      map.touchZoomRotate.enableRotation()
      canvas.style.cursor = ''
      hide()
      setDraft(map, null)
    }
  }, [map, mode, maxKm2, onDone, onCancel])

  if (!mode) return null
  const maxKm = maxKm2 ? maxBoxKm(maxKm2) : 10
  return (
    <>
      <div className="draw-hint" role="status">
        <span>{HINT[mode]} Esc to cancel.</span>
        {mode === 'point' && (
          <label className="box-size">
            <span>Box</span>
            <input type="range" min={MIN_POINT_BOX_KM} max={maxKm} step={0.5} value={Math.min(boxKm, maxKm)}
              onChange={(e) => onBoxKm(Number(e.target.value))} aria-valuetext={`${boxKm} by ${boxKm} kilometres`} />
            <output className="num">{boxKm}&nbsp;×&nbsp;{boxKm}&nbsp;km</output>
          </label>
        )}
        <button type="button" className="link-btn" onClick={onUseView}>Use the area in view</button>
      </div>
      <div ref={readout} className="area-readout" hidden aria-hidden="true"><span /><small /></div>
    </>
  )
}
