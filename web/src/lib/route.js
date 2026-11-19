/*
 * Which page a URL is. Path routes for the public site; the explorer keeps
 * its old permanent links: ?report=<id> anywhere is the area report, and a
 * bare `/?bbox=` or `/?job=` link still opens the explorer, never the
 * landing page.
 */
import { parseReport } from './link.js'

export const PAGES = {
  landing: { path: '/', title: 'GeoWatch' },
  explore: { path: '/explore', title: 'Explorer, GeoWatch' },
  gallery: { path: '/gallery', title: 'City gallery, GeoWatch' },
  honesty: { path: '/honesty', title: 'What we can and cannot tell you, GeoWatch' },
}

/** {page, report} for a pathname and search string. */
export function routeOf(pathname, search) {
  const report = parseReport(search)
  if (report) return { page: 'report', report }
  const p = (pathname || '/').replace(/\/index\.html$/, '/').replace(/\/+$/, '') || '/'
  if (p === '/') {
    const q = new URLSearchParams(search)
    return { page: q.has('bbox') || q.has('job') ? 'explore' : 'landing', report: null }
  }
  const hit = Object.entries(PAGES).find(([, v]) => v.path === p)
  return { page: hit ? hit[0] : 'notfound', report: null }
}

/** The explorer opened on a box. */
export const exploreHref = (bbox) => `${PAGES.explore.path}?bbox=${bbox.map((v) => (+v).toFixed(5)).join(',')}`
