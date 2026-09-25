import { useState, useEffect, useRef, useCallback } from 'react'
import { MapContainer, TileLayer, Rectangle, ImageOverlay, GeoJSON, useMapEvents, useMap, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import {
  TRUST_META, blockFlag, isFlagged, reportApplicability, mechanismRows,
} from './applicability'
import { categoryColor, legendEntries } from './palette'
// Build item 43: API base and credentials now live in ./api, so every request
// is authenticated by construction rather than by remembering. Item 70 put an
// X-API-Key check at the perimeter; this frontend sent no header on any call,
// so every request had been 401ing since that shipped.
import { apiFetch, fetchImageObjectUrl, isKeyMissing } from './api'
import { legacyPipelineNotice } from './legacyPipeline'


/* ============================================================
   DESIGN TOKENS
   ============================================================ */

const FONTS = {
  display: "'Space Grotesk', sans-serif",
  body: "'Inter', sans-serif",
  mono: "'JetBrains Mono', monospace",
}

const C = {
  void: '#0a0a16',
  panel: '#111129',
  panelRaised: '#171736',
  panelDeep: '#0d0d20',
  hairline: '#26264a',
  hairlineBright: '#34345e',
  text: '#f2f1f9',
  textDim: '#a5a3c8',
  textFaint: '#716fa0',
  cyan: '#5fd4ff',
  cyanDim: 'rgba(95,212,255,0.10)',
  amber: '#ffb454',
  amberDim: 'rgba(255,180,84,0.10)',
  violet: '#c3a4ff',
  violetDim: 'rgba(195,164,255,0.10)',
  coral: '#ff8080',
  coralDim: 'rgba(255,128,128,0.10)',
  green: '#5ed99b',
  greenDim: 'rgba(94,217,155,0.10)',
}

const STATUS_META = {
  available:              { label: 'Measured',        color: C.cyan },
  experimental:           { label: 'Experimental',    color: C.amber },
  national_global_context:{ label: 'National scope',  color: C.violet },
  not_calculated:         { label: 'Not yet defined',  color: C.textDim },
  not_applicable:         { label: 'Not applicable',   color: C.textFaint },
  unavailable:            { label: 'Unavailable',      color: C.coral },
  insufficient_evidence:  { label: 'Not enough data',  color: C.coral },
  waived_pending_real_user_validation: { label: 'Validation pending', color: C.amber },
  // C23/C24, build item 42. Distinguishes "there is no exposure product to
  // validate" from "the product passed Gate C". Before item 42 both arrived as
  // an absent field, so the waiver and its own opposite looked identical.
  not_applicable_no_exposure_product: { label: 'No product to validate', color: C.textFaint },
}
function statusMeta(status) {
  return STATUS_META[status] || { label: (status || 'unknown').replace(/_/g, ' '), color: C.textDim }
}
function StatusPill({ status, size = 'sm' }) {
  const m = statusMeta(status)
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontFamily: FONTS.mono, fontSize: size === 'sm' ? 9 : 10.5, letterSpacing: '0.03em',
      color: m.color, background: `${m.color}18`, border: `1px solid ${m.color}44`,
      borderRadius: 20, padding: size === 'sm' ? '2px 8px' : '4px 11px', whiteSpace: 'nowrap',
    }}>
      <span style={{ width: 5, height: 5, borderRadius: 5, background: m.color, flexShrink: 0 }} />
      {m.label}
    </span>
  )
}

const CLASS_COLORS = { very_low: C.green, low: '#9ccc65', moderate: C.amber, high: '#ff8a65', very_high: C.coral, unknown: C.textDim }

// C31 / build item 43: the CAT_COLORS literal that used to live here is gone.
// It was 0 of 8 in agreement with ingestion/inference.py's CATEGORY_COLORS_RGB,
// on the authority of a Python comment claiming they must match exactly.
// Colours now come from result.landcover.palette via ./palette — there is no
// palette on this side any more, so there is nothing left to drift.
// CAT_LABELS below is display text, not colour, and stays.
const CAT_LABELS = {
  dense_informal_roofing: 'Dense informal roofing', sparse_informal_roofing: 'Sparse informal roofing',
  unpaved_dirt_road: 'Unpaved dirt road', paved_road: 'Paved road', open_drainage_channel: 'Open drainage channel',
  standing_water: 'Standing water', vegetation_clearing: 'Vegetation clearing', active_construction: 'Active construction',
  dense_vegetation: 'Dense vegetation', open_waste: 'Open waste', unknown: 'Unknown',
}
const UNPAVED_HIGHWAY_TYPES = new Set(['track', 'path', 'footway', 'bridleway', 'unclassified', 'service', 'living_street', 'steps'])

// Plain-language "what this is" strings, written for a non-technical reader.
const SUSC_INFO = {
  pluvial:      { label: 'Pluvial (rainfall pooling)', what: 'How likely rain falling directly on this area is to pool up faster than it can drain away.' },
  fluvial:      { label: 'Fluvial (river overflow)', what: 'How exposed this area is to a nearby river overflowing its banks.' },
  coastal:      { label: 'Coastal (storm surge / tide)', what: 'How exposed this area is to seawater pushing inland during a storm, based on distance and height above the coast.' },
  flash_flood:  { label: 'Flash flood', what: 'How likely sudden, fast-moving runoff is during a heavy burst of rain, based on slope and terrain.' },
  waterlogging: { label: 'Waterlogging', what: 'How likely water is to sit and build up on the surface for an extended time after rain, rather than draining or evaporating.' },
}

function landcoverImagePath(result) {
  if (!result?.run_id || !result?.landcover?.map_path) return null
  return `/runs/${result.run_id}/${result.landcover.map_path}`
}

/*
 * The landcover PNG is served from the /runs mount, which item 70 put behind
 * the API key. An <img> load cannot carry a custom header, so the bytes are
 * fetched with one and handed to Leaflet as a blob URL instead. See
 * api.js:fetchImageObjectUrl for why the alternatives (key-in-query-string,
 * exempting the mount) were rejected.
 */
function useAuthedImage(path) {
  const [objectUrl, setObjectUrl] = useState(null)
  useEffect(() => {
    if (!path) { setObjectUrl(null); return }
    let cancelled = false
    let created = null
    fetchImageObjectUrl(path)
      .then(url => {
        if (cancelled) { URL.revokeObjectURL(url); return }
        created = url
        setObjectUrl(url)
      })
      .catch(() => { if (!cancelled) setObjectUrl(null) })
    return () => {
      cancelled = true
      // Revoke on unmount or path change, or every re-render leaks a blob.
      if (created) URL.revokeObjectURL(created)
    }
  }, [path])
  return objectUrl
}
function fmtNum(n, digits = 0) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: digits })
}
function fmtPct(n, digits = 1) {
  if (n === null || n === undefined) return '—'
  return `${Number(n).toFixed(digits)}%`
}

/* ============================================================
   MAP HELPERS
   ============================================================ */

