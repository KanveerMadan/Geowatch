import { useEffect } from 'react'
import { PAGES } from '../lib/route.js'
import '../styles/site.css'

const NAV = [
  ['explore', 'Explorer'],
  ['gallery', 'Gallery'],
  ['honesty', 'What we can’t tell you'],
]

export function Wordmark() {
  return (
    <a className="site-mark" href={PAGES.landing.path} aria-label="GeoWatch home">
      <svg width="20" height="20" viewBox="0 0 16 16" aria-hidden="true">
        <rect width="16" height="16" rx="4" fill="currentColor" opacity="0.08" />
        <rect x="4" y="4" width="8" height="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <span>GeoWatch</span>
    </a>
  )
}

/** Header, skip link, main landmark and footer for the public pages. */
export default function SiteChrome({ page, title, children }) {
  useEffect(() => { document.title = title ?? PAGES[page]?.title ?? 'GeoWatch' }, [page, title])
  return (
    <div className="site">
      <a className="site-skip" href="#main">Skip to content</a>
      <header className="site-head">
        <Wordmark />
        <nav aria-label="Site">
          <ul className="site-nav">
            {NAV.map(([k, label]) => (
              <li key={k}>
                <a href={PAGES[k].path} aria-current={k === page ? 'page' : undefined}
                  className={k === 'explore' ? 'site-nav-cta' : undefined}>{label}</a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" className="site-main" tabIndex={-1}>{children}</main>
      <footer className="site-foot">
        <p>
          GeoWatch is open analysis of public data: Sentinel-2, Open Buildings, OpenStreetMap,
          MERIT Hydro, FABDEM, Copernicus DEM and CHIRPS. Each number names its sources.
        </p>
        <p>
          Public results stop at wards and 100 m cells. Building-level detail is shared only with
          named partners, because finer maps of where people live can be used against them.
        </p>
        <ul className="site-foot-links">
          <li><a href={PAGES.explore.path}>Explorer</a></li>
          <li><a href={PAGES.gallery.path}>Gallery</a></li>
          <li><a href={PAGES.honesty.path}>Validation and limits</a></li>
        </ul>
      </footer>
    </div>
  )
}
