import { AnimatePresence } from 'motion/react'
import { X } from '@phosphor-icons/react'
import { color } from '../design/tokens.js'
import { fmtPct0, fmtPct1, fractionRows, groundSummary, readOutput } from '../lib/contract.js'
import { fmtArea } from '../lib/geo.js'
import { areaNotes, sourcesOf } from '../lib/notes.js'
import { groupState, outputsOf } from '../lib/stages.js'
import TrustBadge from './TrustBadge.jsx'
import { CountUp, Skeleton } from './bits.jsx'
import { Disclosure, Reveal } from './PanelBits.jsx'

const fmtPct = fmtPct1

function FractionRow({ r, chosen, onChoose }) {
  const hue = color.data[r.key] ?? color.select
  return (
    <li className={`frow${r.measured ? '' : ' frow-absent'}${chosen ? ' frow-on' : ''}`}>
      {r.measured ? (
        <button type="button" className="frow-main" aria-pressed={chosen} onClick={() => onChoose(r.key)}
          title={`Show ${r.name.toLowerCase()} on the map`}>
          <i className="swatch" style={{ background: hue }} aria-hidden="true" />
          <span className="frow-name">{r.name}</span>
          <span className="frow-val"><CountUp value={r.value} format={fmtPct} /></span>
          <span className="frow-bar" aria-hidden="true"><span style={{ background: hue, transform: `scaleX(${r.value})` }} /></span>
        </button>
      ) : (
        <div className="frow-main">
          <i className="swatch swatch-hatch" aria-hidden="true" />
          <span className="frow-name">{r.name}</span>
          <span className="frow-val frow-absent-text">{r.display}</span>
        </div>
      )}
      <TrustBadge of={{ validation_status: r.trust.key, validation_scope: r.trust.scope }} compact />
    </li>
  )
}

/** The figures behind the rows, one click deeper. */
function FractionFigures({ rows }) {
  return (
    <Disclosure label="Figures and sources">
      <dl className="kv">
        {rows.map((r) => (
          <div key={r.key}>
            <dt>{r.name}</dt>
            <dd>
              {r.measured
                ? <>{fmtPct(r.value)} of the area{r.coverage != null && <>, from the {fmtPct0(r.coverage)} that was observed</>}.</>
                : <>{r.display}{r.reason && <>: {r.reason}</>}.</>}
              {r.sources.filter((x) => !x.startsWith('none')).map((x) => <span key={x} className="kv-src">{x}</span>)}
            </dd>
          </div>
        ))}
      </dl>
    </Disclosure>
  )
}

function CellBreakdown({ cell, onClose }) {
  if (!cell) return null
  if (cell.loading) return <div className="cell-box"><Skeleton h={14} w="40%" /><Skeleton h={64} /></div>
  if (cell.error) {
    return <div className="cell-box"><p className="muted">This cell's breakdown could not be loaded. Click it again to retry.</p></div>
  }
  const rows = fractionRows(cell.outputs?.fractions)
  const seen = readOutput(cell.outputs?.observability?.observed_fraction)
  return (
    <div className="cell-box">
      <div className="cell-head">
        <h3>{cell.unit_name || 'Selected cell'}</h3>
        <span className="muted num">{fmtArea((cell.area_m2 ?? 0) / 1e6)}</span>
        <button type="button" className="icon-btn" aria-label="Close cell breakdown" onClick={onClose}><X size={14} /></button>
      </div>
      <ul className="mini-rows">
        {rows.map((r) => (
          <li key={r.key}>
            <i className={`swatch${r.measured ? '' : ' swatch-hatch'}`} style={r.measured ? { background: color.data[r.key] } : undefined} aria-hidden="true" />
            <span>{r.name}</span>
            <span className={`num${r.measured ? '' : ' frow-absent-text'}`}>{r.display}</span>
            <TrustBadge of={{ validation_status: r.trust.key, validation_scope: r.trust.scope }} compact />
          </li>
        ))}
      </ul>
      {seen.measured && <p className="caption">Imagery saw {fmtPct0(seen.value)} of this cell clearly.</p>}
    </div>
  )
}

export default function GroundPanel({ job, fraction, onFraction, cell, onCloseCell, cellsNote }) {
  if (!job) return null
  const outputs = outputsOf(job)
  const fr = groupState(job, 'fractions')
  const result = job?.result
  const rows = fractionRows(outputs.fractions)
  const notes = result ? areaNotes(result) : []
  const running = job.status === 'queued' || job.status === 'running'

  return (
    <>
      {job && (
        <section className="ground" aria-busy={fr === 'waiting'}>
          <h3 className="section-title">Ground cover</h3>
          {fr === 'waiting' && (
            <>
              <Skeleton h={44} />
              <div className="skeleton-rows">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} h={36} />)}</div>
            </>
          )}
          {fr === 'failed' && !outputs.fractions && (
            <p className="muted">Ground cover could not be measured in this run. Retry to try again.</p>
          )}
          {fr === 'ready' && (
            <Reveal k="fractions">
              <p className="lead summary">{groundSummary(outputs.fractions)}</p>
              <ul className="frows">
                {rows.map((r) => <FractionRow key={r.key} r={r} chosen={r.key === fraction} onChoose={onFraction} />)}
              </ul>
              <FractionFigures rows={rows} />
            </Reveal>
          )}
          {cellsNote && <p className="caption">{cellsNote}</p>}
        </section>
      )}

      <AnimatePresence>{cell && <Reveal k={`cell-${cell.unit_id}`}><CellBreakdown cell={cell} onClose={onCloseCell} /></Reveal>}</AnimatePresence>

      {job && (
        <section>
          <h3 className="section-title">About this area</h3>
          {!result && (running
            ? <div className="skeleton-rows">{[0, 1, 2].map((i) => <Skeleton key={i} h={34} />)}</div>
            : <p className="muted">Notes appear when the analysis finishes.</p>)}
          {result && (
            <Reveal k="notes">
              <ul className="notes">
                {notes.map((n) => (
                  <li key={n.id} className={`note note-${n.tone}`}>
                    <p>{n.text}{n.trust && <> <TrustBadge of={n.trust} compact /></>}</p>
                    {n.details.length > 0 && (
                      <Disclosure label="Figures">
                        <dl className="kv">{n.details.map(([k, v], i) => <div key={i}><dt>{k}</dt><dd className="num">{v}</dd></div>)}</dl>
                      </Disclosure>
                    )}
                  </li>
                ))}
              </ul>
              <Disclosure label="Data sources">
                <ul className="sources" translate="no">{sourcesOf(outputs.fractions).map((s) => <li key={s}>{s}</li>)}</ul>
                <p className="caption">Result {result.result_id ?? 'not stored'}, version {result.model_version?.version_id?.slice(0, 12)}</p>
              </Disclosure>
            </Reveal>
          )}
        </section>
      )}
    </>
  )
}
