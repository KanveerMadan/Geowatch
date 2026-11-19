import { PAGES } from '../lib/route.js'
import SiteChrome from './SiteChrome.jsx'

export default function NotFound() {
  return (
    <SiteChrome page="notfound" title="Not found, GeoWatch">
      <section className="page-head">
        <h1 className="page-title">This page does not exist</h1>
        <p className="page-lead">
          Try the <a href={PAGES.landing.path}>home page</a>, the <a href={PAGES.explore.path}>explorer</a> or
          the <a href={PAGES.gallery.path}>city gallery</a>.
        </p>
      </section>
    </SiteChrome>
  )
}
