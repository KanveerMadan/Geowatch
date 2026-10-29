import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, animate, motion as m, useMotionValue, useReducedMotion } from 'motion/react'
import {
  CaretRight, Crosshair, Cube, X, FrameCorners, GlobeHemisphereWest, MapTrifold, Globe, Mountains, Drop, ArrowsLeftRight, Square, Lasso, MagnifyingGlass, Play, SidebarSimple,
} from '@phosphor-icons/react'
import { motion, breakpoint } from './design/tokens.js'
import MapView from './map/MapView.jsx'
import { clearScan, paintCells, scanFrame, setAoi, setCells, setFootprints, showFootprints } from './map/layers.js'
import { ApiError, JOB_POLL_MS, aoiLabel, getBuildings, getFeatures, getJob, getLimits, getWard, startJob } from './lib/api.js'
import { DEFAULT_POINT_BOX_KM, boxForPlace, maxBoxKm } from './lib/geo.js'
import { linkPlace, linkQuery, parseLink } from './lib/link.js'
import { outputsOf } from './lib/stages.js'
import SearchBar from './components/SearchBar.jsx'
import DrawTool from './components/DrawTool.jsx'
import GroundPanel from './components/GroundPanel.jsx'
import HoverCard from './components/HoverCard.jsx'
import Legend from './components/Legend.jsx'
import CommandPalette from './components/CommandPalette.jsx'
import { Kbd } from './components/bits.jsx'

const TABS = [
  { id: 'ground', label: 'Ground', icon: Mountains, key: '1' },
  { id: 'flood', label: 'Flood', icon: Drop, key: '2' },
  { id: 'change', label: 'Change', icon: ArrowsLeftRight, key: '3' },
]
// Fixed 2026-10-29: map tilt above which building footprints rise in 3D.
const TILT_3D_DEG = 15
const TILT_ON_DEG = 55
const TILTED_CELL_OPACITY = 0.4
// Versioned: a choice stored before satellite became the default (v1) must
// not override it. The old key is removed once; later choices are kept.
const BASEMAP_KEY = 'geowatch.basemap.v2'
const BASEMAP_KEY_OLD = 'geowatch.basemap'
const POLL_FAILURES_BEFORE_NOTICE = 5

const isTyping = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)

