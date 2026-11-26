import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { color } from '../design/tokens.js'
import { getChangeFeatures, getChangeCell, compareChange } from '../lib/api.js'
import { fmtPct0, humanize } from '../lib/contract.js'
import { cellAt, toUnit, unitCells } from '../lib/overlay.js'
import { compareError, dynamicWorldCredit, historyMark, historyStates, historyText, initialComparison,
  num, periodText, previousDay, replayError, signalName, stateName, summaryOf } from '../lib/changeHistory.js'
import { useYearPictures } from '../lib/useYearPictures.js'
import { Disclosure } from './PanelBits.jsx'
import ChangeDock from './ChangeDock.jsx'
import ChangeZone from './ChangeZone.jsx'
import SurveyMeasures from './SurveyMeasures.jsx'
import SwipeOverlay from './SwipeOverlay.jsx'
import TrustBadge from './TrustBadge.jsx'

const empty = []
const modeNames = { history: 'Episodes', compare: 'Compare dates', pictures: 'Browse imagery' }
const sourceName = (key) => ({ sentinel1: 'Sentinel-1', sentinel2: 'Sentinel-2', landsat8: 'Landsat 8',
  landsat9: 'Landsat 9', dynamic_world: 'Dynamic World', open_buildings: 'Open Buildings Temporal' })[key] ?? humanize(key)
const amount = (m2) => Number.isFinite(m2) ? num(m2) + ' m²' : 'Unavailable'

function StatusCounts({ summary }) {
  return <dl className="chg-kv">{Object.keys(historyStates).map((state) =>
    <div key={state}><dt>{stateName(state)}</dt><dd className="num">{num(summary.counts?.[state])}</dd></div>
  )}</dl>
}

function Events({ events }) {
  const [id, setId] = useState(null)
  const event = events.find((e) => e.event_id === id) ?? events.at(-1)
  if (!event) return <p className="caption">No signal episodes recorded in this cell.</p>
  return <div className="history-detail">
    <label>Signal episode
      <select value={event.event_id} onChange={(e) => setId(e.target.value)}>
        {events.map((e) => <option key={e.event_id} value={e.event_id}>
          {e.detected_on} · {humanize(e.transition)}
        </option>)}
      </select>
    </label>
    <dl className="kv">
      <div><dt>Signal onset</dt><dd>{event.onset?.after ? `After ${event.onset.after}, ` : ''}by {event.onset?.by ?? event.detected_on}</dd></div>
      <div><dt>First detection</dt><dd>{event.detected_on}</dd></div>
      <div><dt>State</dt><dd>{humanize(event.lifecycle)}{event.trajectory && <> · {humanize(event.trajectory)}</>}</dd></div>
      {event.confirmed_on && <div><dt>Corroborated</dt><dd>{event.confirmed_on}</dd></div>}
      {event.recovered_on && <div><dt>Recovered</dt><dd>{event.recovered_on}</dd></div>}
      <div><dt>Last evidence</dt><dd>{event.last_evidence_on} · {num(event.detections)} observation dates</dd></div>
      {!!event.interpretation?.label && <div><dt>Learned interpretation</dt><dd>{humanize(event.interpretation.label)} · experimental{event.interpretation.as_of && <> as of {event.interpretation.as_of}</>}{event.interpretation.reason && <span className="kv-src">{event.interpretation.reason}</span>}</dd></div>}
      {(event.signals ?? []).map((s) => <div key={JSON.stringify([s.signal, s.source, s.track])}>
        <dt>{signalName(s.signal)}</dt><dd>{num(s.baseline)} expected · {num(s.value)} observed
        <span className="kv-src">{sourceName(s.source)} · {s.track} · {s.observed_on}</span></dd>
      </div>)}
    </dl>
    {event.land_cover_context && <Disclosure label="Land-cover context">
      <p className="caption">Dynamic World class scores from Sentinel-2. The seasonal difference compares observations from the same viewing track, calendar month and product versions.</p>
      <dl className="kv">{Object.entries(event.land_cover_context).map(([key, item]) =>
        <div key={key}><dt>{signalName(key)}</dt><dd>Median {num(item.median_score)} · seasonal difference {num(item.seasonal_difference)}
          <span className="kv-src">{(item.dates ?? []).join(', ')}</span></dd></div>
      )}</dl>
    </Disclosure>}
  </div>
}

