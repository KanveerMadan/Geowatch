import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { color, changeStyle } from '../design/tokens.js'
import { cellChange } from '../lib/change.js'
import { homography, pathOf, toUnit } from '../lib/overlay.js'

// Below this zoom the analysed box is a few pixels: nothing to compare.
const MIN_ZOOM = 9
const STEP = 0.02

/** Before / after pictures of the analysed box with a swipe between them,
 *  and the changed cells of one fraction drawn over both. Everything is in
 *  one square laid on the map by its four projected corners (lib/overlay.js),
 *  repositioned on every map frame without a React render. */
export default function SwipeOverlay({ map, bbox, cells, fraction, before, after, split, onSplit, hoverId }) {
  const root = useRef(null)
  const side = useRef(1024)
  const [px, setPx] = useState(1 / 1024) // one screen pixel in the square's units, once settled
  const pid = useId().replace(/:/g, '')

  const place = useCallback(() => {
    const el = root.current
    if (!el || !map || !bbox) return
    const [w, s, e, n] = bbox
    const quad = [[w, n], [e, n], [e, s], [w, s]].map((c) => { const p = map.project(c); return [p.x, p.y] })
    const ok = map.getZoom() >= MIN_ZOOM && quad.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
    el.style.visibility = ok ? 'visible' : 'hidden'
    if (!ok) return
    // Keep the square's own size near its size on screen, so the transform
    // stays close to 1:1 and edges stay sharp once the map settles.
    const span = Math.max(...quad.map((p) => p[0])) - Math.min(...quad.map((p) => p[0]))
    const want = Math.min(4096, Math.max(256, Math.round(span)))
    if (Math.abs(want - side.current) / side.current > 0.25 && !map.isMoving()) {
      side.current = want
      el.style.width = el.style.height = `${want}px`
      setPx(1 / want)
    }
    el.style.transform = homography(side.current, quad)
  }, [map, bbox])

  useEffect(() => {
    if (!map) return
    place()
    map.on('move', place)
    map.on('moveend', place)
    map.on('resize', place)
    return () => { map.off('move', place); map.off('moveend', place); map.off('resize', place) }
  }, [map, place])

  const paths = useMemo(() => {
    const by = { increase: [], decrease: [], unjudged: [] }
    for (const c of cells ?? []) {
      const k = cellChange(c.props, fraction)
      if (by[k]) by[k].push(c)
    }
    return { up: pathOf(by.increase), down: pathOf(by.decrease), unjudged: pathOf(by.unjudged) }
  }, [cells, fraction])
  const hoverPath = useMemo(() => pathOf((cells ?? []).filter((c) => c.id === hoverId)), [cells, hoverId])

  // Dragging the handle: the pointer's longitude across the box is the split.
  const drag = useRef(false)
  const toSplit = useCallback((ev) => {
    const ll = map.unproject([ev.clientX, ev.clientY])
    const [x] = toUnit(bbox)([ll.lng, ll.lat])
    onSplit(Math.min(1, Math.max(0, x)))
  }, [map, bbox, onSplit])
  const down = (ev) => { drag.current = true; ev.currentTarget.setPointerCapture(ev.pointerId); ev.preventDefault() }
  const move = (ev) => { if (drag.current) toSplit(ev) }
  const up = () => { drag.current = false }
  const key = (ev) => {
    const d = { ArrowLeft: -STEP, ArrowRight: STEP, ArrowDown: -STEP, ArrowUp: STEP }[ev.key]
    if (d) { ev.preventDefault(); onSplit(Math.min(1, Math.max(0, split + d))) }
    if (ev.key === 'Home') { ev.preventDefault(); onSplit(0) }
    if (ev.key === 'End') { ev.preventDefault(); onSplit(1) }
  }

  const hue = color.data[fraction] ?? color.select
  const half = (p, cls) => (
    p?.url ? <img className={cls} src={p.url} alt="" draggable={false} />
      : <div className={`${cls} swipe-empty${p?.state === 'loading' ? ' skeleton' : ''}`}>
        {p?.state === 'missing' && <span>No clear imagery in {p.year}</span>}
        {p?.state === 'error' && <span>Imagery for {p.year} did not load</span>}
      </div>
  )

  return (
    <div ref={root} className="swipe-root" style={{ width: side.current, height: side.current }}>
      {half(before, 'swipe-img')}
      <div className="swipe-after" style={{ clipPath: `inset(0 0 0 ${split * 100}%)` }}>{half(after, 'swipe-img')}</div>
      <svg className="swipe-cells" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <pattern id={`down-${pid}`} patternUnits="userSpaceOnUse" width={px * 6} height={px * 6} patternTransform="rotate(45)">
            <rect width={px * 2.5} height={px * 6} fill={hue} />
          </pattern>
          <pattern id={`na-${pid}`} patternUnits="userSpaceOnUse" width={px * 5} height={px * 5} patternTransform="rotate(-45)">
            <rect width={px * 1.5} height={px * 5} fill={color.data.notMeasured} />
          </pattern>
        </defs>
        <path d={paths.unjudged} fill={`url(#na-${pid})`} opacity="0.85" />
        <path d={paths.up} fill={hue} fillOpacity={changeStyle.fillOpacity} stroke={hue} strokeWidth="1" vectorEffect="non-scaling-stroke" />
        <path d={paths.down} fill={`url(#down-${pid})`} fillOpacity={changeStyle.stripeOpacity} stroke={hue} strokeWidth="1" vectorEffect="non-scaling-stroke" />
        {hoverPath && <path d={hoverPath} fill="none" stroke={color.select} strokeWidth="2" vectorEffect="non-scaling-stroke" />}
      </svg>
      <div className="swipe-line" style={{ left: `${split * 100}%` }}>
        <span className="swipe-tag swipe-tag-l">{before?.year}</span>
        <span className="swipe-tag swipe-tag-r">{after?.year}</span>
        <button type="button" className="swipe-handle" role="slider" aria-label="Swipe between the before and after pictures"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(split * 100)}
          aria-valuetext={`${Math.round(split * 100)}% ${before?.year ?? ''}, the rest ${after?.year ?? ''}`}
          onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onKeyDown={key}>
          <span aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