function DragToggle({ drawing }) {
  const map = useMap()
  useEffect(() => { drawing ? map.dragging.disable() : map.dragging.enable() }, [drawing, map])
  return null
}
function MapRecenter({ bbox }) {
  const map = useMap()
  const prevKeyRef = useRef(null)
  useEffect(() => {
    if (!bbox) return
    const key = `${bbox.west},${bbox.south},${bbox.east},${bbox.north}`
    if (prevKeyRef.current === key) return
    prevKeyRef.current = key
    map.fitBounds([[bbox.south, bbox.west], [bbox.north, bbox.east]], { padding: [40, 40], maxZoom: 17 })
  }, [bbox, map])
  return null
}
function AOIDrawer({ onBboxChange, bbox, drawing }) {
  const startRef = useRef(null)
  const [current, setCurrent] = useState(null)
  useMapEvents({
    mousedown(e) { if (!drawing) return; startRef.current = e.latlng; setCurrent(null) },
    mousemove(e) { if (!drawing || !startRef.current) return; setCurrent(e.latlng) },
    mouseup(e) {
      if (!drawing || !startRef.current) return
      const s = startRef.current, end = e.latlng
      onBboxChange({ west: Math.min(s.lng, end.lng), east: Math.max(s.lng, end.lng), south: Math.min(s.lat, end.lat), north: Math.max(s.lat, end.lat) })
      startRef.current = null; setCurrent(null)
    },
  })
  const drawBounds = current && startRef.current
    ? [[Math.min(startRef.current.lat, current.lat), Math.min(startRef.current.lng, current.lng)], [Math.max(startRef.current.lat, current.lat), Math.max(startRef.current.lng, current.lng)]]
    : null
  return (
    <>
      {drawBounds && <Rectangle bounds={drawBounds} pathOptions={{ color: C.cyan, weight: 2, fillOpacity: 0.1, dashArray: '6 3' }} />}
      {bbox && (
        <Rectangle bounds={[[bbox.south, bbox.west], [bbox.north, bbox.east]]} pathOptions={{ color: C.cyan, weight: 2, fillOpacity: 0.06 }}>
          <Tooltip permanent direction="top" offset={[0, -4]}><span style={{ fontFamily: FONTS.mono, fontSize: 10, color: C.cyan }}>AOI selected</span></Tooltip>
        </Rectangle>
      )}
    </>
  )
}
function LandcoverOverlay({ imageUrl, bbox, opacity }) {
  if (!imageUrl || !bbox) return null
  return <ImageOverlay url={imageUrl} bounds={[[bbox.south, bbox.west], [bbox.north, bbox.east]]} opacity={opacity} />
}
function OSMVectorLayer({ runId, visible }) {
  const [roads, setRoads] = useState(null)
  const [waterways, setWaterways] = useState(null)
  useEffect(() => {
    setRoads(null); setWaterways(null)
    if (!runId) return
    apiFetch(`/runs/${runId}/osm/roads.geojson`).then(r => r.ok ? r.json() : null).then(setRoads).catch(() => setRoads(null))
    apiFetch(`/runs/${runId}/osm/waterways.geojson`).then(r => r.ok ? r.json() : null).then(setWaterways).catch(() => setWaterways(null))
  }, [runId])
  if (!visible) return null
  const roadStyle = (f) => { const u = UNPAVED_HIGHWAY_TYPES.has(f?.properties?.highway); return { color: u ? '#c89858' : '#d8d8f0', weight: u ? 1.5 : 2, opacity: 0.9, dashArray: u ? '4 3' : null } }
  return (
    <>
      {roads && <GeoJSON key={`roads-${runId}`} data={roads} style={roadStyle} onEachFeature={(f, l) => l.bindTooltip(`${(f?.properties?.highway || 'road').replace(/_/g, ' ')}`, { sticky: true, className: 'gw-vector-tooltip' })} />}
      {waterways && <GeoJSON key={`waterways-${runId}`} data={waterways} style={{ color: '#5aa8f0', weight: 2, opacity: 0.9 }} onEachFeature={(f, l) => l.bindTooltip(`${(f?.properties?.type || 'waterway').replace(/_/g, ' ')}`, { sticky: true, className: 'gw-vector-tooltip' })} />}
    </>
  )
}
// `colorFor` is passed in rather than the whole result: these components only
// need "category -> colour", and handing them the resolver keeps them unable to
// reach for a palette of their own.
function SegmentOverlays({ segments, bbox, onSelect, selected, tileWidth, tileHeight, colorFor }) {
  if (!segments || !bbox) return null
  const lonPerPx = (bbox.east - bbox.west) / tileWidth, latPerPx = (bbox.north - bbox.south) / tileHeight
  return segments.map(seg => {
    const [px, py, pw, ph] = seg.bbox
    const west = bbox.west + px * lonPerPx, east = bbox.west + (px + pw) * lonPerPx
    const north = bbox.north - py * latPerPx, south = bbox.north - (py + ph) * latPerPx
    const color = colorFor(seg.dominant_landcover_category)
    const isSelected = selected?.segment_id === seg.segment_id
    const label = CAT_LABELS[seg.dominant_landcover_category] || seg.dominant_landcover_category
    return (
      <Rectangle key={seg.segment_id} bounds={[[south, west], [north, east]]}
        pathOptions={{ color: isSelected ? '#ffffff' : color, weight: isSelected ? 2.5 : 1, fillColor: color, fillOpacity: isSelected ? 0.45 : 0.05 }}
        eventHandlers={{ click: () => onSelect(seg) }}>
        <Tooltip sticky direction="top" opacity={0.95} className="gw-vector-tooltip">
          <span style={{ fontFamily: FONTS.mono, fontSize: 10 }}>{label} · {seg.landcover_purity_pct != null ? `${seg.landcover_purity_pct.toFixed(1)}%` : '—'}</span>
        </Tooltip>
      </Rectangle>
    )
  })
}

/* ============================================================
   PRIMITIVES
   ============================================================ */

