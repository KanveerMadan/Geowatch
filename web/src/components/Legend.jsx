import { color } from '../design/tokens.js'
import { humanize } from '../lib/contract.js'
import TrustBadge from './TrustBadge.jsx'

/** The Ground layer's legend: the shown fraction's ramp, the no-data hatch
 *  as its own state, and the 3D footprint caveat when it is up. */
export default function Legend({ fraction, output, choices, onChoose, footprints }) {
  const hue = color.data[fraction] ?? color.select
  return (
    <div className="legend" aria-label="Map legend">
      <div className="seg" role="radiogroup" aria-label="Fraction shown on the map">
        {choices.map((k) => (
          <button key={k} type="button" role="radio" aria-checked={k === fraction}
            className={k === fraction ? 'on' : ''} onClick={() => onChoose(k)}>
            <i className="swatch" style={{ background: color.data[k] ?? color.select }} aria-hidden="true" />{humanize(k)}
          </button>
        ))}
      </div>
      <div className="ramp-row">
        <span className="ramp" style={{ background: `linear-gradient(90deg, ${hue}0d, ${hue})` }} aria-hidden="true" />
        <span className="ramp-ticks"><span>0%</span><span>share of each 100 m cell</span><span>100%</span></span>
      </div>
      <div className="legend-foot">
        <span><i className="swatch swatch-hatch" aria-hidden="true" /> Not measured</span>
        {output && <TrustBadge of={output} compact />}
      </div>
      {footprints === 'shown' && <p className="caption">Buildings raised to one height for depth: building height is not measured.</p>}
      {footprints === 'loading' && <p className="caption">Loading building outlines…</p>}
      {footprints === 'missing' && <p className="caption">Building outlines are not available for this area on this server.</p>}
    </div>
  )
}