export default function App() {
  const reduce = useReducedMotion()
  const [map, setMap] = useState(null)
  const [maxKm2, setMaxKm2] = useState(null)
  const [service, setService] = useState('ok') // 'ok' | 'down'
  const [place, setPlace] = useState(null)
  const [bbox, setBbox] = useState(null)
  const [job, setJob] = useState(null)
  const [startNote, setStartNote] = useState(null)
  // Read before any effect rewrites the URL.
  const link = useRef(parseLink(window.location.search))
  const [tab, setTab] = useState(link.current.tab)
  const [fraction, setFraction] = useState('built')
  const [panelOpen, setPanelOpen] = useState(false)
  const [drawMode, setDrawMode] = useState(null)
  const [boxKm, setBoxKm] = useState(DEFAULT_POINT_BOX_KM)
  // Satellite by default; the dark map is the toggle. Remembered per viewer.
  const [basemap, setBasemapState] = useState(() => {
    try {
      localStorage.removeItem(BASEMAP_KEY_OLD)
      return localStorage.getItem(BASEMAP_KEY) === 'dark' ? 'dark' : 'satellite'
    } catch { return 'satellite' }
  })
  const chooseBasemap = useCallback((b) => {
    setBasemapState(b)
    try { localStorage.setItem(BASEMAP_KEY, b) } catch { /* storage blocked: the choice lasts this visit */ }
  }, [])
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [features, setFeaturesState] = useState(null)
  const [cellsNote, setCellsNote] = useState(null)
  const [hoverCell, setHoverCell] = useState(null)
  const [cell, setCell] = useState(null)
  const [tilted, setTilted] = useState(false)
  const [buildings, setBuildings] = useState('none') // 'none' | 'loading' | 'shown' | 'missing'
  const [searchCmd, setSearchCmd] = useState(null)
  const searchInput = useRef(null)
  const bboxRef = useRef(null)
  const hx = useMotionValue(0)
  const hy = useMotionValue(0)
  const reveal = useRef({ p: 0, v: 1 })
  const resultId = job?.result_id ?? null

  // ── service limits ──
  useEffect(() => {
    getLimits().then((r) => {
      setMaxKm2(r.max_aoi_area_km2)
      setBoxKm((k) => Math.min(k, maxBoxKm(r.max_aoi_area_km2)))
      setService('ok')
    }).catch(() => setService('down'))
  }, [])

  // ── place / area ──
  const flyToBox = useCallback((b) => {
    if (!map) return
    const wide = window.innerWidth > breakpoint.mobile
    const cam = map.cameraForBounds([[b[0], b[1]], [b[2], b[3]]], {
      padding: wide ? { top: 96, bottom: 96, left: 80, right: 440 } : { top: 120, bottom: 320, left: 24, right: 24 },
    })
    // No camera fits (e.g. a box wider than the globe in view): centre on it.
    const target = cam ?? { center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], zoom: Math.max(map.getZoom(), 3) }
    if (reduce) map.jumpTo({ ...target, pitch: 0, bearing: 0 })
    else map.flyTo({ ...target, pitch: 0, bearing: 0, duration: motion.flyTo.ms, curve: motion.flyTo.curve, essential: true })
  }, [map, reduce])

  const resetArea = useCallback(() => {
    setJob(null); setFeaturesState(null); setCell(null); setCellsNote(null); setStartNote(null); setHoverCell(null)
  }, [])

  const onPick = useCallback((p) => {
    const b = boxForPlace(p, maxKm2 ?? Infinity)
    resetArea()
    setPlace({ name: p.name, region: p.region })
    setBbox(b)
    setPanelOpen(true)
    flyToBox(b)
  }, [maxKm2, resetArea, flyToBox])

  // A drawn box replaces any earlier area, and the camera frames it.
  const onDrawn = useCallback((b) => {
    resetArea()
    setPlace(null)
    setBbox(b)
    setDrawMode(null)
    setPanelOpen(true)
    flyToBox(b)
  }, [resetArea, flyToBox])

  // Back to the empty search state: no outline, no area in the panel or URL.
  // The camera stays where it is; a running analysis is left to finish
  // (and be cached) on the server.
  const clearArea = useCallback(() => {
    resetArea(); setBbox(null); setPlace(null); setDrawMode(null); setPanelOpen(false)
    searchInput.current?.focus()
  }, [resetArea])
  const cancelDraw = useCallback(() => setDrawMode(null), [])
  // The drag-free way to set an area: whatever the map shows now.
  const useView = useCallback(() => {
    if (!map) return
    // Level first, so the box is exactly the view and not the bounds of a tilted one.
    map.jumpTo({ pitch: 0, bearing: 0 })
    const b = map.getBounds()
    onDrawn([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => Math.round(v * 1e6) / 1e6))
  }, [map, onDrawn])

  const backToGlobe = useCallback(() => {
    resetArea(); setBbox(null); setPlace(null); setDrawMode(null)
    map?.flyTo({ center: [20, 12], zoom: motion.globe.idleZoom, pitch: 0, bearing: 0, duration: reduce ? 0 : motion.flyTo.ms })
  }, [map, reduce, resetArea])

  useEffect(() => { bboxRef.current = bbox; if (map) setAoi(map, bbox) }, [map, bbox])

  // Deep links: ?bbox=w,s,e,n opens an area; ?job=<id> reattaches to a job.
  useEffect(() => {
    if (!map) return
    const { bbox: b, jobId: id } = link.current
    if (b) {
      setBbox(b); setPlace(linkPlace(b)); setPanelOpen(true); flyToBox(b)
    }
    if (id) {
      getJob(id).then((j) => {
        setBbox(j.request.bbox); setPlace({ name: j.request.aoi_label.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()), region: null })
        setJob(j); setPanelOpen(true); flyToBox(j.request.bbox)
      }).catch(() => setStartNote('That analysis link has expired. Analyse the area again.'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])
  useEffect(() => {
    const q = linkQuery({ bbox, jobId: job?.job_id, jobDone: job?.status === 'complete', tab })
    window.history.replaceState(null, '', q || window.location.pathname)
  }, [bbox, job?.job_id, job?.status, tab])

  // ── analysis job ──
  const analyse = useCallback(async () => {
    if (!bbox) return
    resetArea()
    try {
      setJob(await startJob(bbox, aoiLabel(place?.name ?? 'drawn_area')))
      setService('ok')
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setStartNote('The service refused this area. It may be over the size limit; draw a smaller one.')
      else if (e instanceof ApiError && e.status === 401) setStartNote('This app is not allowed to start analyses: its access key is missing or wrong.')
      else { setService('down'); setStartNote('The analysis could not start: the GeoWatch service is not answering. Try again shortly.') }
    }
  }, [bbox, place, resetArea])

  const jobId = job?.job_id
  const jobLive = job && (job.status === 'queued' || job.status === 'running')
  useEffect(() => {
    if (!jobId || !jobLive) return
    const ctl = new AbortController()
    let fails = 0
    const t = setInterval(async () => {
      try {
        const j = await getJob(jobId, ctl.signal)
        fails = 0
        setService('ok')
        setJob(j)
      } catch (e) {
        if (ctl.signal.aborted) return
        if (e instanceof ApiError && e.status === 404) {
          setJob((j) => ({ ...j, status: 'failed', stages: {}, lost: true }))
        } else if (++fails >= POLL_FAILURES_BEFORE_NOTICE) setService('down')
      }
    }, JOB_POLL_MS)
    return () => { clearInterval(t); ctl.abort() }
  }, [jobId, jobLive])

  // The scan: a sweep over the area while stages run.
  useEffect(() => {
    if (!map || !bbox || !jobLive || reduce) return
    let raf
    const t0 = performance.now()
    const tick = (now) => {
      scanFrame(map, bbox, ((now - t0) % motion.scan.periodMs) / motion.scan.periodMs)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); clearScan(map) }
  }, [map, bbox, jobLive, reduce])

  // Cells: loaded once a stored result exists, then resolved along the sweep.
  useEffect(() => {
    if (!map) return
    if (!resultId) {
      setCells(map, null, [0, 0, 1, 1])
      if (job?.status === 'complete') setCellsNote('The cell map appears once every step finishes.')
      return
    }
    const ctl = new AbortController()
    getFeatures(resultId, 'grid', ctl.signal).then((fc) => {
      setFeaturesState(fc)
      setCells(map, fc, job.result.request.bbox)
      setCellsNote(null)
    }).catch(() => { if (!ctl.signal.aborted) setCellsNote('The cell map could not be loaded. Reload the page to try again.') })
    return () => ctl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, resultId, job?.status])

  useEffect(() => {
    if (!map || !features) return
    if (reduce) { reveal.current.p = 1; paintCells(map, fraction, 1, reveal.current.v); return }
    reveal.current.p = 0
    const c = animate(0, 1, {
      duration: (motion.reveal.ms + motion.reveal.staggerMs * 3) / 1000,
      ease: 'linear',
      onUpdate: (p) => { reveal.current.p = p; paintCells(map, fraction, p, reveal.current.v) },
    })
    return () => c.stop()
    // A new fraction re-resolves the layer: the change is the point.
  }, [map, features, fraction, reduce])

  // Tab switch: the Ground layer crossfades out and back. Tilted, it steps
  // back so the raised buildings read over it.
  useEffect(() => {
    if (!map || !features) return
    const to = tab !== 'ground' ? 0 : tilted ? TILTED_CELL_OPACITY : 1
    const c = animate(reveal.current.v, to, {
      duration: reduce ? 0 : motion.layerCrossfadeMs / 1000,
      onUpdate: (v) => { reveal.current.v = v; paintCells(map, fraction, reveal.current.p, v) },
    })
    return () => c.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, tab, features, tilted])

  // ── hover and click on cells ──
  useEffect(() => {
    if (!map || !features || tab !== 'ground') return
    let hovered = null
    const setHover = (id) => {
      if (hovered === id) return
      if (hovered != null) map.setFeatureState({ source: 'cells', id: hovered }, { hover: false })
      hovered = id
      if (id != null) map.setFeatureState({ source: 'cells', id }, { hover: true })
    }
    const move = (e) => {
      const f = e.features?.[0]
      hx.set(e.originalEvent.clientX + 16)
      hy.set(e.originalEvent.clientY + 16)
      if (!f) return
      if (hovered !== f.id) setHoverCell(f.properties)
      setHover(f.id)
      map.getCanvas().style.cursor = 'pointer'
    }
    const leave = () => { setHover(null); setHoverCell(null); map.getCanvas().style.cursor = '' }
    map.on('mousemove', 'cells-fill', move)
    map.on('mouseleave', 'cells-fill', leave)
    return () => { map.off('mousemove', 'cells-fill', move); map.off('mouseleave', 'cells-fill', leave); leave() }
  }, [map, features, tab, hx, hy])

  const selected = useRef(null)
  useEffect(() => {
    if (!map || !features || !resultId) return
    const click = async (e) => {
      const f = e.features?.[0]
      if (!f) return
      if (selected.current != null) map.setFeatureState({ source: 'cells', id: selected.current }, { selected: false })
      selected.current = f.id
      map.setFeatureState({ source: 'cells', id: f.id }, { selected: true })
      setPanelOpen(true)
      setCell({ unit_id: f.id, loading: true })
      try {
        setCell(await getWard(resultId, 'grid', f.id))
      } catch {
        setCell({ unit_id: f.id, error: true })
      }
    }
    map.on('click', 'cells-fill', click)
    return () => map.off('click', 'cells-fill', click)
  }, [map, features, resultId])

  const closeCell = useCallback(() => {
    if (map && selected.current != null) map.setFeatureState({ source: 'cells', id: selected.current }, { selected: false })
    selected.current = null
    setCell(null)
  }, [map])

  // ── 3D footprints, lazy: fetched the first time the map tilts ──
  useEffect(() => {
    if (!map) return
    const onPitch = () => setTilted(map.getPitch() > TILT_3D_DEG)
    map.on('pitchend', onPitch)
    return () => map.off('pitchend', onPitch)
  }, [map])
  const footprintsFor = useRef(null)
  useEffect(() => {
    if (!map) return
    const on = tilted && tab === 'ground' && !!resultId
    showFootprints(map, on)
    if (on && footprintsFor.current !== resultId) {
      footprintsFor.current = resultId
      setBuildings('loading')
      getBuildings(resultId).then((fc) => { setFootprints(map, fc); setBuildings('shown') })
        .catch(() => setBuildings('missing'))
    }
    if (!resultId) { setFootprints(map, null); setBuildings('none'); footprintsFor.current = null }
  }, [map, tilted, tab, resultId])
  const toggle3d = () => map?.easeTo({ pitch: tilted ? 0 : TILT_ON_DEG, duration: reduce ? 0 : 900 })

  // ── keyboard ──
  useEffect(() => {
    const key = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((o) => !o); return }
      if (isTyping(document.activeElement) || paletteOpen || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === '/') { e.preventDefault(); searchInput.current?.focus() }
      // Esc clears the area, unless a drawing is in progress (Esc cancels that).
      if (e.key === 'Escape' && !drawMode && bboxRef.current) { e.preventDefault(); clearArea() }
      const t = TABS.find((x) => x.key === e.key)
      if (t) setTab(t.id)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [paletteOpen, drawMode, clearArea])

  const actions = useMemo(() => [
    { id: 'search', label: 'Search a place', icon: MagnifyingGlass, kbd: '/', run: () => setTimeout(() => searchInput.current?.focus(), 0) },
    { id: 'rect', label: 'Draw a rectangle', icon: Square, run: () => setDrawMode('rect') },
    { id: 'lasso', label: 'Draw freehand', icon: Lasso, run: () => setDrawMode('lasso') },
    { id: 'point', label: 'Click a point for a fixed box', icon: Crosshair, run: () => setDrawMode('point') },
    { id: 'view', label: 'Use the area in view', icon: FrameCorners, disabled: !map, run: useView },
    { id: 'analyse', label: 'Analyse this area', icon: Play, disabled: !bbox || !!jobLive, run: analyse },
    ...TABS.map((t) => ({ id: `tab-${t.id}`, label: `Show ${t.label}`, icon: t.icon, kbd: t.key, run: () => setTab(t.id) })),
    { id: 'panel', label: panelOpen ? 'Hide the panel' : 'Show the panel', icon: SidebarSimple, run: () => setPanelOpen((o) => !o) },
    { id: '3d', label: tilted ? 'Flatten the map' : 'Tilt the map to 3D', icon: Cube, disabled: !map, run: toggle3d },
    { id: 'clear', label: 'Clear the area', icon: X, kbd: 'Esc', disabled: !bbox, run: clearArea },
    { id: 'globe', label: 'Back to the globe', icon: Globe, run: backToGlobe },
    { id: 'basemap', label: basemap === 'satellite' ? 'Show the dark map' : 'Show satellite imagery', icon: basemap === 'satellite' ? MapTrifold : GlobeHemisphereWest,
      run: () => chooseBasemap(basemap === 'satellite' ? 'dark' : 'satellite') },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [bbox, jobLive, analyse, panelOpen, tilted, map, backToGlobe, useView, basemap, chooseBasemap, clearArea])

  const outputs = outputsOf(job)
  const measuredChoices = Object.entries(outputs.fractions ?? {})
    .filter(([, o]) => o?.status === 'available').map(([k]) => k)
  const panelT = reduce ? { duration: motion.reduced.duration } : motion.spring
  const tabLabel = TABS.find((t) => t.id === tab).label

  return (
    <div className="app">
      <h1 className="sr-only">GeoWatch</h1>
      <MapView onReady={setMap} spinning={!bbox && !drawMode} reducedMotion={reduce} basemap={basemap} />

      <div className="top-left">
        <SearchBar inputRef={searchInput} onPick={onPick} drawMode={drawMode} onDraw={setDrawMode} command={searchCmd} />
      </div>

      <nav className="tabs" role="tablist" aria-label="Views">
        {TABS.map((t) => (
          <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} aria-controls="panel"
            className={tab === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>
            {tab === t.id && <m.span layoutId="tab-pill" className="tab-pill" transition={panelT} />}
            <t.icon size={15} aria-hidden="true" /><span>{t.label}</span><Kbd>{t.key}</Kbd>
          </button>
        ))}
      </nav>

      <DrawTool map={map} mode={drawMode} maxKm2={maxKm2} boxKm={boxKm} onBoxKm={setBoxKm}
        onDone={onDrawn} onCancel={cancelDraw} onUseView={useView} />

      <AnimatePresence initial={false}>
        {panelOpen ? (
          <m.aside
            key="panel"
            id="panel"
            role="tabpanel"
            aria-label={`${tabLabel} panel`}
            className="panel"
            initial={reduce ? { opacity: 0 } : { x: 32, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { x: 32, opacity: 0 }}
            transition={panelT}
          >
            <button type="button" className="icon-btn panel-hide" aria-label="Hide the panel" onClick={() => setPanelOpen(false)}>
              <CaretRight size={16} />
            </button>
            {service === 'down' && (
              <p className="callout callout-warn" role="status">The GeoWatch service is not answering. Search still works; analysis resumes when it is back.</p>
            )}
            {startNote && <p className="callout callout-danger" role="alert">{startNote}</p>}
            <AnimatePresence mode="wait" initial={false}>
              <m.div key={tab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: motion.layerCrossfadeMs / 2000 }}>
                {tab === 'ground' ? (
                  <GroundPanel place={place} bbox={bbox} maxKm2={maxKm2} job={job} onAnalyse={analyse} onRetry={analyse}
                    onRedraw={() => setDrawMode('rect')} fraction={fraction} onFraction={setFraction}
                    cell={cell} onCloseCell={closeCell} cellsNote={cellsNote} onClear={clearArea} />
                ) : (
                  <div className="panel-empty">
                    <p className="lead">{tabLabel} view</p>
                    <p className="muted">This view is the next build step. Ground is ready to use.</p>
                  </div>
                )}
              </m.div>
            </AnimatePresence>
          </m.aside>
        ) : (
          <m.button key="reopen" type="button" className="panel-reopen" onClick={() => setPanelOpen(true)}
            initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={panelT}
            aria-label={`Show the ${tabLabel} panel`}>
            <SidebarSimple size={16} aria-hidden="true" /> {tabLabel}
          </m.button>
        )}
      </AnimatePresence>

      {features && tab === 'ground' && measuredChoices.length > 0 && (
        <Legend fraction={fraction} output={outputs.fractions?.[fraction]} choices={measuredChoices}
          onChoose={setFraction} footprints={tilted ? buildings : 'none'} />
      )}

      <div className="map-tools">
        <div className="seg seg-float" role="radiogroup" aria-label="Base map">
          {[['satellite', 'Satellite'], ['dark', 'Map']].map(([id, label]) => (
            <button key={id} type="button" role="radio" aria-checked={basemap === id} className={basemap === id ? 'on' : ''}
              onClick={() => chooseBasemap(id)}>{label}</button>
          ))}
        </div>
        {bbox && (
          <button type="button" className={`chip${tilted ? ' chip-on' : ''}`} aria-pressed={tilted} onClick={toggle3d} disabled={!map}>
            <Cube size={15} aria-hidden="true" /> 3D
          </button>
        )}
      </div>

      <HoverCard cell={tab === 'ground' ? hoverCell : null} keys={measuredChoices} x={hx} y={hy} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} actions={actions}
        onSearch={(q) => setSearchCmd({ q, n: Date.now() })} />
    </div>
  )
}