function Explain({ children }) {
  // High-contrast plain-language sentence — always readable regardless
  // of the card's accent color, per the contrast fix.
  return <p style={{ fontFamily: FONTS.body, fontSize: 13, color: C.text, lineHeight: 1.65, margin: '0 0 12px' }}>{children}</p>
}
function Small({ children }) {
  return <p style={{ fontFamily: FONTS.body, fontSize: 12, color: C.textDim, lineHeight: 1.6, margin: 0 }}>{children}</p>
}
function Metric({ label, value, unit, accent, big }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontFamily: FONTS.body, fontSize: 10.5, color: C.textDim, letterSpacing: '0.05em', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ fontFamily: FONTS.mono, fontSize: big ? 26 : 16, color: accent || C.text, fontWeight: 700, lineHeight: 1.1 }}>
        {value}{unit && <span style={{ fontSize: big ? 14 : 11, color: C.textDim, fontWeight: 500, marginLeft: 4 }}>{unit}</span>}
      </span>
    </div>
  )
}
function Disclosure({ label = 'Show raw scores', children }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ marginTop: 10 }}>
      <button onClick={() => setOpen(o => !o)} style={{
        background: 'none', border: 'none', cursor: 'pointer', padding: 0,
        fontFamily: FONTS.mono, fontSize: 10.5, color: C.cyan, display: 'flex', alignItems: 'center', gap: 5,
      }}>
        <span style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s', display: 'inline-block' }}>›</span>
        {open ? 'Hide raw scores' : label}
      </button>
      {open && <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.hairline}` }}>{children}</div>}
    </div>
  )
}
function CaveatList({ items }) {
  if (!items || items.length === 0) return null
  return (
    <div style={{ marginTop: 12, background: C.panelDeep, border: `1px solid ${C.hairline}`, borderRadius: 8, padding: '10px 12px' }}>
      <div style={{ fontFamily: FONTS.body, fontSize: 9.5, color: C.textDim, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 7, fontWeight: 600 }}>
        Good to know
      </div>
      <ul style={{ margin: 0, paddingLeft: 16, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.slice(0, 5).map((it, i) => (
          <li key={i} style={{ fontFamily: FONTS.body, fontSize: 11.5, color: C.textDim, lineHeight: 1.55 }}>{it}</li>
        ))}
      </ul>
    </div>
  )
}
function ReportCard({ title, status, children, style }) {
  return (
    <div style={{ background: C.panelRaised, border: `1px solid ${C.hairline}`, borderRadius: 12, padding: '18px 20px', marginBottom: 14, ...style }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ fontFamily: FONTS.display, fontSize: 15, fontWeight: 600, color: C.text }}>{title}</div>
        {status && <StatusPill status={status} />}
      </div>
      {children}
    </div>
  )
}

/* ============================================================
   GATE C WAIVER — C23 / C24 / build item 42
   ============================================================ */

// Plain-language reading of exposure/compute.py's GATE_C_STATUS constants.
// Gate C is "is this output actually useful and correctly understood by a real
// user" -- waived, never passed. PROJECT_GATES.md holds the reasoning.
const GATE_C_NOTES = {
  waived_pending_real_user_validation:
    '(not yet reviewed by a real user for decision-support use)',
  not_applicable_no_exposure_product:
    '(nothing was computed here, so there is no product to validate)',
}

/*
 * The susceptibility panel's caveat span, lifted verbatim.
 *
 * C24's point was that the discipline already existed in this file and simply
 * had not been applied to exposure: SecHazard renders
 *
 *     {s.status === 'experimental' && <span style={{ fontFamily: FONTS.body,
 *       fontSize: 11, color: C.textDim }}>(early-stage estimate, not a
 *       certified hazard map)</span>}
 *
 * so item 42 says copy that exact pattern rather than invent another. The style
 * object below is that one, unchanged. It is a component only so the three
 * sites that need it stay identical -- three hand-copies of one rule is S3
 * ("cross-boundary contracts enforced only by prose"), which is how C31 ended
 * up with 0 of 8 categories matching.
 */
function GateCNote({ status }) {
  const note = GATE_C_NOTES[status]
  if (!note) return null
  return <span style={{ fontFamily: FONTS.body, fontSize: 11, color: C.textDim }}>{note}</span>
}

/* ============================================================
   APPLICABILITY — C32 / build item 41
   ============================================================ */

// Trust levels get their own palette rather than reusing STATUS_META. The two
// answer different questions and must not be confusable: STATUS_META describes
// RELEVANCE and completeness ("Not applicable", "Not yet defined"), while this
// describes whether a number can be BELIEVED. The backend keeps the same two
// axes apart for the same reason -- collapsing them would let "there is no
// coastline here" read as "this cannot be trusted".
const TRUST_COLORS = {
  out_of_distribution: C.coral,
  degraded: C.amber,
  in_distribution: C.green,
  unknown: C.textFaint,
}

function TrustPill({ trust, size = 'sm' }) {
  const color = TRUST_COLORS[trust] || C.textFaint
  const label = TRUST_META[trust]?.label || 'Not checked'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontFamily: FONTS.mono, fontSize: size === 'sm' ? 9 : 10.5, letterSpacing: '0.03em',
      color, background: `${color}18`, border: `1px solid ${color}44`,
      borderRadius: 20, padding: size === 'sm' ? '2px 8px' : '4px 11px', whiteSpace: 'nowrap',
    }}>
      <span style={{ width: 5, height: 5, borderRadius: 5, background: color, flexShrink: 0 }} />
      {label}
    </span>
  )
}

/*
 * The banner. Item 41's acceptance is that an AOI tripping out_of_distribution
 * produces a UI the user cannot miss, so this sits above every section, spans
 * the column, and carries the severity colour.
 *
 * It is loud ONLY when there is something to be loud about. On a clean run it
 * collapses to one quiet confirmation line. A banner that shouts on every run
 * trains readers to scroll past it, which is the same mechanism that made
 * C33's "0.0%" meaningless -- a signal that always fires carries no
 * information. The quiet line still appears, because silence would leave a
 * reader unable to tell "checked and fine" from "never checked".
 */
function ApplicabilityBanner({ result, onJump }) {
  const app = reportApplicability(result)
  const color = TRUST_COLORS[app.trust] || C.textFaint

  if (!app.isAlert) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: 9, marginBottom: 14,
        padding: '9px 13px', borderRadius: 9,
        background: C.panelDeep, border: `1px solid ${C.hairline}`,
      }}>
        <span style={{ width: 6, height: 6, borderRadius: 6, background: color, flexShrink: 0 }} />
        <span style={{ fontFamily: FONTS.body, fontSize: 11.5, color: C.textDim }}>
          {app.meta.headline}
        </span>
        <button onClick={() => onJump?.('reliability')} style={{
          marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer',
          fontFamily: FONTS.body, fontSize: 11, color: C.textFaint, textDecoration: 'underline',
        }}>Reliability detail</button>
      </div>
    )
  }

  return (
    <div role="alert" style={{
      marginBottom: 18, borderRadius: 12, overflow: 'hidden',
      background: app.trust === 'out_of_distribution' ? C.coralDim : C.amberDim,
      border: `1px solid ${color}`,
      boxShadow: `0 0 0 1px ${color}22, 0 6px 24px -12px ${color}66`,
    }}>
      <div style={{ height: 3, background: color }} />
      <div style={{ padding: '15px 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 9 }}>
          <span style={{
            fontFamily: FONTS.mono, fontSize: 9.5, letterSpacing: '0.10em',
            textTransform: 'uppercase', fontWeight: 700, color,
          }}>
            {app.trust === 'out_of_distribution' ? 'Reliability warning' : 'Reliability caution'}
          </span>
          <TrustPill trust={app.trust} />
        </div>

        <div style={{
          fontFamily: FONTS.display, fontSize: 16.5, fontWeight: 700,
          color: C.text, lineHeight: 1.35, marginBottom: 8,
        }}>
          {app.meta.headline}
        </div>

        <div style={{ fontFamily: FONTS.body, fontSize: 12.5, color: C.textDim, lineHeight: 1.6 }}>
          {app.meta.plain}
        </div>

        {app.reason && (
          <div style={{
            marginTop: 11, padding: '9px 11px', borderRadius: 7,
            background: 'rgba(0,0,0,0.22)', border: `1px solid ${color}33`,
            fontFamily: FONTS.mono, fontSize: 10.5, color: C.textDim, lineHeight: 1.55,
          }}>
            {app.reason}
          </div>
        )}

        {/* Naming what IS and IS NOT affected is the point of item 40's
            dependency chain. "Everything is suspect" would be both false and
            useless -- fluvial reads MERIT Hydro, coastal a shoreline dataset,
            flash flood slope and catchment; none touches the semantic model. */}
        {app.affectedCount > 0 && (
          <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
            <span style={{ fontFamily: FONTS.body, fontSize: 10.5, color: C.textFaint, marginRight: 2 }}>
              Affected ({app.affectedCount}):
            </span>
            {app.affected.map(({ group, key }) => (
              <span key={`${group}-${key}`} style={{
                fontFamily: FONTS.mono, fontSize: 9.5, color, background: `${color}14`,
                border: `1px solid ${color}33`, borderRadius: 5, padding: '2px 7px',
              }}>{group}/{key.replace(/_/g, ' ')}</span>
            ))}
          </div>
        )}

        {app.unaffected.length > 0 && (
          <div style={{ marginTop: 7, fontFamily: FONTS.body, fontSize: 10.5, color: C.textFaint, lineHeight: 1.5 }}>
            Not affected — these read independent data sources:{' '}
            {app.unaffected.map(u => `${u.group}/${u.key.replace(/_/g, ' ')}`).join(', ')}.
          </div>
        )}

        <button onClick={() => onJump?.('reliability')} style={{
          marginTop: 13, background: `${color}1a`, border: `1px solid ${color}55`,
          color, borderRadius: 7, padding: '7px 13px', cursor: 'pointer',
          fontFamily: FONTS.body, fontSize: 11.5, fontWeight: 600,
        }}>What this means →</button>
      </div>
    </div>
  )
}

/*
 * Inline per-block marker. Item 40 put a flag on every susceptibility,
 * exposure and risk block; this is what reads it where the number actually
 * appears. "Not a buried field" has to mean the warning travels with the value,
 * not only that a banner exists somewhere above.
 */
function BlockTrustNote({ block }) {
  const flag = blockFlag(block)
  if (!flag) return null

  if (flag.gate === 'not_wired') {
    return (
      <div style={{ marginTop: 9, fontFamily: FONTS.mono, fontSize: 10, color: C.textFaint }}>
        Reliability not checked for this value.
      </div>
    )
  }
  if (!isFlagged(block)) return null

  const color = flag.out_of_distribution ? C.coral : C.amber
  const via = (flag.degraded_by || []).join(', ').replace(/_/g, ' ')
  return (
    <div style={{
      marginTop: 10, padding: '8px 10px', borderRadius: 7,
      background: `${color}12`, border: `1px solid ${color}3a`,
      display: 'flex', gap: 8, alignItems: 'flex-start',
    }}>
      <span style={{ color, fontSize: 12, lineHeight: 1.2, flexShrink: 0 }}>▲</span>
      <span style={{ fontFamily: FONTS.body, fontSize: 11, color: C.textDim, lineHeight: 1.5 }}>
        {flag.out_of_distribution
          ? 'This number is derived from land-cover output that is currently unreliable'
          : 'This number is derived from land-cover output that is weaker than usual'}
        {via ? <> — via <span style={{ fontFamily: FONTS.mono, fontSize: 10, color }}>{via}</span></> : null}.
        {' '}It is shown rather than withheld so the value and its caveat stay together.
      </span>
    </div>
  )
}

function SecReliability({ result }) {
  const app = reportApplicability(result)
  const rows = mechanismRows(result)
  const color = TRUST_COLORS[app.trust] || C.textFaint

  return (
    <section id="reliability">
      <ReportCard
        title="Can these results be trusted here"
        style={app.isAlert ? { background: app.trust === 'out_of_distribution' ? C.coralDim : C.amberDim, border: `1px solid ${color}55` } : undefined}
      >
        <div style={{ marginBottom: 10 }}><TrustPill trust={app.trust} size="md" /></div>
        <Explain>{app.meta.plain}</Explain>

        {!app.hasBlock && (
          <CaveatList items={[
            'This run carries no applicability block at all, so no reliability ' +
            'verdict was recorded. Treat that as "not checked" rather than ' +
            '"checked and fine" — it most likely predates reliability gating.',
          ]} />
        )}

        {app.reason && (
          <div style={{
            marginTop: 10, padding: '10px 12px', borderRadius: 8,
            background: C.panelDeep, border: `1px solid ${C.hairline}`,
            fontFamily: FONTS.mono, fontSize: 10.5, color: C.textDim, lineHeight: 1.6,
          }}>{app.reason}</div>
        )}
      </ReportCard>

      {rows.length > 0 && (
        <ReportCard title="Verdict by mechanism">
          <Explain>
            Each flood mechanism is judged separately, because they read different data.
            A problem with the land-cover model does not implicate a mechanism that never uses it.
          </Explain>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1, marginTop: 4 }}>
            {rows.map(r => (
              <div key={r.key} style={{
                display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 11px',
                background: r.isRoot ? C.panelDeep : 'transparent',
                borderRadius: 7, border: r.isRoot ? `1px solid ${color}33` : `1px solid transparent`,
              }}>
                <div style={{ minWidth: 168 }}>
                  <div style={{ fontFamily: FONTS.body, fontSize: 12, color: C.text, fontWeight: r.isRoot ? 600 : 500 }}>
                    {r.isRoot ? 'Land-cover model' : (SUSC_INFO[r.key]?.label || r.key.replace(/_/g, ' '))}
                  </div>
                  {r.isRoot && (
                    <div style={{ fontFamily: FONTS.body, fontSize: 10, color: C.textFaint, marginTop: 2 }}>
                      Root of the chain — everything derived from it inherits this
                    </div>
                  )}
                </div>
                <div style={{ flexShrink: 0 }}>
                  {r.isRoot ? <TrustPill trust={r.status} /> : <StatusPill status={r.status} />}
                </div>
                {r.reason && (
                  <div style={{ fontFamily: FONTS.body, fontSize: 11, color: C.textFaint, lineHeight: 1.5 }}>
                    {r.reason}
                  </div>
                )}
              </div>
            ))}
          </div>
        </ReportCard>
      )}

      {(app.affected.length > 0 || app.ungated.length > 0) && (
        <ReportCard title="What this changes downstream">
          {app.affected.length > 0 && (
            <>
              <Explain>
                These {app.affected.length} values are computed from the land-cover model, so they
                carry its verdict. They are still shown, with the reason attached, rather than hidden.
              </Explain>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}>
                {app.affected.map(({ group, key, flag }) => (
                  <span key={`${group}-${key}`} style={{
                    fontFamily: FONTS.mono, fontSize: 9.5,
                    color: flag.out_of_distribution ? C.coral : C.amber,
                    background: `${flag.out_of_distribution ? C.coral : C.amber}14`,
                    border: `1px solid ${flag.out_of_distribution ? C.coral : C.amber}33`,
                    borderRadius: 5, padding: '3px 8px',
                  }}>{group}/{key.replace(/_/g, ' ')}</span>
                ))}
              </div>
            </>
          )}
          {app.unaffected.length > 0 && (
            <Small>
              Unaffected: {app.unaffected.map(u => `${u.group}/${u.key.replace(/_/g, ' ')}`).join(', ')} —
              these read river, shoreline and terrain data, not the land-cover model.
            </Small>
          )}
          {app.ungated.length > 0 && (
            <CaveatList items={[
              `${app.ungated.length} value(s) carry no reliability flag at all: ` +
              app.ungated.map(u => `${u.group}/${u.key}`).join(', ') +
              '. Unflagged means nobody checked, not that the value is sound.',
            ]} />
          )}
        </ReportCard>
      )}
    </section>
  )
}

/* ============================================================
   REPORT SECTIONS
   ============================================================ */

function SecOverview({ result }) {
  const summary = result?.summary || {}
  const landcover = result?.landcover || {}
  const provenance = landcover.model_provenance || {}
  const informalCount = (result?.segments || []).filter(s => s.dominant_landcover_category === 'dense_informal_roofing' || s.dominant_landcover_category === 'sparse_informal_roofing').length

  return (
    <section id="overview">
      <ReportCard title="What this run found">
        <Explain>
          This scan split the area into {fmtNum(summary.total_segments)} segments and matched each one to a land-cover type.
          The most common type here was <b style={{ color: categoryColor(result, summary.dominant_category) }}>{(summary.dominant_category || '—').replace(/_/g, ' ')}</b>.
        </Explain>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 18 }}>
          <Metric label="Segments found" value={fmtNum(summary.total_segments)} accent={C.cyan} big />
          <Metric label="Informal roofing" value={fmtNum(informalCount)} accent={C.amber} big />
          <Metric label="Standing water" value={fmtNum(summary.standing_water_segment_count ?? 0)} accent={C.cyan} big />
          <Metric label="Unclear pixels" value={fmtPct(landcover.unknown_pct)} accent={landcover.unknown_pct > 15 ? C.coral : C.textDim} big />
        </div>
        <Small>&ldquo;Unclear pixels&rdquo; are spots the model wasn&rsquo;t confident enough to label at all, rather than a wrong guess.</Small>
      </ReportCard>

      <ReportCard title="Satellite imagery used">
        {result?.imagery ? (
          <>
            <Explain>
              This analysis is built from <b style={{ color: C.text }}>{result.imagery.source_image_count}</b> Sentinel-2 satellite images taken between{' '}
              {result.imagery.requested_period?.start} and {result.imagery.requested_period?.end}, combined into a single clearer picture.
            </Explain>
            {result.observation_quality?.status === 'available' && (
              <div style={{ display: 'flex', gap: 24, marginTop: 4 }}>
                <Metric label="Clear view" value={fmtPct(result.observation_quality.valid_observation_pct)} accent={C.green} />
                <Metric label="Blocked by cloud" value={fmtPct(result.observation_quality.cloud_pct)} accent={C.textDim} />
                <Metric label="Blocked by shadow" value={fmtPct(result.observation_quality.cloud_shadow_pct)} accent={C.textDim} />
              </div>
            )}
          </>
        ) : <Explain>No imagery information was recorded for this run.</Explain>}
      </ReportCard>

      <ReportCard title="How reliable is the model" status={provenance.loco_mean_miou != null ? 'available' : 'unavailable'}>
        {provenance.loco_mean_miou != null ? (
          <>
            <Explain>
              Before trusting this model on a new city, it was tested by hiding one of its 11 training cities at a time and checking how well it still worked there.
              On average it scored <b style={{ color: C.cyan }}>{provenance.loco_mean_miou.toFixed(2)} out of 1.0</b> on cities it had never seen. That is the honest
              measure of how well it should generalize to a brand-new place like this one, not just how well it memorized its training data.
            </Explain>
            <Disclosure>
              <div style={{ display: 'flex', gap: 20 }}>
                <Metric label="Mean score" value={provenance.loco_mean_miou.toFixed(4)} />
                {provenance.loco_std_miou != null && <Metric label="Variation" value={`± ${provenance.loco_std_miou.toFixed(4)}`} />}
                {provenance.loco_n_folds != null && <Metric label="Cities tested" value={provenance.loco_n_folds} />}
              </div>
              <Small style={{ marginTop: 8 }}>Architecture: {provenance.architecture || 'GeoWatchResNetSeg'}</Small>
            </Disclosure>
          </>
        ) : <Explain>No reliability testing data was recorded for this run.</Explain>}
      </ReportCard>
    </section>
  )
}

function SecLandcover({ result, showLandcover, setShowLandcover, landcoverOpacity, setLandcoverOpacity, showRoadsVector, setShowRoadsVector }) {
  const landcover = result?.landcover || {}
  const areaPct = landcover.category_area_pct || {}
  // C31 / item 43: the legend is built from the palette the backend emitted
  // with THIS run, so changing a colour in configs/palette.py changes what is
  // drawn here with no edit to this file. That is the item's acceptance test.
  const entries = legendEntries(result).map(e => [e.category, e.color])

  return (
    <section id="landcover">
      <ReportCard title="What covers the ground here">
        <Explain>
          Every part of the area was matched to one of these categories based on what the satellite images show. Percentages are share of the total area.
        </Explain>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px 24px' }}>
          {entries.map(([key, color]) => {
            const pct = areaPct?.[key]
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <div style={{ width: 11, height: 11, borderRadius: 3, background: color, flexShrink: 0 }} />
                <span style={{ fontFamily: FONTS.body, fontSize: 12.5, color: pct ? C.text : C.textFaint, flex: 1 }}>{CAT_LABELS[key]}</span>
                <span style={{ fontFamily: FONTS.mono, fontSize: 12, color: pct ? color : C.textFaint }}>{pct ? fmtPct(pct) : '0.0%'}</span>
              </div>
            )
          })}
          {landcover.unknown_pct != null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <div style={{ width: 11, height: 11, borderRadius: 3, background: C.textFaint, flexShrink: 0 }} />
              <span style={{ fontFamily: FONTS.body, fontSize: 12.5, color: C.textDim, flex: 1 }}>Unclear</span>
              <span style={{ fontFamily: FONTS.mono, fontSize: 12, color: C.textFaint }}>{fmtPct(landcover.unknown_pct)}</span>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 20, marginTop: 16, paddingTop: 14, borderTop: `1px solid ${C.hairline}` }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={showLandcover} onChange={e => setShowLandcover(e.target.checked)} />
            <span style={{ fontFamily: FONTS.body, fontSize: 11.5, color: C.textDim }}>Show colored overlay on map</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={showRoadsVector} onChange={e => setShowRoadsVector(e.target.checked)} />
            <span style={{ fontFamily: FONTS.body, fontSize: 11.5, color: C.textDim }}>Show roads &amp; waterways on map</span>
          </label>
        </div>
        {showLandcover && (
          <div style={{ marginTop: 10 }}>
            <Small>Overlay opacity</Small>
            <input type="range" min={0.2} max={1} step={0.05} value={landcoverOpacity} onChange={e => setLandcoverOpacity(parseFloat(e.target.value))} style={{ width: '100%', accentColor: C.cyan }} />
          </div>
        )}
      </ReportCard>

      <ReportCard title="Roads and waterways">
        <Explain>
          These are real, mapped roads and waterways from OpenStreetMap, not guesses from the satellite image. This matters because the model sometimes confuses
          paved roads with rooftops, so the real road map is used as a cross-check instead of trusting the model's own road guess.
        </Explain>
        {result?.osm_context && (
          <div style={{ display: 'flex', gap: 24 }}>
            <Metric label="Road segments mapped" value={fmtNum(result.osm_context.road_segments)} accent={C.cyan} />
            <Metric label="Waterway features mapped" value={fmtNum(result.osm_context.waterway_features)} accent={C.cyan} />
          </div>
        )}
      </ReportCard>

      <ReportCard title="How much rain soaks in vs. runs off">
        <Explain>
          <b style={{ color: C.amber }}>Impervious</b> is the share of ground that's paved or built over, so rain can't soak in and just runs off the surface instead.{' '}
          <b style={{ color: C.green }}>Infiltration</b> is the share of ground, mostly soil and vegetation, where rain can actually soak in. A higher impervious
          share generally means faster, heavier runoff during rain.
        </Explain>
        <div style={{ display: 'flex', gap: 24 }}>
          <Metric label="Impervious (runs off)" value={fmtPct(result?.hydrological_surfaces?.impervious_fraction_pct)} accent={C.amber} big />
          <Metric label="Infiltration (soaks in)" value={fmtPct(result?.hydrological_surfaces?.infiltration_proxy_pct)} accent={C.green} big />
        </div>
      </ReportCard>
    </section>
  )
}

function SecHazard({ result }) {
  const susceptibility = result?.susceptibility || {}
  const fa = result?.flood_assessment || {}
  const terrain = fa.terrain_context || {}

  return (
    <section id="hazard">
      <ReportCard title="Ground shape and elevation" status={fa.status === 'experimental_screening_only' ? 'experimental' : (fa.status || 'not_calculated')}>
        {fa.status === 'insufficient_evidence' ? (
          <Explain>Elevation data could not be retrieved for this run, so no terrain check was possible.</Explain>
        ) : (
          <>
            <Explain>
              Lower-lying, flatter ground near a river or drainage line tends to collect water faster during heavy rain. These numbers describe how this area's
              elevation compares to its surroundings, an early, rougher signal rather than a precise flood map.
            </Explain>
            <div style={{ display: 'flex', gap: 24 }}>
              {terrain.relative_elevation_proxy?.score != null && <Metric label="Relative elevation" value={terrain.relative_elevation_proxy.score} accent={C.amber} />}
              {terrain.absolute_elevation?.mean_m != null && <Metric label="Average height" value={fmtNum(terrain.absolute_elevation.mean_m, 1)} unit="m" accent={C.cyan} />}
              {result?.terrain_context?.fluvial_hand_context?.mean_hnd_m != null && <Metric label="Height above nearest drainage" value={fmtNum(result.terrain_context.fluvial_hand_context.mean_hnd_m, 2)} unit="m" accent={C.cyan} />}
            </div>
            <CaveatList items={["This elevation reading isn't from bare ground. It's measured from a surface model, so tall buildings can push the number up in dense city areas."]} />
          </>
        )}
      </ReportCard>

      <div style={{ fontFamily: FONTS.body, fontSize: 13, fontWeight: 600, color: C.text, margin: '22px 0 4px' }}>Five ways this area could flood</div>
      <Small>Each type of flooding has a different cause, so they're scored separately rather than combined into one number.</Small>
      <div style={{ height: 12 }} />

      {Object.entries(SUSC_INFO).map(([key, info]) => {
        const s = susceptibility[key]
        if (!s) return null
        const cls = s.aoi_mean_class || 'unknown'
        const color = CLASS_COLORS[cls] || C.textDim
        return (
          <ReportCard key={key} title={info.label} status={s.status}>
            <Explain>{info.what}</Explain>
            {(s.status === 'available' || s.status === 'experimental') ? (
              <>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  <span style={{ fontFamily: FONTS.mono, fontSize: 20, fontWeight: 700, color, textTransform: 'capitalize' }}>{cls.replace(/_/g, ' ')}</span>
                  {s.status === 'experimental' && <span style={{ fontFamily: FONTS.body, fontSize: 11, color: C.textDim }}>(early-stage estimate, not a certified hazard map)</span>}
                </div>
                {s.aoi_mean_score != null && (
                  <Disclosure>
                    <Metric label="Raw score (0 to 1 scale)" value={s.aoi_mean_score.toFixed(3)} />
                  </Disclosure>
                )}
              </>
            ) : (
              <Small>{s.reason || 'Not enough data to score this for this area.'}</Small>
            )}
            {/* C32 / item 41: the warning travels with the number, not only in
                the banner above. A reader who scrolls straight to waterlogging
                must still see that it is derived from unreliable land cover. */}
            <BlockTrustNote block={s} />
          </ReportCard>
        )
      })}
    </section>
  )
}

function SecExposure({ result }) {
  const exposure = result?.exposure
  if (!exposure) return <section id="exposure"><ReportCard title="Who and what is here">No exposure data for this run.</ReportCard></section>
  const layers = exposure.by_evidence_layer || {}
  const layerKeys = Object.keys(layers)
  const [activeLayer, setActiveLayer] = useState(layerKeys[0])
  const layer = layers[activeLayer] || layers[layerKeys[0]]
  if (!layer) return <section id="exposure"><ReportCard title="Who and what is here">No exposure layers available.</ReportCard></section>

  const c = layer.components || {}
  const pop = c.population || {}, builtUp = c.built_up || {}, roads = c.roads || {}, facilities = c.facilities || {}

  return (
    <section id="exposure">
      {/* C24 / item 42: `status=` on ReportCard renders a StatusPill in the
          header -- exactly what SecHazard does with `status={s.status}`. The
          value is read from the layer, never hardcoded; exposure/compute.py's
          GATE_C_STATUS is the single source of truth. */}
      <ReportCard title="Who and what is in this area" status={layer.product_validation_status || 'unavailable'}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8 }}>
          <span style={{ fontFamily: FONTS.body, fontSize: 12, color: C.text, fontWeight: 600 }}>Review status</span>
          <GateCNote status={layer.product_validation_status} />
        </div>
        <Explain>
          Exposure means counting people, buildings, roads and facilities that sit inside this area, if a flood happened. It doesn't mean they will flood or
          be harmed, just that they're physically located here. Pick a flood type below to see the count relevant to that specific risk.
        </Explain>
        {layer.product_validation_status === 'waived_pending_real_user_validation' && (
          <CaveatList items={[
            "These exposure figures have passed their data checks, but no planner, NGO or researcher has yet reviewed whether they are shaped and labelled well enough to actually decide anything with. Treat them as screening context, not as a finished product.",
          ]} />
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 8 }}>
          {layerKeys.map(k => (
            <button key={k} onClick={() => setActiveLayer(k)} style={{
              padding: '6px 12px', borderRadius: 7, cursor: 'pointer', fontFamily: FONTS.body, fontSize: 11.5, fontWeight: 500,
              background: activeLayer === k ? C.cyanDim : 'transparent',
              border: `1px solid ${activeLayer === k ? C.cyan : C.hairline}`,
              color: activeLayer === k ? C.cyan : C.textDim,
            }}>{SUSC_INFO[k]?.label || k.replace(/_/g, ' ')}</button>
          ))}
        </div>
        {layer.intersection_type === 'aoi_total_given_layer_applicability' && (
          <CaveatList items={["These are totals for the whole area, not just the flood-prone parts, because this flood type is currently scored as a single area-wide number rather than mapped spot by spot."]} />
        )}
        {/* C32 / item 41. Note the line above: `intersection_type ===
            'aoi_total_given_layer_applicability'` was the ONLY occurrence of
            the string "applicability" anywhere in src/ before this item — an
            unrelated comparison that made the signal look wired when it was
            not. The real flag is read here. */}
        <BlockTrustNote block={layer} />
      </ReportCard>

      <ReportCard title="Estimated population" status={pop.status || 'unavailable'}>
        {pop.status === 'available' ? (
          <>
            <Explain>An estimate of how many people live in this area, based on population modeling, not a door-to-door census.</Explain>
            <Metric label="Estimated people" value={fmtNum(pop.estimated_population)} accent={C.cyan} big />
            <div style={{ display: 'flex', gap: 24, marginTop: 14 }}>
              <Metric label="Data from year" value={pop.population_source?.population_year ?? '—'} />
              <Metric label="Grid size" value={pop.population_source?.native_resolution_m ? `~${Math.round(pop.population_source.native_resolution_m)}` : '—'} unit="m" />
            </div>
            <CaveatList items={[
              "This is a modeled estimate, not a household count.",
              "The most recent population data available is from 2020, so this may not reflect how many people live here today.",
              "Never treat this as a count of people 'at risk', it's simply who is located in the area.",
            ]} />
          </>
        ) : <Small>{pop.error || 'Population data is unavailable for this run.'}</Small>}
      </ReportCard>

      <ReportCard title="Built-up area" status={builtUp.status || 'not_calculated'}>
        {builtUp.status === 'available' ? (
          <>
            <Explain>Share of this area covered by buildings and paved surfaces, as estimated by the land-cover model.</Explain>
            <Metric label="Built-up share" value={fmtPct(builtUp.geowatch_model_builtup_pct)} accent={C.amber} big />
            <Small style={{ marginTop: 10 }}>
              {builtUp.global_reference_source
                ? `This is cross-checked against an independent global dataset (${builtUp.global_reference_source}), though the two haven't been formally compared yet.`
                : (builtUp.note || 'No independent cross-check dataset was available for this run.')}
            </Small>
          </>
        ) : <Small>Not calculated for this run.</Small>}
      </ReportCard>

      <ReportCard title="Roads in this area" status={roads.status || 'unavailable'}>
        {roads.status === 'available' ? (
          <>
            <Explain>Total length of real, mapped roads inside this area, from OpenStreetMap rather than the model's own guess.</Explain>
            <Metric label="Total road length" value={fmtNum(roads.total_length_km, 1)} unit="km" accent={C.cyan} big />
          </>
        ) : <Small>{roads.error || 'Road data is unavailable for this run.'}</Small>}
      </ReportCard>

      <ReportCard title="Hospitals, clinics and schools" status={facilities.status || 'unavailable'}>
        {facilities.status === 'available' ? (
          <>
            <Explain>Facilities mapped inside this area. This only shows that a facility is located here, not whether it's currently working or affected by anything.</Explain>
            <Metric label="Facilities found" value={fmtNum(facilities.count)} accent={C.cyan} big />
          </>
        ) : <Small>{facilities.error || 'Facilities data is unavailable for this run.'}</Small>}
      </ReportCard>

      <CaveatList items={layer.limitations} />
    </section>
  )
}

