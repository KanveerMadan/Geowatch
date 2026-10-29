import { useEffect, useRef } from 'react'
import { animate, useReducedMotion } from 'motion/react'
import { motion } from '../design/tokens.js'

/** A number that counts up from 0 when it arrives. Writes the DOM directly,
 *  so React does not re-render every frame. */
export function CountUp({ value, format }) {
  const ref = useRef(null)
  const reduce = useReducedMotion()
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (reduce) { el.textContent = format(value); return }
    const c = animate(0, value, {
      duration: motion.countUpMs / 1000,
      ease: motion.ease,
      onUpdate: (v) => { el.textContent = format(v) },
    })
    return () => c.stop()
  }, [value, format, reduce])
  return <span ref={ref} className="num">{format(reduce ? value : 0)}</span>
}

/** A placeholder with the final content's height, so nothing shifts. */
export function Skeleton({ h = 16, w = '100%', r }) {
  return <span className="skeleton" style={{ height: h, width: w, borderRadius: r }} aria-hidden="true" />
}

export function Kbd({ children }) {
  return <kbd className="kbd">{children}</kbd>
}
