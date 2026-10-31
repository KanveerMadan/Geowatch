import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion as m, useReducedMotion } from 'motion/react'
import { MagnifyingGlass } from '@phosphor-icons/react'
import { motion } from '../design/tokens.js'
import { Kbd } from './bits.jsx'

/** Cmd/Ctrl+K: every action in one list. Typing filters; when the text is
 *  not an action, the first row searches places for it. */
export default function CommandPalette({ open, onClose, actions, onSearch }) {
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const input = useRef(null)
  const reduce = useReducedMotion()

  useEffect(() => { if (open) { setQ(''); setActive(0); setTimeout(() => input.current?.focus(), 0) } }, [open])

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase()
    const hits = actions.filter((a) => !a.disabled && (!s || a.label.toLowerCase().includes(s)))
    return s ? [{ id: 'search', label: `Search places for "${q.trim()}"`, run: () => onSearch(q.trim()) }, ...hits] : hits
  }, [q, actions, onSearch])

  function key(e) {
    if (e.key === 'Escape') { e.preventDefault(); onClose() }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, rows.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    if (e.key === 'Enter' && rows[active]) { e.preventDefault(); rows[active].run(); onClose() }
  }

  return (
    <AnimatePresence>
      {open && (
        <m.div className="palette-scrim" onMouseDown={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: motion.duration.fast }}>
          <m.div
            className="palette"
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            onMouseDown={(e) => e.stopPropagation()}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4, scale: 0.99 }}
            transition={reduce ? { duration: motion.reduced.duration } : motion.spring}
          >
            <div className="palette-input">
              <MagnifyingGlass size={18} aria-hidden="true" />
              <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setActive(0) }} onKeyDown={key}
                placeholder="Type a command or a place…" aria-label="Command or place"
                role="combobox" aria-controls="palette-list" aria-expanded="true"
                aria-activedescendant={rows[active] ? `pa-${rows[active].id}` : undefined} />
              <Kbd>Esc</Kbd>
            </div>
            <ul id="palette-list" role="listbox" aria-label="Commands">
              {rows.map((a, i) => (
                <li key={a.id} id={`pa-${a.id}`} role="option" aria-selected={i === active} className={i === active ? 'active' : ''}
                  onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); a.run(); onClose() }}>
                  {a.icon && <a.icon size={16} aria-hidden="true" />}
                  <span>{a.label}</span>
                  {a.kbd && <Kbd>{a.kbd}</Kbd>}
                </li>
              ))}
              {!rows.length && <li className="palette-empty">No matching command.</li>}
            </ul>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
