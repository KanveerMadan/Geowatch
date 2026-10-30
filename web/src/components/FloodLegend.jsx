import { color } from '../design/tokens.js'
import { TIERS, TIER_TEXT } from '../lib/flood.js'
import TrustBadge from './TrustBadge.jsx'

/** The Flood layer's legend: which flood type is drawn, the five tiers, the
 *  not-measured hatch as its own state, and the shown type's badge. */
export default function FloodLegend({ rows, layerKey, onLayer }) {
  const mapped = rows.filter((r) => r.mapped)
  const shown = rows.find((r) => r.key === layerKey)
  if (!mapped.length) return null
  return (
    <div className="legend" aria-label="Map legend">
      <div className="seg seg-wrap" role="radiogroup" aria-label="Flood type shown on the map">
        {mapped.map((r) => (
          <button key={r.key} type="button" role="radio" aria-checked={r.key === layerKey}
            className={r.key === layerKey ? 'on' : ''} onClick={() => onLayer(r.key)}>{r.name}</button>
        ))}
      </div>
      <ol className="tier-key" aria-label="Susceptibility tiers">
        {TIERS.map((t) => (
          <li key={t}><i style={{ background: color.flood[t] }} aria-hidden="true" />{TIER_TEXT[t]}</li>
        ))}
      </ol>
      <div className="legend-foot">
        <span><i className="swatch swatch-hatch" aria-hidden="true" /> Not measured</span>
        {shown && <TrustBadge of={{ validation_status: shown.trust.key, validation_scope: shown.trust.scope }} compact />}
      </div>
      {shown?.trust.key === 'failed'
        ? <p className="caption caption-failed">This type failed validation. The map is shown for transparency, not for decisions.</p>
        : <p className="caption">Mean score in each 100 m cell. Not a flood forecast.</p>}
    </div>
  )
}
