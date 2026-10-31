import { useId, useState } from 'react'
import { AnimatePresence, motion as m, useReducedMotion } from 'motion/react'
import { motion } from '../design/tokens.js'
import { trustOf } from '../lib/contract.js'

/** The one trust badge. Hover, focus or tap opens a plain sentence; a
 *  validated output adds its scope note. */
export default function TrustBadge({ of, compact = false }) {
  const t = trustOf(of)
  const [open, setOpen] = useState(false)
  const id = useId()
  const reduce = useReducedMotion()
  return (
    <span className="trust-wrap" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        className={`trust trust-${t.key}${compact ? ' trust-compact' : ''}`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
      >
        <span className="trust-mark" aria-hidden="true" />
        {t.label}
      </button>
      <AnimatePresence>
        {open && (
          <m.span
            id={id}
            role="tooltip"
            className="trust-tip"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={reduce ? { duration: motion.reduced.duration } : motion.spring}
          >
            <strong className={`trust-tip-title trust-text-${t.key}`}>{t.label}</strong>
            {t.explain}
            {t.scope && <span className="trust-scope">{t.scope}</span>}
          </m.span>
        )}
      </AnimatePresence>
    </span>
  )
}
