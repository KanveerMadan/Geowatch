import { AnimatePresence, motion as m, useReducedMotion } from 'motion/react'
import { color, motion } from '../design/tokens.js'
import { fmtPct0, humanize, stackSegments } from '../lib/contract.js'
import { TIER_TEXT, tierOf } from '../lib/flood.js'
import { cellChange, unjudgedText } from '../lib/change.js'

const BAR_W = 168

/** A small stacked bar of the hovered cell's fractions. It follows the
 *  pointer (motion values, no re-render) and its segments morph from cell
 *  to cell, so neighbouring cells read as a change, not a new chart. */
const score = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const CHANGE_WORD = { increase: 'Up', decrease: 'Down', none: 'No detectable change' }

/** Flood: the hovered cell's tier and score for the shown type. */
function FloodRows({ cell, flood }) {
  const v = cell[`flood_${flood.key}`]
  const tier = tierOf(v)
  return (
    <>
      <p className="hc-title">{flood.name}</p>
      <dl className="hc-rows">
        <div>
          <dt>{tier && <i style={{ background: color.flood[tier] }} />}{tier ? TIER_TEXT[tier] : 'Not measured'}</dt>
          <dd className="num">{tier ? score.format(v) : ''}</dd>
        </div>
      </dl>
    </>
  )
}

/** Change: the hovered cell's verdict per fraction, the shown one first. */
function ChangeRows({ change }) {
  const keys = change.rows.filter((r) => r.measured).map((r) => r.key)
    .sort((a, b) => (a === change.fraction ? -1 : b === change.fraction ? 1 : 0))
  return (
    <dl className="hc-rows">
      {keys.map((k) => {
        const c = cellChange(change.props, k)
        return (
          <div key={k}>
            <dt><i style={{ background: color.data[k] ?? color.select }} />{humanize(k)}</dt>
            <dd>{c === 'unjudged' ? unjudgedText(change.props[k]) : CHANGE_WORD[c]}</dd>
          </div>
        )
      })}
    </dl>
  )
}

export default function HoverCard({ cell, keys, x, y, flood, change }) {
  const reduce = useReducedMotion()
  const t = reduce ? { duration: 0 } : motion.springSoft
  const st = cell && !flood ? stackSegments(cell, keys) : null
  if (change || (cell && flood)) {
    return (
      <m.div className="hover-card" style={{ x, y }} aria-hidden="true">
        {change ? <ChangeRows change={change} /> : <FloodRows cell={cell} flood={flood} />}
      </m.div>
    )
  }
  return (
    <AnimatePresence>
      {cell && (
        <m.div
          className="hover-card"
          style={{ x, y }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: motion.duration.fast }}
          aria-hidden="true"
        >
          <div className="hc-bar" style={{ width: BAR_W }}>
            {keys.map((k) => {
              const s = st.segments.find((g) => g.key === k)
              return (
                <m.span
                  key={k}
                  className="hc-seg"
                  style={{ background: color.data[k] ?? color.select, width: BAR_W, originX: 0 }}
                  initial={false}
                  animate={{ x: (s?.start ?? 0) * BAR_W, scaleX: s?.width ?? 0 }}
                  transition={t}
                />
              )
            })}
          </div>
          <dl className="hc-rows">
            {keys.map((k) => (
              <div key={k}>
                <dt><i style={{ background: color.data[k] ?? color.select }} />{humanize(k)}</dt>
                <dd className="num">{typeof cell[k] === 'number' ? fmtPct0(cell[k]) : 'Not measured'}</dd>
              </div>
            ))}
          </dl>
          {st.overlap && <p className="hc-note">Sources overlap here; the bar is scaled to fit.</p>}
        </m.div>
      )}
    </AnimatePresence>
  )
}