const pageLength = 12
export function DynamicWorldCredit({ summary }) {
  const used = summary?.source_status?.some((s) => s.source === 'dynamic_world' && ['available', 'partial'].includes(s.status))
  return used ? <p className="caption">{summary.sources?.dynamic_world?.attribution ?? dynamicWorldCredit} <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a></p> : null
}

function ObservationDate({ observation }) {
  if (!observation.scenes?.length) return observation.date
  return <details className="history-scenes"><summary>{observation.date}</summary>
    {observation.imagery_interval && <p>Source imagery from {observation.imagery_interval.join(' to ')}.</p>}
    {observation.inference_date && <p>Inference date {observation.inference_date}.</p>}
    {observation.scenes.map((scene) => <div key={scene['system:index']}>
      <p>{observation.asset}/{scene['system:index']}</p>
      {scene.dynamicworld_algorithm_version && <p>Model {scene.dynamicworld_algorithm_version}</p>}
      {scene.qa_algorithm_version && <p>Cloud mask {scene.qa_algorithm_version}</p>}
      {scene.PROCESSING_BASELINE && <p>Sentinel-2 processing baseline {scene.PROCESSING_BASELINE}</p>}
    </div>)}
  </details>
}

function ObservationTable({ records, signal }) {
  const [page, setPage] = useState(0)
  const lastPage = Math.ceil(records.length / pageLength) - 1
  const shown = records.slice(page * pageLength, (page + 1) * pageLength)
  return <>
    <table className="obs-table"><thead><tr><th>Date</th><th>Value</th><th>Cell seen</th></tr></thead>
      <tbody>{shown.map((o) => <tr key={o.date}><th><ObservationDate observation={o} /></th>
        <td>{num(o.values?.[signal])}</td><td>{Number.isFinite(o.coverage) ? fmtPct0(o.coverage) : 'Unknown'}</td>
      </tr>)}</tbody>
    </table>
    {lastPage > 0 && <div className="history-pages">
      <button type="button" disabled={!page} onClick={() => setPage(page - 1)}>Earlier rows</button>
      <span>{page + 1} / {lastPage + 1}</span>
      <button type="button" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>Later rows</button>
    </div>}
  </>
}

