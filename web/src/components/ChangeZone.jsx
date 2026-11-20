import { useEffect, useState } from 'react'
import { getChangeZone, getUnitPage } from '../lib/api.js'
import { humanize } from '../lib/contract.js'
import SurveyMeasures from './SurveyMeasures.jsx'
import { num, stateName } from '../lib/changeHistory.js'

const size = 20
function Units({ resultId, type }) {
  const [offset, setOffset] = useState(0)
  const [id, setId] = useState('')
  const [page, setPage] = useState(null)
  const [zone, setZone] = useState(null)
  useEffect(() => {
    const ctl = new AbortController()
    getUnitPage(resultId, type, offset, size, ctl.signal)
      .then((r) => { if (!ctl.signal.aborted) setPage({ ...r, offset }) })
      .catch(() => { if (!ctl.signal.aborted) setPage({ offset, error: true }) })
    return () => ctl.abort()
  }, [resultId, type, offset])
  useEffect(() => {
    if (!id) return
    const ctl = new AbortController()
    getChangeZone(resultId, type, id, ctl.signal)
      .then((r) => { if (!ctl.signal.aborted) setZone({ ...r, id }) })
      .catch(() => { if (!ctl.signal.aborted) setZone({ id, error: true }) })
    return () => ctl.abort()
  }, [resultId, type, id])
  if (page?.offset !== offset) return <p>Loading boundaries…</p>
  if (page.error) return <p>Boundary list unavailable.</p>
  const jump = (off) => { setId(''); setZone(null); setOffset(off) }
  return <>
    <label>Boundary<select value={id} onChange={(e) => setId(e.target.value)}>
      <option value="">Select a boundary</option>
      {page.units.map((u) => <option key={u.unit_id} value={u.unit_id}>{u.unit_name ?? u.unit_id}</option>)}
    </select></label>
    {page.n_units > size && <div className="history-pages">
      <button type="button" disabled={!offset} onClick={() => jump(offset - size)}>Previous</button>
      <span>{offset + 1}–{Math.min(page.n_units, offset + size)} of {page.n_units}</span>
      <button type="button" disabled={offset + size >= page.n_units} onClick={() => jump(offset + size)}>Next</button>
    </div>}
    {id && (zone?.id !== id ? <p>Loading coverage…</p> : zone.error ? <p>Coverage unavailable for this boundary.</p>
      : <><p className="caption">Area inside this boundary by reporting-cell status.</p><dl className="kv">
        {Object.entries(zone.support_area_m2 ?? {}).map(([k, v]) => <div key={k}><dt>{stateName(k)}</dt><dd>{num(v)} m²</dd></div>)}
        {Number.isFinite(zone.outside_record_m2) && <div><dt>Outside the record</dt><dd>{num(zone.outside_record_m2)} m²</dd></div>}
      </dl><SurveyMeasures surveys={zone.survey_measurements} provenance={zone.survey_sources} /></>)}
  </>
}

export default function ChangeZone({ resultId, types }) {
  const [type, setType] = useState(() => types.find((t) => t.startsWith('ward:')) ?? types[0])
  return <div className="history-detail">
    <label>Boundary layer<select value={type} onChange={(e) => setType(e.target.value)}>
      {types.map((t) => <option key={t} value={t}>{t.startsWith('ward:') ? 'Wards · ' + humanize(t.slice(5)) : humanize(t)}</option>)}
    </select></label>
    <Units key={type} resultId={resultId} type={type} />
  </div>
}
