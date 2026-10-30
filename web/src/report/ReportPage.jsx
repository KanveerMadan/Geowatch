import { useEffect, useState } from 'react'
import { ArrowSquareOut, Printer } from '@phosphor-icons/react'
import { color } from '../design/tokens.js'
import { TRUST, fmtPct1, fractionRows, groundSummary, trustOf } from '../lib/contract.js'
import { TIER_BREAKS, TIER_TEXT, floodRows, floodSummary, defaultFloodLayer, rankWards, wardUnitType } from '../lib/flood.js'
import { changeRows, changeSummary } from '../lib/change.js'
import { bboxAreaKm2, fmtKm2 } from '../lib/geo.js'
import { areaNotes, sourcesOf } from '../lib/notes.js'
import { getChangeFeatures, getFeatures, getResult } from '../lib/api.js'
import StaticMap from './StaticMap.jsx'
import '../styles/report.css'

const score = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const when = new Intl.DateTimeFormat(undefined, { dateStyle: 'long' })
const WARDS_IN_REPORT = 12
const fmtDate = (iso) => when.format(new Date(`${iso}T00:00:00`))
const coord = (v, pos, neg) => `${Math.abs(v).toFixed(4)}° ${v >= 0 ? pos : neg}`

/** A printed badge: the label, and for a validated output its scope. */
function Badge({ of }) {
  const t = trustOf(of)
  return <span className={`rbadge rbadge-${t.key}`}>{t.label}</span>
}
function Scope({ of }) {
  const t = trustOf(of)
  return t.scope ? <span className="rscope">Holds for: {t.scope}</span> : null
}

// Map layers for the report's three pictures.
const cellsLayer = (fc, paint) => (map) => {
  map.addSource('cells', { type: 'geojson', data: fc })
  map.addLayer({ id: 'cells', type: 'fill', source: 'cells', paint })
}
const isNum = (p) => ['==', ['typeof', ['get', p]], 'number']

function SectionHead({ title, children }) {
  return (
    <header className="rsec-head">
      <h2>{title}</h2>
      {children}
    </header>
  )
}

