import { color } from '../design/tokens.js'
import { changeRows, changeSummary } from '../lib/change.js'
import { groupState, outputsOf } from '../lib/stages.js'
import TrustBadge from './TrustBadge.jsx'
import { Skeleton } from './bits.jsx'
import { Disclosure, Reveal } from './PanelBits.jsx'

const num3 = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 3 })

function Counts({ r }) {
  // Up and down out of the cells judged; the split bar is to scale.
  const w = (k) => `${(100 * k) / Math.max(1, r.judged)}%`
  const hue = color.data[r.key] ?? color.select
  return (
    <div className="chg-counts">
      <span className="chg-split" aria-hidden="true">
        <span className="chg-up" style={{ width: w(r.increase), background: hue }} />
        <span className="chg-down" style={{ width: w(r.decrease), '--hue': hue }} />
      </span>
      <dl className="chg-kv">
        <div><dt>Up</dt><dd className="num">{r.increase}</dd></div>
        <div><dt>Down</dt><dd className="num">{r.decrease}</dd></div>
        <div><dt>No change</dt><dd className="num">{r.unchanged}</dd></div>
        {r.unjudged > 0 && <div><dt>Not judged</dt><dd className="num">{r.unjudged}</dd></div>}
      </dl>
    </div>
  )
}

function ChangeRow({ r, chosen, onChoose }) {
  const hue = color.data[r.key] ?? color.select
  if (!r.measured) {
    return (
      <li className="chrow frow-absent">
        <div className="chrow-head">
          <i className="swatch swatch-hatch" aria-hidden="true" />
          <span className="frow-name">{r.name}</span>
          <span className="frow-absent-text">{r.text}</span>
        </div>
        <TrustBadge of={{ validation_status: r.trust.key }} compact />
      </li>
    )
  }
  return (
    <li className={`chrow${chosen ? ' frow-on' : ''}`}>
      <button type="button" className="chrow-main" aria-pressed={chosen} onClick={() => onChoose(r.key)}
        title={`Show ${r.name.toLowerCase()} change on the map`}>
        <span className="chrow-head">
          <i className="swatch" style={{ background: hue }} aria-hidden="true" />
          <span className="frow-name">{r.name}</span>
          <span className="caption num">{r.years ? `${r.years[0]} to ${r.years[1]}` : ''}</span>
        </span>
        {r.judged > 0 ? <Counts r={r} /> : <span className="frow-absent-text">Not judged: {r.unjudgedWhy.toLowerCase()}.</span>}
      </button>
      <TrustBadge of={{ validation_status: r.trust.key, validation_scope: r.trust.scope }} compact />
    </li>
  )
}

export default function ChangePanel({ job, fraction, onFraction, cellsNote }) {
  if (!job) return null
  const outputs = outputsOf(job)
  const state = groupState(job, 'change')
  const rows = changeRows(outputs.change)
  return (
    <section aria-busy={state === 'waiting'}>
      <h3 className="section-title">Change over time</h3>
      {state === 'waiting' && (
        <>
          <Skeleton h={64} />
          <div className="skeleton-rows">{[0, 1, 2].map((i) => <Skeleton key={i} h={72} />)}</div>
        </>
      )}
      {state === 'failed' && !outputs.change && (
        <p className="muted">Change could not be measured in this run. Retry to try again.</p>
      )}
      {outputs.change && (
        <Reveal k="change">
          <p className="lead summary">{changeSummary(outputs.change)}</p>
          <ul className="chrows">
            {rows.map((r) => <ChangeRow key={r.key} r={r} chosen={r.key === fraction} onChoose={onFraction} />)}
          </ul>
          <p className="caption">
            Counts are 100 m cells. A cell counts as changed only when the difference is over three times the noise between two pictures of the same year.
          </p>
          {cellsNote && <p className="caption">{cellsNote}</p>}
          <Disclosure label="Method and sources">
            <dl className="kv">
              {rows.filter((r) => r.measured).map((r) => (
                <div key={r.key}>
                  <dt>{r.name}</dt>
                  <dd>
                    Change threshold <span className="num">{num3.format(r.threshold)}</span> ({r.k} × noise <span className="num">{num3.format(r.noise)}</span>).
                    {' '}{r.judged} of {r.cells} cells were seen well enough in both years.
                    {r.method && <span className="kv-src">{r.method}</span>}
                    {r.sources.map((x) => <span key={x} className="kv-src">{x}</span>)}
                  </dd>
                </div>
              ))}
              {rows.filter((r) => !r.measured).map((r) => (
                <div key={r.key}><dt>{r.name}</dt><dd>{r.text}{r.reason && <>: {r.reason}</>}.</dd></div>
              ))}
            </dl>
          </Disclosure>
        </Reveal>
      )}
    </section>
  )
}
