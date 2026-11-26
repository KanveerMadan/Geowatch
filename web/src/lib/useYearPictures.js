import { useEffect, useRef, useState } from 'react'
import { ApiError, getImageryYear, getImageryYears } from './api.js'

export function useYearPictures(resultId, active) {
  const [imagery, setImagery] = useState(null)
  const [pair, setPair] = useState(null)
  const [imgs, setImgs] = useState({})
  const resources = useRef(null)

  useEffect(() => {
    const r = { controller: new AbortController(), years: new Set(), urls: [] }
    resources.current = r
    setImagery(null); setPair(null); setImgs({})
    return () => {
      r.controller.abort()
      r.urls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [resultId])

  useEffect(() => {
    if (!active || !resultId || imagery) return
    const ctl = new AbortController()
    getImageryYears(resultId, ctl.signal).then(({ years, compared }) => {
      if (ctl.signal.aborted) return
      setImagery({ resultId, years, compared })
      if (years?.length >= 2) {
        setPair(compared?.length === 2 && compared.every((y) => years.includes(y)) && compared[0] < compared[1]
          ? compared : [years[0], years.at(-1)])
      }
    }).catch(() => { if (!ctl.signal.aborted) setImagery({ resultId, years: [], failed: true }) })
    return () => ctl.abort()
  }, [active, resultId, imagery])

  useEffect(() => {
    const r = resources.current
    if (!active || !resultId || !r || !pair || imagery?.resultId !== resultId) return
    for (const y of pair) {
      if (r.years.has(y)) continue
      r.years.add(y)
      setImgs((s) => ({ ...s, [y]: { state: 'loading' } }))
      getImageryYear(resultId, y, r.controller.signal).then((url) => {
        if (r.controller.signal.aborted) { URL.revokeObjectURL(url); return }
        r.urls.push(url)
        setImgs((s) => ({ ...s, [y]: { state: 'ready', url } }))
      }).catch((e) => {
        if (!r.controller.signal.aborted) setImgs((s) => ({ ...s, [y]: {
          state: e instanceof ApiError && e.status === 404 ? 'missing' : 'error',
        } }))
      })
    }
  }, [active, resultId, pair, imagery])
  return imagery?.resultId === resultId ? { imagery, pair, setPair, imgs } : { imagery: null, pair: null, setPair, imgs: {} }
}
