import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, animate, motion as m, useMotionValue, useReducedMotion } from 'motion/react'
import {
  CaretDown, CaretRight, Crosshair, Cube, X, FrameCorners, GlobeHemisphereWest, MapTrifold, Globe, Mountains, Drop, ArrowsLeftRight, Square, Lasso, MagnifyingGlass, Play, SidebarSimple, FileText,
} from '@phosphor-icons/react'
import { motion, breakpoint } from './design/tokens.js'
import MapView from './map/MapView.jsx'
import { clearScan, paintCells, scanFrame, setAoi, setCells, setFootprints, showFootprints } from './map/layers.js'
import {
  ApiError, JOB_POLL_MS, aoiLabel, getBoundaries, getBuildings, getChangeFeatures, getFeatures, getImageryYear,
  getImageryYears, getJob, getLimits, getWard, startJob,
} from './lib/api.js'
import { DEFAULT_POINT_BOX_KM, boundaryFor, boxForPlace, maxBoxKm } from './lib/geo.js'
import { linkPlace, linkQuery, parseLink, reportHref } from './lib/link.js'
import { outputsOf } from './lib/stages.js'
import { defaultFloodLayer, floodRows, wardUnitType } from './lib/flood.js'
import { changeRows } from './lib/change.js'
import { cellAt, toUnit, unitCells } from './lib/overlay.js'
import SearchBar from './components/SearchBar.jsx'
import DrawTool from './components/DrawTool.jsx'
import AreaStatus from './components/AreaStatus.jsx'
import GroundPanel from './components/GroundPanel.jsx'
import FloodPanel from './components/FloodPanel.jsx'
import ChangePanel from './components/ChangePanel.jsx'
import HoverCard from './components/HoverCard.jsx'
import Legend from './components/Legend.jsx'
import FloodLegend from './components/FloodLegend.jsx'
import ChangeDock from './components/ChangeDock.jsx'
import SwipeOverlay from './components/SwipeOverlay.jsx'
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
// The mobile sheet: dragged further than this, it snaps to the next height.
const SHEET_SNAP_PX = 36
const MOBILE_QUERY = `(max-width: ${breakpoint.mobile}px)`

const isTyping = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)

function useMobile() {
  const [on, setOn] = useState(() => window.matchMedia(MOBILE_QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY)
    const f = () => setOn(mq.matches)
    mq.addEventListener('change', f)
    return () => mq.removeEventListener('change', f)
  }, [])
  return on
}