function SecVulnerability({ result }) {
  const v = result?.vulnerability
  if (!v) return <section id="vulnerability"><ReportCard title="How prepared is this country">No vulnerability data for this run.</ReportCard></section>

  return (
    <section id="vulnerability">
      <ReportCard title="How prepared is this country for a disaster" status={v.status}>
        {v.status === 'available' ? (
          <>
            <Explain>
              This isn't specific to this exact location. It reflects <b style={{ color: C.text }}>{v.country_lookup?.country_name || v.country_iso3}</b> as a whole,
              since disaster preparedness is measured at the national level.
            </Explain>
            <div style={{ display: 'flex', gap: 28, marginTop: 6 }}>
              <div>
                <Metric label="Vulnerability" value={v.dimensions?.vulnerability?.raw_score} unit="/ 10" accent={C.violet} big />
                <Small style={{ marginTop: 6, maxWidth: 220 }}>How exposed the population is to hardship if a disaster hits. Higher means more vulnerable.</Small>
              </div>
              <div>
                <Metric label="Lack of coping capacity" value={v.dimensions?.lack_of_coping_capacity?.raw_score} unit="/ 10" accent={C.violet} big />
                <Small style={{ marginTop: 6, maxWidth: 220 }}>How much difficulty the country would have responding to and recovering from a disaster. Higher means less capacity to cope.</Small>
              </div>
            </div>
            <Disclosure label="Show data quality details">
              <div style={{ display: 'flex', gap: 20 }}>
                <Metric label="Reliability score" value={v.data_quality?.lack_of_reliability_score?.toFixed?.(2) ?? '—'} />
                <Metric label="Missing indicators" value={v.data_quality?.pct_missing_indicators != null ? fmtPct(v.data_quality.pct_missing_indicators * 100) : '—'} />
              </div>
              <Small style={{ marginTop: 8 }}>Source: {v.source}, {v.source_edition} edition.</Small>
            </Disclosure>
            <CaveatList items={v.limitations} />
          </>
        ) : <Small>{v.reason || 'Vulnerability data is unavailable for this run.'}</Small>}
      </ReportCard>

      <ReportCard title="Why is this the same for the whole country" style={{ background: C.violetDim, border: `1px solid ${C.violet}44` }}>
        <Explain>
          Every area inside the same country gets this exact same score. That's intentional, not a shortcut we're waiting to fix. Guessing how prepared a
          specific neighborhood is from satellite images alone, like assuming denser housing means less prepared, would be an unreliable and potentially
          unfair guess. Using a real, published national statistic instead is more honest, even though it's less locally specific.
        </Explain>
      </ReportCard>
    </section>
  )
}

