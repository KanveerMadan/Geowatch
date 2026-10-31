import { color } from '../design/tokens.js'
import { TIER_TEXT, floodName, floodRows, floodSummary, rankWards } from '../lib/flood.js'
import { groupState, outputsOf } from '../lib/stages.js'
import TrustBadge from './TrustBadge.jsx'
import { Skeleton } from './bits.jsx'
import { Disclosure, Reveal } from './PanelBits.jsx'

const score = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const VERDICT = { passed: 'passed', validated: 'passed', failed: 'did not pass', 'not-run': 'not run' }
const WARDS_SHOWN = 8

function TierMeter({ tier }) {
  // Five steps, filled up to the tier: a position on a fixed scale, not a bar
  // of an amount, so it reads the same for every flood type.
  const n = ['very_low', 'low', 'moderate', 'high', 'very_high'].indexOf(tier) + 1
  return (
    <span className="tier-meter" aria-hidden="true">
      {[1, 2, 3, 4, 5].map((i) => <i key={i} style={i <= n ? { background: color.flood[tier] } : undefined} />)}
    </span>
  )
}

function FloodRow({ r, chosen, onChoose }) {
  const body = (
    <>
      <span className="flrow-name">{r.name}{!r.mapped && r.measured && <span className="flrow-scope"> area-wide</span>}</span>
      <span className={`flrow-val${r.measured ? '' : ' frow-absent-text'}`}>{r.tierText}</span>
      {r.measured ? <TierMeter tier={r.tier} /> : <span />}
      <span className="flrow-blurb">{r.blurb}</span>
      {r.trust.scope && <span className="flrow-scope-note">{r.trust.scope}</span>}
    </>
  )
  return (
    <li className={`flrow${chosen ? ' frow-on' : ''}${r.measured ? '' : ' frow-absent'}${r.trust.key === 'failed' ? ' flrow-failed' : ''}`}>
      {r.mapped ? (
        <button type="button" className="flrow-main" aria-pressed={chosen} onClick={() => onChoose(r.key)}
          title={`Show ${r.long} on the map`}>{body}</button>
      ) : <div className="flrow-main">{body}</div>}
      <TrustBadge of={{ validation_status: r.trust.key, validation_scope: r.trust.scope }} compact />
    </li>
  )
}

function WardRanking({ wards, layerKey, row, loading, failed }) {
  if (!wards) {
    return (
      <p className="muted">
        No ward boundaries are loaded for this area, so there is nothing to rank. The 100 m cells on the map show where within the area.
      </p>
    )
  }
  if (loading) return <div className="skeleton-rows">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={28} />)}</div>
  if (failed) return <p className="muted">The ward ranking could not be loaded. Reload the page to try again.</p>
  if (!row?.mapped) {
    return <p className="muted">{floodName(layerKey)} is one value for the whole area here, so it cannot rank wards.</p>
  }
  const { ranked, unranked } = rankWards(wards.fc, layerKey)
  const top = ranked.slice(0, WARDS_SHOWN)
  return (
    <>
      <p className="caption">
        {ranked.length} ward{ranked.length === 1 ? '' : 's'} of {wards.name}, by mean {row.long} score over each ward’s part inside this area.
      </p>
      <ol className="wards">
        {top.map((w) => (
          <li key={w.id}>
            <span className="num ward-rank">{w.rank}</span>
            <span className="ward-name">{w.name}</span>
            <span className="ward-bar" aria-hidden="true">
              <span style={{ transform: `scaleX(${w.value})`, background: color.flood[w.tier] }} />
            </span>
            <span className="ward-tier">{TIER_TEXT[w.tier]}</span>
          </li>
        ))}
      </ol>
      {ranked.length > WARDS_SHOWN && <p className="caption">And {ranked.length - WARDS_SHOWN} more, lower.</p>}
      {unranked.length > 0 && (
        <p className="caption">Not ranked, not measured: {unranked.map((w) => w.name).join(', ')}.</p>
      )}
      <div className="row-badge">
        <span className="caption">Ranking carries the {row.name.toLowerCase()} label</span>
        <TrustBadge of={{ validation_status: row.trust.key, validation_scope: row.trust.scope }} compact />
      </div>
    </>
  )
}

export default function FloodPanel({ job, layerKey, onLayer, wards }) {
  if (!job) return null
  const outputs = outputsOf(job)
  const state = groupState(job, 'susceptibility')
  const rows = floodRows(outputs.susceptibility)
  const shown = rows.find((r) => r.key === layerKey)

  return (
    <>
      <section aria-busy={state === 'waiting'}>
        <h3 className="section-title">Flood susceptibility</h3>
        {state === 'waiting' && (
          <>
            <Skeleton h={64} />
            <div className="skeleton-rows">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} h={52} />)}</div>
          </>
        )}
        {state === 'failed' && !outputs.susceptibility && (
          <p className="muted">Flood susceptibility could not be computed in this run. Retry to try again.</p>
        )}
        {outputs.susceptibility && (
          <Reveal k="flood">
            <p className="lead summary">{floodSummary(outputs.susceptibility)}</p>
            <ul className="flrows">
              {rows.filter((r) => !r.unbuilt).map((r) => <FloodRow key={r.key} r={r} chosen={r.key === layerKey} onChoose={onLayer} />)}
              {rows.some((r) => r.unbuilt) && (
                <li className="flrow frow-absent">
                  <div className="flrow-main">
                    <span className="flrow-name">Not built yet</span>
                    <span className="flrow-val frow-absent-text">Not measured</span>
                    <span className="flrow-blurb">{rows.filter((r) => r.unbuilt).map((r) => r.name).join(', ')}.</span>
                  </div>
                  <TrustBadge of={{ validation_status: 'placeholder' }} compact />
                </li>
              )}
            </ul>
            <p className="caption">
              Susceptibility is how prone the ground is to each kind of flooding, on a five-step scale. It is not a forecast of any flood.
            </p>
            <Disclosure label="Figures and sources">
              <dl className="kv">
                {rows.filter((r) => !r.unbuilt).map((r) => (
                  <div key={r.key}>
                    <dt>{r.name}</dt>
                    <dd>
                      {r.measured
                        ? <>Score <span className="num">{score.format(r.value)}</span> of 1 ({r.tierText.toLowerCase()}), {r.term}. {r.mapped ? 'Mapped per cell.' : 'One value for the whole area.'}</>
                        : <>{r.text}{r.reason && <>: {r.reason}</>}.</>}
                      {r.verdict && <> Independent flood test: {VERDICT[r.verdict] ?? r.verdict}.</>}
                      {r.limitations.slice(0, 2).map((x) => <span key={x} className="kv-src">{x}</span>)}
                      {r.sources.map((x) => <span key={x} className="kv-src">{x}</span>)}
                    </dd>
                  </div>
                ))}
              </dl>
            </Disclosure>
          </Reveal>
        )}
      </section>

      {outputs.susceptibility && job.result && (
        <section>
          <h3 className="section-title">Ward ranking{shown ? `, ${shown.name.toLowerCase()}` : ''}</h3>
          <WardRanking wards={wards} layerKey={layerKey} row={shown} loading={wards?.loading} failed={wards?.failed} />
        </section>
      )}
    </>
  )
}
