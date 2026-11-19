import { useId, useState } from 'react'
import { MagnifyingGlass } from '@phosphor-icons/react'
import { searchPlaces } from '../lib/geocode.js'
import { DEFAULT_BOX_KM, boxAround, parseCoordinates } from '../lib/geo.js'
import { PAGES, exploreHref } from '../lib/route.js'

/** The landing page's way into the explorer: search a place (on submit
 *  only, Nominatim's policy), pick a result, land in the explorer on it. */
export default function TrySearch() {
  const [text, setText] = useState('')
  const [state, setState] = useState({ rows: null, busy: false, error: null })
  const id = useId()

  async function submit(e) {
    e.preventDefault()
    const q = text.trim()
    if (!q) return
    const c = parseCoordinates(q)
    if (c) { window.location.assign(exploreHref(boxAround(c.lat, c.lon))); return }
    setState({ rows: null, busy: true, error: null })
    try {
      const rows = await searchPlaces(q)
      setState({ rows, busy: false, error: null })
    } catch {
      setState({ rows: null, busy: false, error: 'The place search is not answering. Try coordinates, or open the explorer.' })
    }
  }

  return (
    <div className="try">
      <form className="try-form" role="search" onSubmit={submit}>
        <label htmlFor={id} className="sr-only">Search a place or coordinates</label>
        <MagnifyingGlass size={18} aria-hidden="true" className="try-icon" />
        <input id={id} type="search" value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Search a place, or type coordinates" autoComplete="off" enterKeyHint="search" />
        <button type="submit" className="sbtn sbtn-primary" disabled={state.busy}>
          {state.busy ? 'Searching…' : 'Find'}
        </button>
      </form>
      <div aria-live="polite" className="try-results">
        {state.error && <p className="caption">{state.error}</p>}
        {state.rows && state.rows.length === 0 && <p className="caption">No place found. Try a city or district name.</p>}
        {state.rows && state.rows.length > 0 && (
          <>
            <ul>
              {state.rows.map((p) => (
                <li key={p.id}>
                  <a href={exploreHref(boxAround(p.lat, p.lon))}>
                    <span>{p.name}</span>
                    <span className="caption">{p.region}</span>
                  </a>
                </li>
              ))}
            </ul>
            <p className="caption">Search by OpenStreetMap Nominatim. Opens a {DEFAULT_BOX_KM} km box around the place; you can redraw it.</p>
          </>
        )}
        {!state.rows && !state.error && (
          <p className="caption">Or <a href={PAGES.explore.path}>open the explorer</a> and draw any area on the globe.</p>
        )}
      </div>
    </div>
  )
}