function SecRisk({ result }) {
  const risk = result?.risk
  if (!risk) return <section id="risk"><ReportCard title="Overall risk">No risk data for this run.</ReportCard></section>
  const layers = risk.by_evidence_layer || {}

  return (
    <section id="risk">
      <ReportCard title="Overall risk score" style={{ background: C.amberDim, border: `1px solid ${C.amber}44` }}>
        <div style={{ marginBottom: 10 }}><StatusPill status="not_calculated" size="md" /></div>
        <Explain>
          Risk is usually calculated as hazard times exposure times vulnerability, meaning how likely a flood is, multiplied by who and what is in its path,
          multiplied by how prepared they are to handle it. All three of those pieces now exist as real data for this area. What's missing on purpose is the
          formula that combines them into one final number.
        </Explain>
        <Explain>
          An earlier shortcut, just multiplying by a placeholder of 1.0, was considered and rejected. That would have quietly dressed up the exposure number
          as if it were a real risk score, without actually accounting for preparedness. Rather than guess, this stays honestly unscored until a real,
          reviewed method for combining the three is decided.
        </Explain>
      </ReportCard>

      <div style={{ fontFamily: FONTS.body, fontSize: 13, fontWeight: 600, color: C.text, margin: '22px 0 12px' }}>Status by flood type</div>
      {Object.entries(layers).map(([key, r]) => (
        <ReportCard key={key} title={SUSC_INFO[key]?.label || key.replace(/_/g, ' ')} status={r.status}>
          <Small>{r.reason || 'No further detail available.'}</Small>
          {/* C23/C24 item 42: risk's own docstring requires it to propagate
              exposure's Gate C status "rather than silently disappearing two
              layers up the stack". It now does, on all four return paths, and
              this is where it surfaces. */}
          {r.exposure_product_validation_status && (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8 }}>
              <StatusPill status={r.exposure_product_validation_status} />
              <GateCNote status={r.exposure_product_validation_status} />
            </div>
          )}
          {/* Risk inherits its trust from the hazard and exposure it consumed
              (item 40's gated_inherit), so the inherited verdict shows here. */}
          <BlockTrustNote block={r} />
        </ReportCard>
      ))}
    </section>
  )
}

