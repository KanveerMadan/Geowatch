import { ArrowClockwise, FileText, Polygon, X } from '@phosphor-icons/react'
import { areaState, bboxAreaKm2, fmtKm2 } from '../lib/geo.js'
import { failureText, gapText } from '../lib/stages.js'
import { Disclosure, StageList } from './PanelBits.jsx'

/** The top of every tab: the place, its area against the limit, the one
 *  action, and the job's state while it runs or if it stopped. */
export default function AreaStatus({ place, bbox, maxKm2, job, wards, onAnalyse, onRetry, onRedraw, onClear, reportHref }) {
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
  const running = job && (job.status === 'queued' || job.status === 'running')
  return (
    <>
      <header className="panel-head">
        <h2 className="place">{place?.name ?? 'Drawn area'}</h2>
        <div className="head-actions">
          <button type="button" className="btn-clear" onClick={onClear} aria-label="Clear area (Esc)">
            <X size={13} aria-hidden="true" /> Clear area
          </button>
          {reportHref && (
            <a className="btn-clear" href={reportHref} target="_blank" rel="noopener">
              <FileText size={13} aria-hidden="true" /> Area report
            </a>
          )}
        </div>
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
          <p className="caption">
            {st === 'warn' ? `Near the ${maxKm2} km² limit. ` : ''}Takes a few minutes. Keep exploring while it runs.
            {wards && <> Wards from {wards.name} will be ranked.</>}
          </p>
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
    </>
  )
}