function Observations({ detail }) {
  const [selected, setSelected] = useState('')
  const channels = useMemo(() => {
    const channels = new Map()
    for (const s of detail.series ?? []) {
      const key = JSON.stringify([s.source, s.track, s.signal])
      channels.set(key, { ...s, key })
    }
    for (const r of detail.observations ?? []) {
      for (const signal of Object.keys(r.values ?? {})) {
        const key = JSON.stringify([r.source, r.track, signal])
        if (!channels.has(key)) channels.set(key, { key, signal, source: r.source, track: r.track })
      }
    }
    return [...channels.values()]
  }, [detail])
  const channel = channels.find((c) => c.key === selected) ?? channels[0]
  const rows = useMemo(() => channel ? (detail.observations ?? [])
    .filter((o) => o.source === channel.source && o.track === channel.track).sort((a, b) => a.date.localeCompare(b.date)) : [], [detail, channel])
  if (!channel) return <p className="caption">No usable observation series was recorded.</p>
  const signal = channel.signal
  const points = rows.filter((r) => Number.isFinite(r.values?.[signal]))
  const values = points.map((r) => r.values[signal])
  const min = Math.min(...values), max = Math.max(...values)
  const t0 = Date.parse(rows[0]?.date), t1 = Date.parse(rows.at(-1)?.date)
  const first = rows[0]
  return <div className="history-detail">
    <label>Signal and source track<select value={channel.key} onChange={(e) => setSelected(e.target.value)}>
      {channels.map((c) => <option key={c.key} value={c.key}>{signalName(c.signal)} · {sourceName(c.source)} · {c.track}</option>)}
    </select></label>
    <p className="caption">{points.length} usable dates of {rows.length} acquisitions.
      {Number.isFinite(first?.resolution_m) && <> Source resolution {first.resolution_m} m.</>}
      {channel.status && <> {humanize(channel.status)}.</>}
    </p>
    {points.length > 0 && <figure className="history-trace">
      <svg viewBox="0 0 300 78" role="img" aria-label={`${signalName(signal)} across ${points.length} dates, range ${num(min)} to ${num(max)}.`}>
        {points.map((r) => <circle key={r.date} r="2" cx={5 + 290 * (Date.parse(r.date) - t0) / (t1 - t0 || 1)}
          cy={max === min ? 38 : 72 - 66 * (r.values[signal] - min) / (max - min)} />)}
      </svg>
      <figcaption><span>{rows[0].date}</span><span>{rows.at(-1).date}</span></figcaption>
    </figure>}
    {first?.quality && <p className="caption">{first.quality}</p>}
    {channel.source === 'dynamic_world' && <p className="caption">These scores describe model confidence from the Sentinel-2 scene. Physical cover area requires dated surveys.</p>}

    {channel.reason && <p className="caption">{humanize(channel.reason)}.</p>}
    <Disclosure label="Dated measurements"><ObservationTable key={channel.key} records={rows} signal={signal} /></Disclosure>
  </div>
}

function CellReplay({ resultId, unit, summary }) {
  const [draft, setDraft] = useState(() => ({ start: summary.period[0], end: summary.period[1],
    mode: 'prospective', as_of: previousDay(summary.period[1]) }))
  const [query, setQuery] = useState(null)
  const [replay, setReplay] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (!query) return
    const ctl = new AbortController()
    getChangeCell(resultId, unit, ctl.signal, query).then((data) => {
      if (!ctl.signal.aborted) setReplay(data)
    }).catch(() => { if (!ctl.signal.aborted) setFailed(true) })
    return () => ctl.abort()
  }, [query, resultId, unit])
  const edit = (k, value) => {
    setDraft({ ...draft, [k]: value }); setQuery(null); setFailed(false); setReplay(null)
  }
  const error = replayError(draft, summary)
  return <div className="history-detail">
    <form className="history-detail" onSubmit={(e) => {
      e.preventDefault()
      if (!error) { setFailed(false); setReplay(null); setQuery({ ...draft }) }
    }}>
      <label>Evidence mode<select value={draft.mode} onChange={(e) => edit('mode', e.target.value)}>
        <option value="prospective">As observed during the interval</option>
        <option value="retrospective">Allow later evidence of persistence or recovery</option>
      </select></label>
      {[['start', 'Interval start'], ['end', 'Interval end (exclusive)'], ['as_of', 'Use evidence through']].map(([key, label]) =>
        <label key={key}>{label}<input type="date" value={draft[key]} min={summary.training_period[0]}
          max={key === 'end' ? summary.period[1] : previousDay(summary.period[1])}
          onChange={(e) => edit(key, e.target.value)} required /></label>)}
      {error && <p role="status">{error}</p>}
      <button className="chip" disabled={!!error || (!!query && !replay && !failed)}>Replay cell</button>
    </form>
    {query && !replay && <p role="status">{failed ? 'The replay could not be loaded.' : 'Replaying archived observations…'}</p>}
    {replay && query && <div className="history-detail">
      <p className="lead">Cell replay · {stateName(replay.state)}</p>
      <p className="caption">{humanize(replay.mode ?? query.mode)} from {periodText([query.start, query.end])}.
        {' '}Evidence through {replay.as_of ?? query.as_of}. Map marks show the original monitoring interval.</p>
      <Events events={replay.events ?? empty} />
      <Observations detail={{ ...replay, observations: (replay.observations ?? []).filter((r) => r.date <= (replay.as_of ?? query.as_of)) }} />
    </div>}
  </div>
}

