import { useEffect, useState } from 'react'
import { AnimatePresence, motion as m, useReducedMotion } from 'motion/react'
import { MagnifyingGlass, Square, Lasso, CircleNotch, MapPin, X } from '@phosphor-icons/react'
import { motion } from '../design/tokens.js'
import { parseCoordinates } from '../lib/geo.js'
import { searchPlaces } from '../lib/geocode.js'
import { Kbd } from './bits.jsx'

/** Search first: one field for any place, address or coordinates; drawing
 *  an area is the second option, beside it. Searches run on Enter. */
export default function SearchBar({ inputRef, onPick, drawMode, onDraw, command }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null) // null: closed
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [active, setActive] = useState(0)
  const reduce = useReducedMotion()

  // The command palette hands a query over: show it here and search it.
  useEffect(() => {
    if (!command) return
    setQ(command.q)
    run(null, command.q)
    inputRef.current?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command])

  async function run(e, text = q) {
    e?.preventDefault()
    setError(null)
    const c = parseCoordinates(text)
    if (c) {
      setResults([{ id: 'coords', name: `${c.lat.toFixed(5)}, ${c.lon.toFixed(5)}`, region: 'Coordinates', ...c, bbox: null }])
      setActive(0)
      return
    }
    if (!text.trim()) return
    setBusy(true)
    try {
      const r = await searchPlaces(text)
      setResults(r)
      setActive(0)
      if (!r.length) setError('No place found. Try a city, a street, or coordinates like 19.04, 72.85.')
    } catch {
      setResults([])
      setError('Search is not answering right now. Try again, or type coordinates.')
    } finally {
      setBusy(false)
    }
  }

  function pick(p) {
    setResults(null)
    setQ(p.name)
    onPick(p)
  }

  function onKey(e) {
    if (!results?.length) {
      if (e.key === 'Escape') { setResults(null); setError(null) }
      return
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => (a + 1) % results.length) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => (a - 1 + results.length) % results.length) }
    if (e.key === 'Escape') setResults(null)
  }

  const open = results !== null && (results.length > 0 || error)
  return (
    <div className="search">
      <form className="search-bar" role="search" onSubmit={(e) => {
        if (results?.length && results[active]) { e.preventDefault(); pick(results[active]) } else run(e)
      }}>
        <span className="search-icon" aria-hidden="true">
          {busy ? <CircleNotch className="spin-slow" size={18} /> : <MagnifyingGlass size={18} />}
        </span>
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => { setQ(e.target.value); setResults(null); setError(null) }}
          onKeyDown={onKey}
          placeholder="Search any place or coordinates…"
          aria-label="Search a place, address or coordinates"
          aria-controls="search-results"
          aria-expanded={!!open}
          aria-activedescendant={open && results?.length ? `sr-${active}` : undefined}
          role="combobox"
          aria-autocomplete="none"
          autoComplete="off"
          spellCheck={false}
        />
        {q ? (
          <button type="button" className="icon-btn" aria-label="Clear search" onClick={() => { setQ(''); setResults(null); setError(null) }}>
            <X size={14} />
          </button>
        ) : <Kbd>/</Kbd>}
      </form>
      <div className="draw-group" role="group" aria-label="Draw an area">
        <button type="button" className={`chip${drawMode === 'rect' ? ' chip-on' : ''}`} aria-pressed={drawMode === 'rect'}
          onClick={() => onDraw(drawMode === 'rect' ? null : 'rect')} title="Draw a rectangle">
          <Square size={15} /> <span>Draw an area</span>
        </button>
        <button type="button" className={`chip chip-icon${drawMode === 'lasso' ? ' chip-on' : ''}`} aria-pressed={drawMode === 'lasso'}
          onClick={() => onDraw(drawMode === 'lasso' ? null : 'lasso')} aria-label="Draw freehand (lasso)" title="Draw freehand">
          <Lasso size={15} />
        </button>
      </div>
      <AnimatePresence>
        {open && (
          <m.div
            className="search-results"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={reduce ? { duration: motion.reduced.duration } : motion.spring}
          >
            {error && <p className="search-msg">{error}</p>}
            {results?.length > 0 && (
              <ul id="search-results" role="listbox" aria-label="Places">
                {results.map((p, i) => (
                  <li key={p.id} id={`sr-${i}`} role="option" aria-selected={i === active}
                    className={i === active ? 'active' : ''} onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(p) }}>
                    <MapPin size={16} aria-hidden="true" />
                    <span className="sr-name">{p.name}</span>
                    {p.region && <span className="sr-region">{p.region}</span>}
                  </li>
                ))}
              </ul>
            )}
            {results?.length > 0 && results[0].id !== 'coords' && <p className="search-attr">Search by OpenStreetMap Nominatim</p>}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
