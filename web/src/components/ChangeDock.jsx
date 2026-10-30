import { useRef } from 'react'
import { color } from '../design/tokens.js'
import { humanize } from '../lib/contract.js'
import { orderPair } from '../lib/change.js'

/** Two thumbs on a row of years: the before and after pictures. The years
 *  the change test compared are marked, so a scrub away from them is never
 *  mistaken for the analysis. */
function TimeScrubber({ years, pair, compared, status, onPair }) {
  const track = useRef(null)
  const dragging = useRef(null)
  const at = (y) => (years.length > 1 ? (years.indexOf(y) / (years.length - 1)) * 100 : 50)
  const yearFromX = (clientX) => {
    const r = track.current.getBoundingClientRect()
    const i = Math.round(((clientX - r.left) / r.width) * (years.length - 1))
    return years[Math.min(years.length - 1, Math.max(0, i))]
  }
  const set = (which, y) => onPair(orderPair(pair, which, y, years))
  const down = (which) => (ev) => { dragging.current = which; ev.currentTarget.setPointerCapture(ev.pointerId) }
  const move = (ev) => { if (dragging.current) set(dragging.current, yearFromX(ev.clientX)) }
  const up = () => { dragging.current = null }
  const key = (which) => (ev) => {
    const i = years.indexOf(pair[which === 'before' ? 0 : 1])
    const d = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[ev.key]
    if (d) { ev.preventDefault(); set(which, years[Math.min(years.length - 1, Math.max(0, i + d))]) }
    if (ev.key === 'Home') { ev.preventDefault(); set(which, years[0]) }
    if (ev.key === 'End') { ev.preventDefault(); set(which, years.at(-1)) }
  }
  // A click on a year moves the nearer thumb there.
  const pick = (y) => set(Math.abs(y - pair[0]) <= Math.abs(y - pair[1]) ? 'before' : 'after', y)

  return (
    <div className="scrub">
      <div className="scrub-track" ref={track}>
        <span className="scrub-range" style={{ left: `${at(pair[0])}%`, width: `${at(pair[1]) - at(pair[0])}%` }} aria-hidden="true" />
        {years.map((y) => (
          <button key={y} type="button" tabIndex={-1} className={`scrub-tick scrub-${status[y] ?? 'idle'}${compared?.includes(y) ? ' scrub-compared' : ''}`}
            style={{ left: `${at(y)}%` }} onClick={() => pick(y)} aria-label={`Show ${y}`}>
            <span className="scrub-year num">{String(y).slice(2)}</span>
          </button>
        ))}
        {['before', 'after'].map((which, i) => (
          <button key={which} type="button" role="slider" className={`scrub-thumb scrub-thumb-${which}`}
            style={{ left: `${at(pair[i])}%` }}
            aria-label={which === 'before' ? 'Before year' : 'After year'}
            aria-valuemin={years[0]} aria-valuemax={years.at(-1)} aria-valuenow={pair[i]}
            onPointerDown={down(which)} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onKeyDown={key(which)}>
            <span className="num">{pair[i]}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/** The Change tab's dock: which fraction's changes are drawn, what the marks
 *  mean, and the years of the two pictures. */
export default function ChangeDock({ choices, fraction, onFraction, years, pair, compared, status, onPair, analysedPair }) {
  const hue = color.data[fraction] ?? color.select
  const same = analysedPair && pair[0] === analysedPair[0] && pair[1] === analysedPair[1]
  const missing = pair.filter((y) => status[y] === 'missing')
  return (
    <div className="legend change-dock" aria-label="Change legend and years">
      {choices.length > 0 && (
        <div className="seg" role="radiogroup" aria-label="Fraction whose change is drawn">
          {choices.map((k) => (
            <button key={k} type="button" role="radio" aria-checked={k === fraction}
              className={k === fraction ? 'on' : ''} onClick={() => onFraction(k)}>
              <i className="swatch" style={{ background: color.data[k] ?? color.select }} aria-hidden="true" />{humanize(k)}
            </button>
          ))}
        </div>
      )}
      <div className="legend-foot chg-key">
        <span><i className="swatch" style={{ background: hue }} aria-hidden="true" /> Up</span>
        <span><i className="swatch swatch-stripe" style={{ '--hue': hue }} aria-hidden="true" /> Down</span>
        <span><i className="swatch swatch-hatch" aria-hidden="true" /> Not judged</span>
      </div>
      {years?.length > 1 && (
        <>
          <TimeScrubber years={years} pair={pair} compared={compared} status={status} onPair={onPair} />
          <p className="caption">
            {same
              ? <>Pictures and marked cells both compare {pair[0]} and {pair[1]}, the analysed years.</>
              : <>Pictures show {pair[0]} and {pair[1]}. Marked cells compare {analysedPair?.[0]} and {analysedPair?.[1]}, the analysed years.</>}
            {missing.length > 0 && <> No clear imagery in {missing.join(' or ')}.</>}
          </p>
          <p className="caption">Pictures: contains modified Copernicus Sentinel-2 data {pair[0]}, {pair[1]}.</p>
        </>
      )}
    </div>
  )
}
