import { AnimatePresence, motion as m, useReducedMotion } from 'motion/react'
import { color, motion } from '../design/tokens.js'
import { fmtPct0, humanize, stackSegments } from '../lib/contract.js'

const BAR_W = 168

/** A small stacked bar of the hovered cell's fractions. It follows the
 *  pointer (motion values, no re-render) and its segments morph from cell
 *  to cell, so neighbouring cells read as a change, not a new chart. */
export default function HoverCard({ cell, keys, x, y }) {
  const reduce = useReducedMotion()
  const t = reduce ? { duration: 0 } : motion.springSoft
  const st = cell ? stackSegments(cell, keys) : null
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