function ComparisonForm({ summary, window, onSubmit, onEdit, waiting }) {
  const [draft, setDraft] = useState(() => initialComparison(summary, window))
  const error = compareError(draft, summary)
  const edit = (key, value) => { setDraft({ ...draft, [key]: value }); onEdit() }
  return <form className="history-detail" onSubmit={(e) => { e.preventDefault(); if (!error) onSubmit(draft) }}>
    <label>Measured signal<select value={draft.signal} onChange={(e) => edit('signal', e.target.value)}>
      {(summary.signals ?? []).map((s) => <option key={s} value={s}>{signalName(s)}</option>)}
    </select></label>
    {['before', 'after'].map((which) => <fieldset key={which} className="history-dates">
      <legend>{which === 'before' ? 'First period' : 'Second period'}</legend>
      {['start', 'end'].map((edge) => <label key={edge}>{edge === 'start' ? 'From' : 'Until (exclusive)'}
        <input type="date" required value={draft[which + '_' + edge]} min={summary.training_period?.[0]} max={summary.period?.[1]}
          onChange={(e) => edit(which + '_' + edge, e.target.value)} />
      </label>)}
    </fieldset>)}
    {error && <p className="caption" role="status">{error}</p>}
    <button className="chip" disabled={!!error || waiting}>{waiting ? 'Comparing…' : 'Compare periods'}</button>
  </form>
}

function HistoryKey({ comparison, query, summary }) {
  const marks = comparison ? [['Higher signal', color.select], ['Lower signal', 'stripe']]
    : [['Detected', color.trust.experimental], ['Candidate', 'stripe']]
  return <div className="legend change-dock">
    <p className="caption">{comparison ? (query ? `${signalName(query.signal)} · ${periodText([query.before_start, query.before_end])} vs ${periodText([query.after_start, query.after_end])}` : 'Choose two periods to map their difference.')
      : `Signal episodes from ${periodText(summary.period)}`}</p>
    <div className="legend-foot chg-key">
      {[...marks, ['Insufficient', 'hatch']].map(([label, swatch]) => <span key={label}>
        <i className={'swatch' + (['stripe', 'hatch'].includes(swatch) ? ' swatch-' + swatch : '')}
          style={{ backgroundColor: swatch.startsWith('#') ? swatch : undefined, '--hue': color.select }} aria-hidden="true" />
        {label}
      </span>)}
    </div>
  </div>
}

function CellPicker({ cells, current, onUnit }) {
  const [entry, setEntry] = useState(current == null ? '' : String(current))
  const [error, setError] = useState(false)
  const select = (e) => {
    e.preventDefault()
    const cell = cells.find((c) => String(c.props.unit_index) === entry.trim())
    setError(!cell)
    if (cell) onUnit(cell.props.unit_index)
  }
  const firstEvent = cells.find((c) => c.props.event_count > 0)
  return <form className="history-detail" onSubmit={select}>
    <label>Inspect a cell on the map or enter its index
      <input inputMode="numeric" value={entry} onChange={(e) => { setEntry(e.target.value); setError(false) }}
        placeholder={String(cells[0].props.unit_index)} />
    </label>
    <div className="history-pages"><button type="submit">Open cell</button>
      {firstEvent && <button type="button" onClick={() => onUnit(firstEvent.props.unit_index)}>First cell with episodes</button>}
    </div>
    {error && <p role="alert">No mapped cell has this index.</p>}
  </form>
}

