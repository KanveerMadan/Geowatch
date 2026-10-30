import { useState } from 'react'
import { motion as m, useReducedMotion } from 'motion/react'
import { CaretDown, Check, CircleNotch, Warning } from '@phosphor-icons/react'
import { motion } from '../design/tokens.js'
import { stageRows } from '../lib/stages.js'

/** A section arriving: a short rise and fade, or a fade under reduced motion. */
export function Reveal({ children, k }) {
  const reduce = useReducedMotion()
  return (
    <m.div key={k} initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      transition={reduce ? { duration: motion.reduced.duration } : { duration: motion.duration.slow, ease: motion.ease }}>
      {children}
    </m.div>
  )
}

/** Figures and reasons, one click deeper (DESIGN.md rule 4). */
export function Disclosure({ label, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="disclosure">
      <button type="button" className="disclosure-btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <CaretDown size={12} className={open ? 'rot' : ''} aria-hidden="true" /> {label}
      </button>
      {open && <div className="disclosure-body">{children}</div>}
    </div>
  )
}

export function StageList({ job }) {
  const rows = stageRows(job)
  const icon = {
    done: <Check size={13} weight="bold" />,
    running: <CircleNotch size={13} className="spin-slow" />,
    failed: <Warning size={13} weight="bold" />,
    timeout: <Warning size={13} weight="bold" />,
    waiting: <span className="dot-wait" />,
  }
  const word = { failed: 'failed', timeout: 'timed out' }
  return (
    <ol className="stages" aria-label="Analysis steps">
      {rows.map((r) => (
        <li key={r.key} className={`stage stage-${r.state}`}>
          <span className="stage-icon" aria-hidden="true">{icon[r.state]}</span>
          <span>{r.text}</span>
          {word[r.state] && <span className="stage-word">{word[r.state]}</span>}
          <span className="sr-only">{r.state}</span>
        </li>
      ))}
    </ol>
  )
}