export default function App() {
  const reduce = useReducedMotion()
  const mobile = useMobile()
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
  const [floodLayer, setFloodLayer] = useState(null)
  const [changeFraction, setChangeFraction] = useState(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const [sheet, setSheet] = useState('peek') // mobile only: 'peek' | 'full'
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
  const [boundaries, setBoundaries] = useState([])
  const [wards, setWards] = useState(null) // {name, fc, loading, failed}
  const [changeCells, setChangeCells] = useState(null)
  const [changeNote, setChangeNote] = useState(null)
  const [imagery, setImagery] = useState(null) // {years, compared}
  const [pair, setPair] = useState(null)
  const [split, setSplit] = useState(0.5)
  const [imgs, setImgs] = useState({}) // {year: {state, url}}
  const [changeHover, setChangeHover] = useState(null)
  const searchInput = useRef(null)
  const bboxRef = useRef(null)
  const hx = useMotionValue(0)
  const hy = useMotionValue(0)
  const reveal = useRef({ p: 0, v: 1 })
  const resultId = job?.result_id ?? null
  const result = job?.result ?? null
  const outputs = outputsOf(job)

  // ── service limits and the ward layers it holds ──
  useEffect(() => {
    getLimits().then((r) => {
      setMaxKm2(r.max_aoi_area_km2)
      setBoxKm((k) => Math.min(k, maxBoxKm(r.max_aoi_area_km2)))
      setService('ok')
    }).catch(() => setService('down'))
    getBoundaries().then((r) => setBoundaries(r.boundaries)).catch(() => { /* no ward ranking offered */ })
  }, [])
  const wardLayer = bbox ? boundaryFor(bbox, boundaries) : null

  // ── place / area ──
  const flyToBox = useCallback((b) => {
    if (!map) return
    const wide = window.innerWidth > breakpoint.mobile
    const cam = map.cameraForBounds([[b[0], b[1]], [b[2], b[3]]], {
      padding: wide ? { top: 96, bottom: 96, left: 80, right: 440 } : { top: 120, bottom: Math.round(window.innerHeight * 0.45), left: 24, right: 24 },
    })
    // No camera fits (e.g. a box wider than the globe in view): centre on it.
    const target = cam ?? { center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], zoom: Math.max(map.getZoom(), 3) }
    if (reduce) map.jumpTo({ ...target, pitch: 0, bearing: 0 })
    else map.flyTo({ ...target, pitch: 0, bearing: 0, duration: motion.flyTo.ms, curve: motion.flyTo.curve, essential: true })
  }, [map, reduce])

  const resetArea = useCallback(() => {
    setJob(null); setFeaturesState(null); setCell(null); setCellsNote(null); setStartNote(null); setHoverCell(null)
    setFloodLayer(null); setChangeFraction(null); setWards(null); setChangeCells(null); setChangeNote(null)
    setImagery(null); setPair(null); setChangeHover(null); setSplit(0.5)
  }, [])

  const onPick = useCallback((p) => {
    const b = boxForPlace(p, maxKm2 ?? Infinity)
    resetArea()
    setPlace({ name: p.name, region: p.region })
    setBbox(b)
    setPanelOpen(true); setSheet('peek')
    flyToBox(b)
  }, [maxKm2, resetArea, flyToBox])

  // A drawn box replaces any earlier area, and the camera frames it.
  const onDrawn = useCallback((b) => {
    resetArea()
    setPlace(null)
    setBbox(b)
    setDrawMode(null)
    setPanelOpen(true); setSheet('peek')
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
      setJob(await startJob(bbox, aoiLabel(place?.name ?? 'drawn_area'), wardLayer?.boundary_layer_id))
      setService('ok')
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setStartNote('The service refused this area. It may be over the size limit; draw a smaller one.')
      else if (e instanceof ApiError && e.status === 401) setStartNote('This app is not allowed to start analyses: its access key is missing or wrong.')
      else { setService('down'); setStartNote('The analysis could not start: the GeoWatch service is not answering. Try again shortly.') }
    }
  }, [bbox, place, resetArea, wardLayer])

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

  // Each tab's default layer, once its group arrives.
  useEffect(() => {
    if (!floodLayer && outputs.susceptibility) setFloodLayer(defaultFloodLayer(outputs.susceptibility))
  }, [floodLayer, outputs.susceptibility])
  const chRows = useMemo(() => changeRows(outputs.change), [outputs.change])
  const changeChoices = useMemo(() => chRows.filter((r) => r.measured).map((r) => r.key), [chRows])
  useEffect(() => {
    if (!changeFraction && changeChoices.length) setChangeFraction(changeChoices[0])
  }, [changeFraction, changeChoices])

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

  // What the cell layers show: Ground's fraction, or Flood's type.
  const cellLayer = useMemo(() => (tab === 'flood' && floodLayer
    ? { kind: 'flood', key: floodLayer } : { kind: 'fraction', key: fraction }), [tab, floodLayer, fraction])
  const layerRef = useRef(cellLayer)
  layerRef.current = cellLayer

  useEffect(() => {
    if (!map || !features) return
    if (reduce) { reveal.current.p = 1; paintCells(map, cellLayer, 1, reveal.current.v); return }
    reveal.current.p = 0
    const c = animate(0, 1, {
      duration: (motion.reveal.ms + motion.reveal.staggerMs * 3) / 1000,
      ease: 'linear',
      onUpdate: (p) => { reveal.current.p = p; paintCells(map, cellLayer, p, reveal.current.v) },
    })
    return () => c.stop()
    // A new layer re-resolves the cells: the change is the point.
  }, [map, features, cellLayer, reduce])

  // Tab switch: the cell layer crossfades. Change draws its own cells over
  // the pictures, so the shared ones step out; tilted, they step back so
  // the raised buildings read over them.
  const cellsShown = tab === 'ground' || (tab === 'flood' && !!floodLayer)
  useEffect(() => {
    if (!map || !features) return
    const to = !cellsShown ? 0 : tilted ? TILTED_CELL_OPACITY : 1
    const c = animate(reveal.current.v, to, {
      duration: reduce ? 0 : motion.layerCrossfadeMs / 1000,
      onUpdate: (v) => { reveal.current.v = v; paintCells(map, layerRef.current, reveal.current.p, v) },
    })
    return () => c.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, cellsShown, features, tilted])

  // ── hover and click on cells ──
  useEffect(() => {
    if (!map || !features || !cellsShown) return
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
  }, [map, features, cellsShown, hx, hy])

  const selected = useRef(null)
  useEffect(() => {
    if (!map || !features || !resultId || tab !== 'ground') return
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
  }, [map, features, resultId, tab])

  const closeCell = useCallback(() => {
    if (map && selected.current != null) map.setFeatureState({ source: 'cells', id: selected.current }, { selected: false })
    selected.current = null
    setCell(null)
  }, [map])

  // ── Flood: the ward ranking, when the result carries wards ──
  const wardType = wardUnitType(result)
  useEffect(() => {
    if (!resultId || !wardType) { setWards(null); return }
    const id = wardType.slice('ward:'.length)
    const name = boundaries.find((b) => b.boundary_layer_id === id)?.name ?? id.replace(/_/g, ' ')
    const ctl = new AbortController()
    setWards({ name, loading: true })
    getFeatures(resultId, wardType, ctl.signal).then((fc) => setWards({ name, fc }))
      .catch(() => { if (!ctl.signal.aborted) setWards({ name, failed: true }) })
    return () => ctl.abort()
  }, [resultId, wardType, boundaries])

  // ── Change: per-cell verdicts and the pictures, fetched on first visit ──
  const changeBbox = result?.request?.bbox ?? null
  useEffect(() => {
    if (tab !== 'change' || !resultId || changeCells) return
    const ctl = new AbortController()
    getChangeFeatures(resultId, ctl.signal)
      .then((fc) => {
        setChangeCells(unitCells(fc, changeBbox))
        setChangeNote(fc.status === 'available' ? null : 'Per-cell change is not available for this result.')
      })
      .catch((e) => {
        if (ctl.signal.aborted) return
        setChangeNote(e instanceof ApiError && e.status === 404
          ? 'This result was stored before per-cell change was kept. Analyse the area again to see changed cells.'
          : 'The changed cells could not be loaded. Reload the page to try again.')
      })
    return () => ctl.abort()
  }, [tab, resultId, changeCells, changeBbox])

  useEffect(() => {
    if (tab !== 'change' || !resultId || imagery) return
    const ctl = new AbortController()
    getImageryYears(resultId, ctl.signal).then((r) => {
      setImagery({ years: r.years, compared: r.compared })
      setPair(r.compared ?? [r.years[0], r.years.at(-1)])
    }).catch(() => { if (!ctl.signal.aborted) setImagery({ years: [], compared: null, failed: true }) })
    return () => ctl.abort()
  }, [tab, resultId, imagery])

  // Pictures for the two chosen years, each fetched once per result.
  const urls = useRef([])
  const asked = useRef(new Set())
  useEffect(() => {
    if (!resultId || !pair) return
    for (const y of pair) {
      if (asked.current.has(y)) continue
      asked.current.add(y)
      setImgs((s) => ({ ...s, [y]: { state: 'loading' } }))
      getImageryYear(resultId, y).then((url) => {
        urls.current.push(url)
        setImgs((s) => ({ ...s, [y]: { state: 'ready', url } }))
      }).catch((e) => setImgs((s) => ({ ...s, [y]: { state: e instanceof ApiError && e.status === 404 ? 'missing' : 'error' } })))
    }
  }, [resultId, pair])
  useEffect(() => () => {
    urls.current.forEach((u) => URL.revokeObjectURL(u))
    urls.current = []; asked.current = new Set(); setImgs({})
  }, [resultId])

  // Hovering a changed cell: a hit test in the overlay's own square.
  useEffect(() => {
    if (!map || tab !== 'change' || !changeCells || !changeBbox) return
    const u = toUnit(changeBbox)
    const move = (e) => {
      hx.set(e.originalEvent.clientX + 16)
      hy.set(e.originalEvent.clientY + 16)
      const c = cellAt(changeCells, u([e.lngLat.lng, e.lngLat.lat]))
      setChangeHover((h) => (h?.id === c?.id ? h : c))
    }
    const out = () => setChangeHover(null)
    map.on('mousemove', move)
    map.on('mouseout', out)
    return () => { map.off('mousemove', move); map.off('mouseout', out); out() }
  }, [map, tab, changeCells, changeBbox, hx, hy])

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

  const report = resultId ? reportHref(resultId, place?.name) : null
  const actions = useMemo(() => [
    { id: 'search', label: 'Search a place', icon: MagnifyingGlass, kbd: '/', run: () => setTimeout(() => searchInput.current?.focus(), 0) },
    { id: 'rect', label: 'Draw a rectangle', icon: Square, run: () => setDrawMode('rect') },
    { id: 'lasso', label: 'Draw freehand', icon: Lasso, run: () => setDrawMode('lasso') },
    { id: 'point', label: 'Click a point for a fixed box', icon: Crosshair, run: () => setDrawMode('point') },
    { id: 'view', label: 'Use the area in view', icon: FrameCorners, disabled: !map, run: useView },
    { id: 'analyse', label: 'Analyse this area', icon: Play, disabled: !bbox || !!jobLive, run: analyse },
    ...TABS.map((t) => ({ id: `tab-${t.id}`, label: `Show ${t.label}`, icon: t.icon, kbd: t.key, run: () => setTab(t.id) })),
    { id: 'report', label: 'Open the area report', icon: FileText, disabled: !report, run: () => window.open(report, '_blank', 'noopener') },
    { id: 'panel', label: panelOpen ? 'Hide the panel' : 'Show the panel', icon: SidebarSimple, run: () => setPanelOpen((o) => !o) },
    { id: '3d', label: tilted ? 'Flatten the map' : 'Tilt the map to 3D', icon: Cube, disabled: !map, run: toggle3d },
    { id: 'clear', label: 'Clear the area', icon: X, kbd: 'Esc', disabled: !bbox, run: clearArea },
    { id: 'globe', label: 'Back to the globe', icon: Globe, run: backToGlobe },
    { id: 'basemap', label: basemap === 'satellite' ? 'Show the dark map' : 'Show satellite imagery', icon: basemap === 'satellite' ? MapTrifold : GlobeHemisphereWest,
      run: () => chooseBasemap(basemap === 'satellite' ? 'dark' : 'satellite') },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [bbox, jobLive, analyse, panelOpen, tilted, map, backToGlobe, useView, basemap, chooseBasemap, clearArea, report])

  const measuredChoices = Object.entries(outputs.fractions ?? {})
    .filter(([, o]) => o?.status === 'available').map(([k]) => k)
  const fRows = useMemo(() => floodRows(outputs.susceptibility), [outputs.susceptibility])
  const analysedPair = chRows.find((r) => r.key === changeFraction)?.years ?? imagery?.compared ?? null
  const imgStatus = Object.fromEntries(Object.entries(imgs).map(([y, v]) => [y, v.state]))
  const panelT = reduce ? { duration: motion.reduced.duration } : motion.spring
  const tabLabel = TABS.find((t) => t.id === tab).label

  // The map's dock for the current tab: floating on a wide screen, inside
  // the sheet on a phone.
  let dock = null
  if (tab === 'ground' && features && measuredChoices.length > 0) {
    dock = <Legend fraction={fraction} output={outputs.fractions?.[fraction]} choices={measuredChoices}
      onChoose={setFraction} footprints={tilted ? buildings : 'none'} />
  } else if (tab === 'flood' && features && floodLayer) {
    dock = <FloodLegend rows={fRows} layerKey={floodLayer} onLayer={setFloodLayer} />
  } else if (tab === 'change' && resultId && changeFraction && pair) {
    dock = <ChangeDock choices={changeChoices} fraction={changeFraction} onFraction={setChangeFraction}
      years={imagery?.years} pair={pair} compared={imagery?.compared} status={imgStatus}
      onPair={setPair} analysedPair={analysedPair} />
  }

  // Mobile sheet: drag the grip up for the full sheet, down to peek or hide.
  const grip = useRef(null)
  const gripDown = (e) => { grip.current = e.clientY; e.currentTarget.setPointerCapture(e.pointerId) }
  const gripUp = (e) => {
    if (grip.current == null) return
    const d = e.clientY - grip.current
    grip.current = null
    if (d < -SHEET_SNAP_PX) setSheet('full')
    else if (d > SHEET_SNAP_PX) { if (sheet === 'full') setSheet('peek'); else setPanelOpen(false) }
    else setSheet((s) => (s === 'full' ? 'peek' : 'full'))
  }

  const tabBody = {
    ground: <GroundPanel job={job} fraction={fraction} onFraction={setFraction}
      cell={cell} onCloseCell={closeCell} cellsNote={cellsNote} />,
    flood: <FloodPanel job={job} layerKey={floodLayer} onLayer={setFloodLayer} wards={wards} />,
    change: <ChangePanel job={job} fraction={changeFraction} onFraction={setChangeFraction}
      cellsNote={changeNote ?? (imagery?.failed ? 'The before and after pictures could not be listed. Reload the page to try again.' : null)} />,
  }[tab]

  return (
    <div className="app">
      <h1 className="sr-only">GeoWatch</h1>
      <MapView onReady={setMap} spinning={!bbox && !drawMode} reducedMotion={reduce} basemap={basemap} />

      {tab === 'change' && map && changeBbox && pair && (
        <SwipeOverlay map={map} bbox={changeBbox} cells={changeCells} fraction={changeFraction}
          before={{ year: pair[0], ...imgs[pair[0]] }} after={{ year: pair[1], ...imgs[pair[1]] }}
          split={split} onSplit={setSplit} hoverId={changeHover?.id} />
      )}

      <div className="top-left">
        <SearchBar inputRef={searchInput} onPick={onPick} drawMode={drawMode} onDraw={setDrawMode} command={searchCmd} />
      </div>

      <nav className="tabs" role="tablist" aria-label="Views">
        {TABS.map((t) => (
          <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} aria-controls="panel"
            className={tab === t.id ? 'on' : ''} onClick={() => { setTab(t.id); if (bbox) setPanelOpen(true) }}>
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
            className={`panel${mobile ? ` sheet sheet-${sheet}` : ''}`}
            initial={reduce ? { opacity: 0 } : mobile ? { y: 48, opacity: 0 } : { x: 32, opacity: 0 }}
            animate={{ x: 0, y: 0, opacity: 1 }}
            exit={reduce ? { opacity: 0 } : mobile ? { y: 48, opacity: 0 } : { x: 32, opacity: 0 }}
            transition={panelT}
          >
            {mobile && (
              <button type="button" className="sheet-grip" aria-label={sheet === 'full' ? 'Shrink the panel' : 'Expand the panel'}
                onPointerDown={gripDown} onPointerUp={gripUp} onPointerCancel={() => { grip.current = null }}>
                <span aria-hidden="true" />
              </button>
            )}
            <button type="button" className="icon-btn panel-hide" aria-label="Hide the panel" onClick={() => setPanelOpen(false)}>
              {mobile ? <CaretDown size={16} /> : <CaretRight size={16} />}
            </button>
            {service === 'down' && (
              <p className="callout callout-warn" role="status">The GeoWatch service is not answering. Search still works; analysis resumes when it is back.</p>
            )}
            {startNote && <p className="callout callout-danger" role="alert">{startNote}</p>}
            <AreaStatus place={place} bbox={bbox} maxKm2={maxKm2} job={job} wards={!job ? wardLayer : null}
              onAnalyse={analyse} onRetry={analyse} onRedraw={() => setDrawMode('rect')} onClear={clearArea}
              reportHref={report} />
            {mobile && dock && <div className="dock-inline">{dock}</div>}
            <AnimatePresence mode="wait" initial={false}>
              <m.div key={tab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: motion.layerCrossfadeMs / 2000 }}>
                {tabBody}
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

      {!mobile && dock}

      <div className="map-tools">
        <div className="seg seg-float" role="radiogroup" aria-label="Base map">
          {[['satellite', 'Satellite'], ['dark', 'Map']].map(([id, label]) => (
            <button key={id} type="button" role="radio" aria-checked={basemap === id} className={basemap === id ? 'on' : ''}
              onClick={() => chooseBasemap(id)}>{label}</button>
          ))}
        </div>
        {bbox && !mobile && (
          <button type="button" className={`chip${tilted ? ' chip-on' : ''}`} aria-pressed={tilted} onClick={toggle3d} disabled={!map}>
            <Cube size={15} aria-hidden="true" /> 3D
          </button>
        )}
      </div>

      <HoverCard cell={cellsShown ? hoverCell : null} keys={measuredChoices} x={hx} y={hy}
        flood={tab === 'flood' ? fRows.find((r) => r.key === floodLayer) : null}
        change={tab === 'change' && changeHover ? { props: changeHover.props, fraction: changeFraction, rows: chRows } : null} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} actions={actions}
        onSearch={(q) => setSearchCmd({ q, n: Date.now() })} />
    </div>
  )
}