/* ============================================================
   SEGMENT DETAIL (map popover)
   ============================================================ */

function SegmentDetail({ seg, onClose, colorFor }) {
  if (!seg) return null
  const color = colorFor(seg.dominant_landcover_category)
  const isOsmTagged = seg.label_source === 'osm_vector'
  return (
    <div style={{ position: 'absolute', bottom: 20, left: '50%', transform: 'translateX(-50%)', background: C.panelRaised, border: `1px solid ${C.hairlineBright}`, borderRadius: 12, padding: '18px 22px', width: 420, zIndex: 1000, boxShadow: '0 16px 48px rgba(0,0,0,0.55)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
        <div>
          <div style={{ fontFamily: FONTS.mono, fontSize: 9, color: C.textFaint, marginBottom: 4 }}>SEGMENT {seg.segment_id}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{ width: 11, height: 11, borderRadius: 3, background: color }} />
            <span style={{ fontFamily: FONTS.display, fontSize: 15, fontWeight: 600, color }}>{CAT_LABELS[seg.dominant_landcover_category] || seg.dominant_landcover_category}</span>
          </div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: `1px solid ${C.hairline}`, color: C.textDim, borderRadius: 6, width: 26, height: 26, cursor: 'pointer', fontSize: 13 }}>✕</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginBottom: 14 }}>
        <Metric label="Area" value={`${seg.area}`} unit="px" />
        <Metric label="Purity" value={seg.landcover_purity_pct != null ? fmtPct(seg.landcover_purity_pct) : '—'} accent={color} />
        <Metric label="Road access" value={seg.road_access_score === -1 ? 'N/A' : seg.road_access_score?.toFixed?.(2) ?? seg.road_access_score} />
      </div>
      {seg.ambiguous_between && (
        <div style={{ fontFamily: FONTS.body, fontSize: 11, color: C.text, background: C.amberDim, border: `1px solid ${C.amber}44`, borderRadius: 8, padding: '9px 11px', marginBottom: 14, lineHeight: 1.5 }}>
          The model is torn between {CAT_LABELS[seg.ambiguous_between[0]] || seg.ambiguous_between[0]} and {CAT_LABELS[seg.ambiguous_between[1]] || seg.ambiguous_between[1]}
          {seg.ambiguous_pct != null && <> ({fmtPct(seg.ambiguous_pct)} of this segment)</>}
        </div>
      )}
      <div style={{ fontFamily: FONTS.body, fontSize: 11, color: C.textDim, lineHeight: 1.6, borderTop: `1px solid ${C.hairline}`, paddingTop: 10 }}>
        {isOsmTagged
          ? <>Tagged using real map data ({seg.osm_feature_type || 'road/waterway match'}) because this type can't be reliably told apart from satellite color alone.</>
          : <>Based on the model's best guess across this segment's real shape. Purity is the share of pixels inside it that agree with the label shown.</>}
      </div>
    </div>
  )
}

/* ============================================================
   REPORT MODE (full page)
   ============================================================ */

const NAV_SECTIONS = [
  { id: 'overview', label: 'Overview' },
  // C32 / build item 41. Placed second, directly after Overview, because the
  // verdict governs how everything below it should be read. Not placed first:
  // Overview is the landing section and NAV_SECTIONS[0] is the scroll-spy
  // default, so promoting Reliability to index 0 would change where the report
  // opens for every run, including the ones where nothing is wrong.
  { id: 'reliability', label: 'Reliability', alertable: true },
  { id: 'landcover', label: 'Landcover' },
  { id: 'hazard', label: 'Hazard' },
  { id: 'exposure', label: 'Exposure' },
  { id: 'vulnerability', label: 'Vulnerability' },
  { id: 'risk', label: 'Risk' },
]

