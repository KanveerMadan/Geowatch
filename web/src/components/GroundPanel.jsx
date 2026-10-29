import { useState } from 'react'
import { AnimatePresence, motion as m, useReducedMotion } from 'motion/react'
import { ArrowClockwise, CaretDown, Check, CircleNotch, Warning, X, Polygon } from '@phosphor-icons/react'
import { color, motion } from '../design/tokens.js'
import { fmtPct0, fmtPct1, fractionRows, groundSummary, readOutput } from '../lib/contract.js'
import { areaState, bboxAreaKm2, fmtArea, fmtKm2 } from '../lib/geo.js'
import { areaNotes, sourcesOf } from '../lib/notes.js'
import { failureText, gapText, groupState, outputsOf, stageRows } from '../lib/stages.js'
import TrustBadge from './TrustBadge.jsx'
import { CountUp, Skeleton } from './bits.jsx'

const fmtPct = fmtPct1

function Reveal({ children, k }) {
  const reduce = useReducedMotion()
  return (
    <m.div key={k} initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      transition={reduce ? { duration: motion.reduced.duration } : { duration: motion.duration.slow, ease: motion.ease }}>
      {children}
    </m.div>
  )
}

function Disclosure({ label, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="disclosure">
      <button type="button" className="disclosure-btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <CaretDown size={12} className={open ? 'rot' : ''} aria-hidden="true" /> {label}
      </button>
      {open && <div className="disclosure-body">{children}</div>}
    </div>
  )
}

function StageList({ job }) {
  const rows = stageRows(job)
  const icon = {
    done: <Check size={13} weight="bold" />,
    running: <CircleNotch size={13} className="spin-slow" />,
    failed: <Warning size={13} weight="bold" />,
    timeout: <Warning size={13} weight="bold" />,
    waiting: <span className="dot-wait" />,
  }
  const word = { failed: 'failed', timeout: 'timed out' }
  return (
    <ol className="stages" aria-label="Analysis steps">
      {rows.map((r) => (
        <li key={r.key} className={`stage stage-${r.state}`}>
          <span className="stage-icon" aria-hidden="true">{icon[r.state]}</span>
          <span>{r.text}</span>
          {word[r.state] && <span className="stage-word">{word[r.state]}</span>}
          <span className="sr-only">{r.state}</span>
        </li>
      ))}
    </ol>
  )
}

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

export default function GroundPanel({ place, bbox, maxKm2, job, onAnalyse, onRetry, onRedraw, fraction, onFraction, cell, onCloseCell, cellsNote, onClear }) {
  if (!bbox) {
    return (
      <div className="panel-empty">
        <Polygon size={28} weight="light" aria-hidden="true" />
        <p className="lead">Search a place or draw an area</p>
        <p className="muted">Ground cover, flood susceptibility and change, for anywhere on Earth.</p>
      </div>
    )
  }
  const km2 = bboxAreaKm2(bbox)
  const st = areaState(km2, maxKm2)
  const outputs = outputsOf(job)
  const fr = groupState(job, 'fractions')
  const result = job?.result
  const rows = fractionRows(outputs.fractions)
  const notes = result ? areaNotes(result) : []
  const running = job && (job.status === 'queued' || job.status === 'running')

  return (
    <>
      <header className="panel-head">
        <h2 className="place">{place?.name ?? 'Drawn area'}</h2>
        <button type="button" className="btn-clear" onClick={onClear} aria-label="Clear area (Esc)">
          <X size={13} aria-hidden="true" /> Clear area
        </button>
        <p className="muted">
          {place?.region && <>{place.region}<span aria-hidden="true"> · </span></>}
          <span className={`area area-${st}`}>{fmtKm2(km2)}</span>
        </p>
      </header>

      {!job && st === 'over' && (
        <section className="callout callout-danger">
          <p>This area is {fmtKm2(km2)}. One analysis covers up to {maxKm2} km², so it finishes in minutes rather than hours.</p>
          <button type="button" className="btn" onClick={onRedraw}>Draw a smaller area</button>
        </section>
      )}
      {!job && st !== 'over' && (
        <section className="cta-block">
          <button type="button" className="btn btn-primary" onClick={onAnalyse}>Analyse this area</button>
          <p className="caption">{st === 'warn' ? `Near the ${maxKm2} km² limit. ` : ''}Takes a few minutes. Keep exploring while it runs.</p>
        </section>
      )}

      {running && (
        <section aria-live="polite">
          <p className="lead">{job.status === 'queued' ? 'Waiting for a free slot…' : 'Analysing this area…'}</p>
          <StageList job={job} />
        </section>
      )}
      {job?.status === 'failed' && (
        <section className="callout callout-danger" role="alert">
          <p>{failureText(job)}</p>
          <button type="button" className="btn" onClick={onRetry}><ArrowClockwise size={14} aria-hidden="true" /> Retry</button>
          <Disclosure label="Steps"><StageList job={job} /></Disclosure>
        </section>
      )}
      {job?.status === 'complete' && !job.stored && (
        <section className="callout callout-warn" role="status">
          <p>{gapText(job)}</p>
          <button type="button" className="btn" onClick={onRetry}><ArrowClockwise size={14} aria-hidden="true" /> Retry</button>
        </section>
      )}

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