function CellComparison({ cell }) {
  if (!cell) return null
  return <div className="history-detail"><p>{stateName(cell.state)}</p>
    {Number.isFinite(cell.delta) && <dl className="kv">
      <div><dt>Signal difference</dt><dd>{num(cell.delta)} · {signalName(cell.signal)}</dd></div>
      <div><dt>First median</dt><dd>{num(cell.median_before)} across {cell.n_before} dates</dd></div>
      <div><dt>Second median</dt><dd>{num(cell.median_after)} across {cell.n_after} dates</dd></div>
      <div><dt>Track</dt><dd>{sourceName(cell.source)} · {cell.track}</dd></div>
    </dl>}
  </div>
}

export default function ChangeHistory({ host, wrapper, resultId, window, bbox, map, mobile, onInspect, zoneTypes }) {
  const summary = summaryOf(wrapper)
  const [mode, setMode] = useState('history')
  const [cells, setCells] = useState(null)
  const [mapError, setMapError] = useState(false)
  const [unit, setUnit] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState(false)
  const [query, setQuery] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [compareFailed, setCompareFailed] = useState(false)
  const [split, setSplit] = useState(0.5)
  const pics = useYearPictures(resultId, mode === 'pictures')
  const choosingDates = mode === 'compare'
  const pictures = mode === 'pictures'

  useEffect(() => {
    if (!resultId || !bbox) return
    const ctl = new AbortController()
    getChangeFeatures(resultId, ctl.signal).then((fc) => {
      if (!ctl.signal.aborted) setCells(unitCells(fc, bbox))
    }).catch(() => { if (!ctl.signal.aborted) setMapError(true) })
    return () => ctl.abort()
  }, [resultId, bbox])

  useEffect(() => {
    if (unit == null || !resultId || mode !== 'history') return
    const ctl = new AbortController()
    setDetail(null); setDetailError(false)
    getChangeCell(resultId, unit, ctl.signal).then((data) => {
      if (!ctl.signal.aborted) setDetail(data)
    }).catch(() => { if (!ctl.signal.aborted) setDetailError(true) })
    return () => ctl.abort()
  }, [unit, resultId, mode])

  useEffect(() => {
    if (!query || !resultId || !bbox) return
    const ctl = new AbortController()
    compareChange(resultId, query, ctl.signal).then((fc) => {
      if (!ctl.signal.aborted) setComparison({ query, cells: unitCells(fc, bbox) })
    }).catch(() => { if (!ctl.signal.aborted) setCompareFailed(true) })
    return () => ctl.abort()
  }, [query, resultId, bbox])

  const visible = choosingDates ? (query && comparison?.query === query ? comparison.cells : empty) : cells
  useEffect(() => {
    if (pictures || !map || !bbox || !visible?.length) return
    const project = toUnit(bbox)
    const click = (e) => {
      const cell = cellAt(visible, project([e.lngLat.lng, e.lngLat.lat]))
      if (cell) { setUnit(cell.props.unit_index); onInspect() }
    }
    map.on('click', click)
    return () => map.off('click', click)
  }, [pictures, map, bbox, visible, onInspect])

  const focused = visible?.find((c) => c.props.unit_index === unit)
  const picPair = pics.pair
  const changeMode = (m) => { setMode(m); setQuery(null); setComparison(null); setCompareFailed(false) }
  const submit = (draft) => { setComparison(null); setCompareFailed(false); setQuery({ ...draft }) }
  const invalidate = () => { setComparison(null); setQuery(null); setCompareFailed(false) }
  const dock = pictures ? (picPair && <ChangeDock picturesOnly choices={[]} pair={picPair}
    years={pics.imagery.years} onPair={pics.setPair} status={Object.fromEntries(Object.entries(pics.imgs).map(([y, v]) => [y, v.state]))} />)
    : summary?.period && <HistoryKey summary={summary} comparison={choosingDates} query={comparison?.query} />

  return <>
    {!mobile && dock}
    {map && bbox && (!pictures || picPair) && <SwipeOverlay map={map} bbox={bbox}
      cells={pictures ? null : visible} selectedId={focused?.id} classify={historyMark} pictures={pictures}
      before={picPair && { year: picPair[0], ...pics.imgs[picPair[0]] }}
      after={picPair && { year: picPair[1], ...pics.imgs[picPair[1]] }} split={split} onSplit={setSplit} />}
    {host && createPortal(<section className="history-panel">
      <div className="chrow-head"><h3 className="section-title">Change history</h3><TrustBadge of={wrapper} compact /></div>
      <p className="lead">{historyText(wrapper)}</p>
      {summary && <>
        <StatusCounts summary={summary} />
        <DynamicWorldCredit summary={summary} />
        <p className="caption">Monitoring from {periodText(summary.period)}. {summary.grid_cell_m && <>{summary.grid_cell_m} m reporting cells.</>}</p>
        <SurveyMeasures surveys={summary.survey_measurements} provenance={summary.survey_sources} />
        {resultId && zoneTypes?.length > 0 && <Disclosure label="Coverage by boundary">
          <ChangeZone resultId={resultId} types={zoneTypes} />
        </Disclosure>}
        <Disclosure label="Baseline and coverage">
          <p>Local reference period from {periodText(summary.training_period)}.</p>
          <dl className="kv">{(summary.source_status ?? []).map((s) => <div key={s.source}>
            <dt>{sourceName(s.source)}</dt><dd>{humanize(s.status)} · {s.tiles} spatial tiles</dd>
          </div>)}</dl>
          {summary.support_area_m2 && <dl className="kv">{Object.entries(summary.support_area_m2).map(([k, area]) =>
            <div key={k}><dt>{stateName(k)}</dt><dd>{amount(area)} of reporting footprint</dd></div>
          )}</dl>}
        </Disclosure>
      </>}
      {summary && resultId && <>
        <div className="seg" role="group" aria-label="Change view">{Object.entries(modeNames).map(([k, label]) =>
          <button key={k} type="button" className={k === mode ? 'on' : ''} aria-pressed={mode === k} onClick={() => { if (k !== mode) changeMode(k) }}>{label}</button>
        )}</div>
        {choosingDates && <>
          <ComparisonForm summary={summary} window={window} onSubmit={submit} onEdit={invalidate} waiting={!!query && !comparison && !compareFailed} />
          <p className="caption">Each cell compares the median signal on the same source track. Small differences may reflect measurement noise.</p>
          {compareFailed && <p role="alert">The comparison could not be loaded. Submit the periods again to retry.</p>}
        </>}
        {mobile && dock && <div className="dock-inline">{dock}</div>}
        {pictures && !picPair && <p role="status">{pics.imagery?.failed ? 'The imagery years could not be loaded.' : pics.imagery ? 'Two imagery years are unavailable.' : 'Loading imagery years…'}</p>}
        {!pictures && <>
          {mapError && !choosingDates && <p role="alert">The history cell map could not be loaded.</p>}
          {!!visible?.length && <CellPicker key={unit ?? 'none'} cells={visible} current={unit} onUnit={setUnit} />}
          {focused && (choosingDates ? <CellComparison cell={focused.props} /> : <>
            <p className="lead">{stateName(focused.props.state)}</p>
            <SurveyMeasures surveys={focused.props.survey_measurements} provenance={summary.survey_sources} />
            {detailError ? <p role="alert">The cell record could not be loaded.</p>
              : detail?.unit_index !== unit ? <p role="status">Loading cell evidence…</p>
              : <><p className="caption">Mapped assessment from {periodText(summary.period)}{detail.as_of && <> · evidence through {detail.as_of}</>}.</p>
                <Events key={unit} events={detail.events ?? empty} /><Observations key={detail.cell_id} detail={detail} />
                <Disclosure key={'replay' + unit} label="Replay this cell for other dates">
                  <CellReplay resultId={resultId} unit={unit} summary={summary} />
                </Disclosure></>}
          </>)}
        </>}
      </>}
    </section>, host)}
  </>
}