function ReportMode({ result, onBackToMap, landcoverProps }) {
  const [activeSection, setActiveSection] = useState('overview')
  const scrollRef = useRef(null)
  const sectionRefs = useRef({})

  const jumpTo = (id) => {
    sectionRefs.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  useEffect(() => {
    const container = scrollRef.current
    if (!container) return
    const onScroll = () => {
      const top = container.scrollTop + 120
      let current = NAV_SECTIONS[0].id
      for (const s of NAV_SECTIONS) {
        const el = sectionRefs.current[s.id]
        if (el && el.offsetTop <= top) current = s.id
      }
      setActiveSection(current)
    }
    container.addEventListener('scroll', onScroll)
    return () => container.removeEventListener('scroll', onScroll)
  }, [])

  // (ReportMode previously computed an unused imageUrl here. Since item 43 that
  // would issue a real authenticated image fetch for a value nothing reads, so
  // it is removed rather than left as a silent request.)
  // Read once per render and share with the nav; the banner and section read it
  // themselves so they stay usable standalone.
  const reportTrust = reportApplicability(result)

  return (
    <div style={{ position: 'absolute', inset: 0, background: C.void, zIndex: 900, display: 'flex' }}>
      {/* In-report sticky nav */}
      <div style={{ width: 220, flexShrink: 0, borderRight: `1px solid ${C.hairline}`, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '20px 18px 14px' }}>
          <button onClick={onBackToMap} style={{
            display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: `1px solid ${C.hairline}`,
            color: C.textDim, borderRadius: 7, padding: '7px 12px', cursor: 'pointer', fontFamily: FONTS.body, fontSize: 11.5, marginBottom: 18,
          }}>← Back to map</button>
          <div style={{ fontFamily: FONTS.display, fontSize: 15, fontWeight: 700, color: C.text }}>Analysis report</div>
          <div style={{ fontFamily: FONTS.mono, fontSize: 9.5, color: C.textFaint, marginTop: 4 }}>{result.run_id}</div>
        </div>

        {/* AOI thumbnail */}
        <div style={{ margin: '0 18px 18px', borderRadius: 9, overflow: 'hidden', border: `1px solid ${C.hairline}`, height: 110, position: 'relative' }}>
          <MapContainer center={[(result.aoi.south + result.aoi.north) / 2, (result.aoi.west + result.aoi.east) / 2]} zoom={12.5} style={{ height: '100%', width: '100%' }} zoomControl={false} dragging={false} scrollWheelZoom={false} doubleClickZoom={false} touchZoom={false} attributionControl={false}>
            <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
            <Rectangle bounds={[[result.aoi.south, result.aoi.west], [result.aoi.north, result.aoi.east]]} pathOptions={{ color: C.cyan, weight: 2, fillOpacity: 0.12 }} />
          </MapContainer>
        </div>

        <nav style={{ padding: '0 10px', flex: 1, overflowY: 'auto' }}>
          {NAV_SECTIONS.map(s => {
            // C32 / item 41: the nav itself carries the alert, so a flagged run
            // is visible without scrolling and without having reached the
            // banner. The sidebar is always on screen; the banner is not.
            const alerting = s.alertable && reportTrust.isAlert
            const alertColor = reportTrust.trust === 'out_of_distribution' ? C.coral : C.amber
            const active = activeSection === s.id
            return (
              <button key={s.id} onClick={() => jumpTo(s.id)} style={{
                display: 'flex', alignItems: 'center', gap: 7, width: '100%', textAlign: 'left',
                padding: '9px 12px', marginBottom: 2,
                background: active ? (alerting ? `${alertColor}1a` : C.cyanDim) : 'none',
                border: 'none', borderRadius: 7, cursor: 'pointer',
                fontFamily: FONTS.body, fontSize: 12.5, fontWeight: active || alerting ? 600 : 500,
                color: alerting ? alertColor : (active ? C.cyan : C.textDim),
                borderLeft: `2px solid ${active ? (alerting ? alertColor : C.cyan) : 'transparent'}`,
              }}>
                {alerting && (
                  <span aria-hidden="true" style={{
                    width: 6, height: 6, borderRadius: 6, background: alertColor, flexShrink: 0,
                    boxShadow: `0 0 6px ${alertColor}`,
                  }} />
                )}
                <span>{s.label}</span>
                {alerting && (
                  <span style={{
                    marginLeft: 'auto', fontFamily: FONTS.mono, fontSize: 8.5, letterSpacing: '0.06em',
                    color: alertColor, border: `1px solid ${alertColor}55`, borderRadius: 4, padding: '1px 5px',
                  }}>{reportTrust.trust === 'out_of_distribution' ? 'OOD' : 'WEAK'}</span>
                )}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Scrollable report body */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '32px 0' }}>
        <div style={{ maxWidth: 760, margin: '0 auto', padding: '0 32px' }}>
          {/* C32 / item 41: above everything, so an out_of_distribution run
              cannot be read without seeing it first. */}
          <ApplicabilityBanner result={result} onJump={jumpTo} />
          <div ref={el => sectionRefs.current.overview = el}><SecOverview result={result} /></div>
          <div ref={el => sectionRefs.current.reliability = el} style={{ marginTop: 8 }}><SecReliability result={result} /></div>
          <div ref={el => sectionRefs.current.landcover = el} style={{ marginTop: 8 }}><SecLandcover result={result} {...landcoverProps} /></div>
          <div ref={el => sectionRefs.current.hazard = el} style={{ marginTop: 8 }}><SecHazard result={result} /></div>
          <div ref={el => sectionRefs.current.exposure = el} style={{ marginTop: 8 }}><SecExposure result={result} /></div>
          <div ref={el => sectionRefs.current.vulnerability = el} style={{ marginTop: 8 }}><SecVulnerability result={result} /></div>
          <div ref={el => sectionRefs.current.risk = el} style={{ marginTop: 8 }}><SecRisk result={result} /></div>
          <div style={{ height: 60 }} />
        </div>
      </div>
    </div>
  )
}

/* ============================================================
   APP
   ============================================================ */

export default function App() {
  const [bbox, setBbox] = useState(null)
  const [drawing, setDrawing] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [manualBbox, setManualBbox] = useState({ west: '72.836', south: '19.037', east: '72.862', north: '19.060' })
  const [showLandcover, setShowLandcover] = useState(true)
  const [landcoverOpacity, setLandcoverOpacity] = useState(0.75)
  const [showRoadsVector, setShowRoadsVector] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [reportMode, setReportMode] = useState(false)

  useEffect(() => {
    if (!bbox) return
    setManualBbox({ west: String(bbox.west), south: String(bbox.south), east: String(bbox.east), north: String(bbox.north) })
  }, [bbox])

  const applyManualBbox = () => {
    const b = { west: parseFloat(manualBbox.west), south: parseFloat(manualBbox.south), east: parseFloat(manualBbox.east), north: parseFloat(manualBbox.north) }
    if (Object.values(b).some(isNaN)) { setError('Invalid coordinates'); return }
    setBbox(b); setResult(null); setSelected(null)
  }
  const handleBboxChange = useCallback((b) => { setBbox(b); setDrawing(false); setResult(null); setSelected(null) }, [])

  const analyze = async () => {
    if (!bbox) { setError('Draw an AOI first'); return }
    setLoading(true); setError(null); setResult(null); setSelected(null)
    try {
      const res = await apiFetch('/api/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ west: bbox.west, south: bbox.south, east: bbox.east, north: bbox.north, start_date: '2024-01-01', end_date: '2024-03-31', aoi_label: 'aoi', demo: false }),
      })
      // A 401 has one cause and one fix; say so instead of surfacing the raw
      // body. Before item 43 this was every request, and the error the user saw
      // gave no hint that a key was involved at all.
      if (res.status === 401) {
        throw new Error(
          isKeyMissing()
            ? 'API key not configured. Set VITE_GEOWATCH_API_KEY in geowatch-ui/.env (see .env.example) and restart the dev server.'
            : 'API rejected the key. Check VITE_GEOWATCH_API_KEY in geowatch-ui/.env matches GEOWATCH_API_KEY in the backend .env.'
        )
      }
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setResult(data)
      setReportMode(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const reset = () => { setBbox(null); setResult(null); setSelected(null); setError(null); setDrawing(false); setReportMode(false) }
  const imageUrl = useAuthedImage(landcoverImagePath(result))

  const landcoverProps = { showLandcover, setShowLandcover, landcoverOpacity, setLandcoverOpacity, showRoadsVector, setShowRoadsVector }

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden', position: 'relative', background: C.void, fontFamily: FONTS.body }}>
      {isKeyMissing() && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, zIndex: 2000,
          background: C.coralDim, borderBottom: `1px solid ${C.coral}`,
          padding: '9px 16px', fontFamily: FONTS.body, fontSize: 12, color: C.text,
        }}>
          <b style={{ color: C.coral }}>No API key configured.</b>{' '}
          Every request will be refused. Copy <code style={{ fontFamily: FONTS.mono, fontSize: 11 }}>geowatch-ui/.env.example</code> to{' '}
          <code style={{ fontFamily: FONTS.mono, fontSize: 11 }}>geowatch-ui/.env</code>, set{' '}
          <code style={{ fontFamily: FONTS.mono, fontSize: 11 }}>VITE_GEOWATCH_API_KEY</code> to the backend&rsquo;s{' '}
          <code style={{ fontFamily: FONTS.mono, fontSize: 11 }}>GEOWATCH_API_KEY</code>, and restart the dev server.
        </div>
      )}
      {legacyPipelineNotice(result) && (
        <div role="status" data-testid="legacy-pipeline-banner" style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 2000,
          background: C.coralDim, borderTop: `1px solid ${C.coral}`,
          padding: '9px 16px', fontFamily: FONTS.body, fontSize: 12, color: C.text,
        }}>
          <b style={{ color: C.coral }}>{legacyPipelineNotice(result)}</b>
        </div>
      )}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: ${C.void}; }
        ::-webkit-scrollbar-thumb { background: ${C.hairlineBright}; border-radius: 8px; }
        button:focus-visible, input:focus-visible { outline: 2px solid ${C.cyan}; outline-offset: 2px; }
        .gw-vector-tooltip { background: ${C.panelRaised} !important; border: 1px solid ${C.hairline} !important; color: ${C.text} !important; }
      `}</style>

      {/* Sidebar toggle (always visible, floats top-left when sidebar hidden) */}
      <button onClick={() => setSidebarOpen(o => !o)} style={{
        position: 'absolute', top: 14, left: sidebarOpen ? 234 : 14, zIndex: 950,
        width: 30, height: 30, borderRadius: 7, cursor: 'pointer',
        background: C.panelRaised, border: `1px solid ${C.hairline}`, color: C.textDim,
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13,
        transition: 'left 0.15s',
      }}>{sidebarOpen ? '‹' : '›'}</button>

      {/* Sidebar — small now: just controls, no data */}
      {sidebarOpen && (
        <div style={{ width: 260, flexShrink: 0, background: C.panel, borderRight: `1px solid ${C.hairline}`, display: 'flex', flexDirection: 'column', zIndex: 500, overflow: 'hidden' }}>
          <div style={{ padding: '20px 18px 16px', borderBottom: `1px solid ${C.hairline}` }}>
            <div style={{ fontFamily: FONTS.display, fontSize: 16, fontWeight: 700, color: C.text }}>GeoWatch Copilot</div>
            <div style={{ fontFamily: FONTS.body, fontSize: 11, color: C.textDim, marginTop: 3 }}>Satellite flood intelligence</div>
          </div>

          <div style={{ padding: '16px 18px', borderBottom: `1px solid ${C.hairline}` }}>
            <div style={{ fontFamily: FONTS.body, fontSize: 10.5, color: C.textDim, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 10, fontWeight: 600 }}>Area of interest</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 }}>
              {[['west', 'West'], ['south', 'South'], ['east', 'East'], ['north', 'North']].map(([k, lbl]) => (
                <div key={k}>
                  <div style={{ fontFamily: FONTS.body, fontSize: 9, color: C.textFaint, marginBottom: 3 }}>{lbl}</div>
                  <input value={manualBbox[k]} onChange={e => setManualBbox(p => ({ ...p, [k]: e.target.value }))}
                    style={{ width: '100%', background: C.panelDeep, border: `1px solid ${C.hairline}`, borderRadius: 5, padding: '5px 7px', color: C.text, fontFamily: FONTS.mono, fontSize: 10.5, outline: 'none' }} />
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={applyManualBbox} style={{ flex: 1, padding: '7px 0', fontFamily: FONTS.mono, fontSize: 9.5, background: C.panelDeep, border: `1px solid ${C.hairline}`, color: C.cyan, borderRadius: 6, cursor: 'pointer' }}>Apply</button>
              <button onClick={() => setDrawing(d => !d)} style={{ flex: 1, padding: '7px 0', fontFamily: FONTS.mono, fontSize: 9.5, background: drawing ? C.cyan : C.panelDeep, border: `1px solid ${drawing ? C.cyan : C.hairline}`, color: drawing ? '#08121a' : C.textDim, borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}>{drawing ? 'Drawing…' : 'Draw on map'}</button>
            </div>
          </div>

          <div style={{ padding: '16px 18px', borderBottom: `1px solid ${C.hairline}` }}>
            <button onClick={analyze} disabled={loading || !bbox} style={{
              width: '100%', padding: '12px 0', background: loading || !bbox ? C.panelDeep : C.cyan, color: loading || !bbox ? C.textFaint : '#08121a',
              border: 'none', borderRadius: 8, cursor: loading || !bbox ? 'not-allowed' : 'pointer',
              fontFamily: FONTS.display, fontSize: 12.5, fontWeight: 700, letterSpacing: '0.02em',
            }}>{loading ? 'ANALYZING…' : 'ANALYZE'}</button>
            {loading && <div style={{ marginTop: 8, fontFamily: FONTS.body, fontSize: 10.5, color: C.textDim, textAlign: 'center' }}>Sentinel-2 → SAM → per-pixel inference. Roughly 3–5 minutes.</div>}
            {error && <div style={{ marginTop: 8, fontFamily: FONTS.body, fontSize: 11, color: C.coral, lineHeight: 1.5 }}>{error}</div>}
          </div>

          {result && (
            <div style={{ padding: '16px 18px' }}>
              <button onClick={() => setReportMode(true)} style={{
                width: '100%', padding: '11px 0', background: C.cyanDim, border: `1px solid ${C.cyan}`, color: C.cyan,
                borderRadius: 8, cursor: 'pointer', fontFamily: FONTS.display, fontSize: 12, fontWeight: 700, marginBottom: 8,
              }}>View full report</button>
              <button onClick={reset} style={{ width: '100%', padding: '8px 0', fontFamily: FONTS.mono, fontSize: 9.5, background: 'none', border: `1px solid ${C.hairline}`, color: C.textDim, borderRadius: 6, cursor: 'pointer' }}>Clear &amp; reset</button>
            </div>
          )}

          <div style={{ flex: 1 }} />
          <div style={{ padding: '10px 18px', borderTop: `1px solid ${C.hairline}` }}>
            <div style={{ fontFamily: FONTS.mono, fontSize: 8.5, color: C.textFaint, lineHeight: 1.6 }}>
              Sentinel-2 SR · SAM vit_b · ResNet50+DeepLabV3+<br />CPS Lab · VIPS Delhi
            </div>
          </div>
        </div>
      )}

      {/* Map */}
      <div style={{ flex: 1, position: 'relative', cursor: drawing ? 'crosshair' : 'default' }}>
        <MapContainer center={[19.048, 72.849]} zoom={14} style={{ height: '100%', width: '100%' }} zoomControl>
          <DragToggle drawing={drawing} />
          <MapRecenter bbox={bbox} />
          <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" attribution="Tiles &copy; Esri" />
          <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}" attribution="Labels &copy; Esri" />
          <AOIDrawer onBboxChange={handleBboxChange} bbox={bbox} drawing={drawing} />
          {result && showLandcover && <LandcoverOverlay imageUrl={imageUrl} bbox={result.aoi} opacity={landcoverOpacity} />}
          {result?.run_id && <OSMVectorLayer runId={result.run_id} visible={showRoadsVector} />}
          {result?.segments && (
            <SegmentOverlays segments={result.segments} bbox={result.aoi} onSelect={setSelected} selected={selected}
              tileWidth={result.tile_dimensions?.width ?? 291} tileHeight={result.tile_dimensions?.height ?? 257}
              colorFor={cat => categoryColor(result, cat)} />
          )}
        </MapContainer>

        {!result && !loading && (
          <div style={{ position: 'absolute', top: 18, left: '50%', transform: 'translateX(-50%)', background: 'rgba(17,17,41,0.9)', border: `1px solid ${C.hairline}`, borderRadius: 9, padding: '9px 18px', zIndex: 400, pointerEvents: 'none' }}>
            <span style={{ fontFamily: FONTS.body, fontSize: 11.5, color: C.textDim }}>{drawing ? '↔ Drag to draw an AOI, release to confirm' : 'Draw or enter an AOI, then click Analyze'}</span>
          </div>
        )}

        {loading && (
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,22,0.82)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 600 }}>
            <div style={{ fontFamily: FONTS.display, fontSize: 15, fontWeight: 600, color: C.cyan, marginBottom: 12 }}>PIPELINE RUNNING</div>
            <div style={{ fontFamily: FONTS.body, fontSize: 11.5, color: C.textDim, lineHeight: 2, textAlign: 'center' }}>Sentinel-2 → SAM segmentation → per-pixel classification</div>
          </div>
        )}

        {selected && !reportMode && <SegmentDetail seg={selected} onClose={() => setSelected(null)} colorFor={cat => categoryColor(result, cat)} />}

        {result && !reportMode && (
          <div style={{ position: 'absolute', top: 14, right: 14, zIndex: 400, display: 'flex', gap: 8 }}>
            <button onClick={() => setReportMode(true)} style={{
              background: C.cyan, border: 'none', color: '#08121a', borderRadius: 8, padding: '9px 16px',
              fontFamily: FONTS.display, fontSize: 12, fontWeight: 700, cursor: 'pointer',
            }}>View full report</button>
          </div>
        )}
      </div>

      {reportMode && result && (
        <ReportMode result={result} onBackToMap={() => setReportMode(false)} landcoverProps={landcoverProps} />
      )}
    </div>
  )
}