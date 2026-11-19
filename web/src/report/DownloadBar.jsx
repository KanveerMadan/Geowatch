import { useState } from 'react'
import { DownloadSimple } from '@phosphor-icons/react'
import { getWardPage } from '../lib/api.js'
import { PAGE_LIMIT, PUBLIC_UNIT_TYPES, downloadName, toCSV, toGeoJSON } from '../lib/download.js'

const unitLabel = (t) => (t === 'grid' ? '100 m grid' : `Wards (${t.slice(5).replace(/_/g, ' ')})`)

async function allUnits(resultId, unitType) {
  const units = []
  for (let offset = 0; ; offset += PAGE_LIMIT) {
    const page = await getWardPage(resultId, unitType, offset, PAGE_LIMIT)
    units.push(...page.units)
    if (units.length >= page.n_units || page.units.length === 0) return units
  }
}

function save(text, name, type) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** GeoJSON and CSV of a result's public units (wards, 100 m grid), with
 *  provenance. Footprint and path units are never offered. */
export default function DownloadBar({ result, resultId }) {
  const types = PUBLIC_UNIT_TYPES(Object.keys(result.wards ?? {})
    .filter((t) => result.wards[t]?.status === 'available'))
  const [type, setType] = useState(types.find((t) => t.startsWith('ward:')) ?? types[0])
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  if (!types.length) return null

  async function run(kind) {
    setBusy(kind); setError(null)
    try {
      const units = await allUnits(resultId, type)
      const r = { ...result, result_id: resultId }
      if (kind === 'geojson') save(JSON.stringify(toGeoJSON(r, units)), downloadName(r, type, 'geojson'), 'application/geo+json')
      else save(toCSV(r, units), downloadName(r, type, 'csv'), 'text/csv')
    } catch {
      setError('The download could not be prepared. Try again.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="rdl" role="group" aria-label="Download data">
      <label className="rdl-pick">
        <span className="sr-only">Units to download</span>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          {types.map((t) => <option key={t} value={t}>{unitLabel(t)}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => run('geojson')} disabled={!!busy}>
        <DownloadSimple size={15} aria-hidden="true" /> {busy === 'geojson' ? 'Preparing…' : 'GeoJSON'}
      </button>
      <button type="button" onClick={() => run('csv')} disabled={!!busy}>
        <DownloadSimple size={15} aria-hidden="true" /> {busy === 'csv' ? 'Preparing…' : 'CSV'}
      </button>
      {error && <p role="alert" className="rdl-err">{error}</p>}
    </div>
  )
}