export default function ReportPage({ resultId, name }) {
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    const ctl = new AbortController()
    ;(async () => {
      try {
        const r = await getResult(resultId, ctl.signal)
        const wardType = wardUnitType(r)
        const [grid, change, wards] = await Promise.all([
          getFeatures(resultId, 'grid', ctl.signal).catch(() => null),
          getChangeFeatures(resultId, ctl.signal).catch(() => null),
          wardType ? getFeatures(resultId, wardType, ctl.signal).catch(() => null) : null,
        ])
        setState({ r, grid, change, wards, wardType })
      } catch {
        if (!ctl.signal.aborted) setState({ error: true })
      }
    })()
    return () => ctl.abort()
  }, [resultId])

  useEffect(() => { document.title = `${name ?? 'Area'} report, GeoWatch` }, [name])

  if (state.loading) return <main className="report"><p className="rmuted">Loading the report…</p></main>
  if (state.error) {
    return <main className="report"><p>This report could not be loaded. The result may not exist on this server.</p></main>
  }

  const { r, grid, change, wards, wardType } = state
  const o = r.outputs
  const bbox = r.request.bbox
  const title = name ?? r.request.aoi_label.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  const fRows = fractionRows(o.fractions)
  const hRows = floodRows(o.susceptibility)
  const cRows = changeRows(o.change)
  const floodKey = defaultFloodLayer(o.susceptibility)
  const floodShown = hRows.find((h) => h.key === floodKey)
  const changeKey = cRows.find((c) => c.measured)?.key
  const notes = areaNotes(r)
  const wardRank = wards && floodKey ? rankWards(wards, floodKey) : null
  const labelsUsed = [...new Set([...fRows, ...hRows, ...cRows].map((x) => x.trust.key))]
    .filter((k) => TRUST[k])
  const sources = [...new Set([
    ...sourcesOf(o.fractions), ...sourcesOf(o.susceptibility), ...sourcesOf(o.change), ...sourcesOf(o.observability),
  ])]
  const hue = (k) => color.data[k] ?? color.select

  return (
    <main className="report">
      <nav className="rbar" aria-label="Report actions">
        <a href={`./?bbox=${bbox.join(',')}`}><ArrowSquareOut size={15} aria-hidden="true" /> Open in GeoWatch</a>
        <button type="button" onClick={() => window.print()}><Printer size={15} aria-hidden="true" /> Print or save as PDF</button>
      </nav>

      <header className="rhead">
        <p className="rkicker">GeoWatch area report</p>
        <h1>{title}</h1>
        <dl className="rmeta">
          <div><dt>Area</dt><dd>{fmtKm2(bboxAreaKm2(bbox))}, centred {coord((bbox[1] + bbox[3]) / 2, 'N', 'S')}, {coord((bbox[0] + bbox[2]) / 2, 'E', 'W')}</dd></div>
          <div><dt>Imagery window</dt><dd>{fmtDate(r.request.window.start)} to {fmtDate(r.request.window.end)}</dd></div>
          <div><dt>Analysed</dt><dd>{when.format(new Date(r.created_utc))}</dd></div>
          <div><dt>Result</dt><dd className="rmono">{resultId}, version {r.model_version.version_id.slice(0, 12)}</dd></div>
        </dl>
        <p className="rnote">
          Every number here carries a trust label. Only results labelled Validated have passed an independent test, and only within the scope shown with them.
        </p>
      </header>

      <StaticMap bbox={bbox} label={`Satellite view of ${title}, the analysed box outlined`} height={340} />

      <section className="rsec">
        <SectionHead title="Ground cover" />
        <p className="rlead">{groundSummary(o.fractions)}</p>
        <div className="rsplit">
          <table className="rtable">
            <thead><tr><th scope="col">Cover</th><th scope="col" className="rnum">Share</th><th scope="col">Label</th></tr></thead>
            <tbody>
              {fRows.map((x) => (
                <tr key={x.key}>
                  <th scope="row"><i className="rsw" style={{ background: x.measured ? hue(x.key) : undefined }} data-hatch={!x.measured || undefined} />{x.name}</th>
                  <td className="rnum">{x.measured ? fmtPct1(x.value) : <span className="rmuted">{x.display}</span>}</td>
                  <td><Badge of={{ validation_status: x.trust.key, validation_scope: x.trust.scope }} /><Scope of={{ validation_status: x.trust.key, validation_scope: x.trust.scope }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {grid && (
            <div>
              <StaticMap bbox={bbox} height={230} label="Built share of each 100 m cell"
                addLayers={cellsLayer(grid, { 'fill-color': hue('built'), 'fill-opacity': ['case', isNum('built'), ['interpolate', ['linear'], ['get', 'built'], 0, 0.05, 1, 0.9], 0] })} />
              <p className="rcap">Built share of each 100 m cell, deeper where more is built.</p>
            </div>
          )}
        </div>
        {notes.length > 0 && (
          <ul className="rnotes">{notes.map((n) => <li key={n.id}>{n.text}</li>)}</ul>
        )}
      </section>

      <section className="rsec">
        <SectionHead title="Flood susceptibility" />
        <p className="rlead">{floodSummary(o.susceptibility)}</p>
        <div className="rsplit">
          <table className="rtable">
            <thead><tr><th scope="col">Type</th><th scope="col">Tier</th><th scope="col" className="rnum">Score</th><th scope="col">Label</th></tr></thead>
            <tbody>
              {hRows.map((x) => (
                <tr key={x.key}>
                  <th scope="row">{x.name}<span className="rsub">{x.mapped ? 'mapped per cell' : x.measured ? 'one value for the area' : ''}</span></th>
                  <td>{x.measured ? <><i className="rsw" style={{ background: color.flood[x.tier] }} />{x.tierText}</> : <span className="rmuted">{x.text}</span>}</td>
                  <td className="rnum">{x.measured ? score.format(x.value) : ''}</td>
                  <td><Badge of={{ validation_status: x.trust.key, validation_scope: x.trust.scope }} /><Scope of={{ validation_status: x.trust.key, validation_scope: x.trust.scope }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {grid && floodShown?.mapped && (
            <div>
              <StaticMap bbox={bbox} height={230} label={`${floodShown.name} susceptibility per 100 m cell`}
                addLayers={cellsLayer(grid, {
                  'fill-color': ['step', ['get', `flood_${floodKey}`], color.flood.very_low, TIER_BREAKS[0], color.flood.low,
                    TIER_BREAKS[1], color.flood.moderate, TIER_BREAKS[2], color.flood.high, TIER_BREAKS[3], color.flood.very_high],
                  'fill-opacity': ['case', isNum(`flood_${floodKey}`), 0.78, 0],
                })} />
              <p className="rcap">
                {floodShown.name} tier per 100 m cell: {Object.entries(TIER_TEXT).map(([k, v]) => <span key={k} className="rkey"><i className="rsw" style={{ background: color.flood[k] }} />{v}</span>)}
              </p>
            </div>
          )}
        </div>
        <p className="rcap">Susceptibility is how prone the ground is to each kind of flooding. It is not a forecast of any flood.</p>
        {wardRank && wardRank.ranked.length > 0 && (
          <>
            <h3 className="rh3">Wards ranked by {floodShown.long}</h3>
            <table className="rtable rtable-compact">
              <thead><tr><th scope="col" className="rnum">Rank</th><th scope="col">Ward</th><th scope="col">Tier</th><th scope="col" className="rnum">Score</th></tr></thead>
              <tbody>
                {wardRank.ranked.slice(0, WARDS_IN_REPORT).map((w) => (
                  <tr key={w.id}><td className="rnum">{w.rank}</td><th scope="row">{w.name}</th><td>{TIER_TEXT[w.tier]}</td><td className="rnum">{score.format(w.value)}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="rcap">
              Mean score over each ward’s part inside the box ({wardType.slice(5).replace(/_/g, ' ')}). The ranking carries the {floodShown.trust.label.toLowerCase()} label of {floodShown.long}.
              {wardRank.unranked.length > 0 && <> Not measured, not ranked: {wardRank.unranked.map((w) => w.name).join(', ')}.</>}
            </p>
          </>
        )}
      </section>

      <section className="rsec">
        <SectionHead title="Change over time" />
        <p className="rlead">{changeSummary(o.change)}</p>
        <div className="rsplit">
          <table className="rtable">
            <thead><tr><th scope="col">Cover</th><th scope="col">Years</th><th scope="col" className="rnum">Up</th><th scope="col" className="rnum">Down</th><th scope="col" className="rnum">No change</th><th scope="col">Label</th></tr></thead>
            <tbody>
              {cRows.map((x) => (
                <tr key={x.key}>
                  <th scope="row">{x.name}</th>
                  {x.measured ? (
                    <>
                      <td className="rmono">{x.years ? `${x.years[0]} to ${x.years[1]}` : ''}</td>
                      <td className="rnum">{x.increase}</td><td className="rnum">{x.decrease}</td><td className="rnum">{x.unchanged}</td>
                    </>
                  ) : <td colSpan={4} className="rmuted">{x.text}</td>}
                  <td><Badge of={{ validation_status: x.trust.key, validation_scope: x.trust.scope }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {change?.features?.length > 0 && changeKey && (
            <div>
              <StaticMap bbox={bbox} height={230} label={`Cells where ${changeKey} changed`}
                addLayers={cellsLayer(change, {
                  'fill-color': hue(changeKey),
                  'fill-opacity': ['match', ['get', changeKey], 'increase', 0.75, 'decrease', 0.3, 0],
                })} />
              <p className="rcap">{cRows.find((c) => c.key === changeKey).name}: cells that went up (solid) and down (pale). Counts are 100 m cells.</p>
            </div>
          )}
        </div>
      </section>

      <section className="rsec rsec-keep">
        <SectionHead title="What the labels mean" />
        <dl className="rlabels">
          {labelsUsed.map((k) => (
            <div key={k}><dt><span className={`rbadge rbadge-${k}`}>{TRUST[k].label}</span></dt><dd>{TRUST[k].explain}</dd></div>
          ))}
        </dl>
      </section>

      <section className="rsec rsec-keep">
        <SectionHead title="Data sources" />
        <ul className="rsources">
          {sources.map((s) => <li key={s}>{s}</li>)}
          <li>Pictures: Esri World Imagery (Esri, Vantor, Earthstar Geographics, and the GIS User Community)</li>
        </ul>
        <p className="rcap">Generated {when.format(new Date())} from stored result {resultId}. A stored result never changes; a new method version is a new result.</p>
      </section>
    </main>
  )
}
