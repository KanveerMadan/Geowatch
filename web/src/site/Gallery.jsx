import gallery from '../generated/gallery.json'
import { cardModel } from '../lib/gallery.js'
import { PAGES } from '../lib/route.js'
import TrustBadge from '../components/TrustBadge.jsx'
import SiteChrome from './SiteChrome.jsx'
import TileThumb from './TileThumb.jsx'

const when = new Intl.DateTimeFormat('en-GB', { dateStyle: 'long' })

function Row({ r }) {
  return (
    <div className="g-row">
      <dt>{r.name}</dt>
      <dd>
        <span className={r.measured ? 'num' : 'g-absent'}>{r.display}</span>
        <TrustBadge of={r.label} compact />
      </dd>
    </div>
  )
}

function Card({ c }) {
  const m = cardModel(c)
  return (
    <article className="g-card" aria-labelledby={`g-${m.key}`}>
      <TileThumb bbox={m.bbox} />
      <div className="g-body">
        <header>
          <h2 id={`g-${m.key}`} className="g-name">{m.name}</h2>
          <p className="caption">{m.region}</p>
        </header>
        <p className="g-observed">
          <span className="num">{m.observed}</span> of the area seen in clear imagery,
          {' '}{when.format(new Date(`${m.window[0]}T00:00:00`))} to {when.format(new Date(`${m.window[1]}T00:00:00`))}.
        </p>
        <section aria-label={`Ground cover, ${m.name}`}>
          <h3 className="g-h3">Ground cover, share of area</h3>
          <dl className="g-list">{m.ground.map((r) => <Row key={r.key} r={r} />)}</dl>
        </section>
        <section aria-label={`Flood susceptibility, ${m.name}`}>
          <h3 className="g-h3">Flood susceptibility, area tier</h3>
          <dl className="g-list">{m.floods.map((r) => <Row key={r.key} r={r} />)}</dl>
        </section>
        <footer className="g-foot">
          <p className="caption">
            Stored {when.format(new Date(m.run_utc))}, result <span className="num" translate="no">{m.result_id}</span>,
            version <span className="num" translate="no">{m.version_id}</span>. Labels are as stored with the result.
          </p>
          <div className="g-actions">
            <a className="sbtn sbtn-primary" href={m.reportHref}>Open the report</a>
            <a className="sbtn" href={m.exploreHref}>Explore this area</a>
          </div>
        </footer>
      </div>
    </article>
  )
}

export default function Gallery() {
  return (
    <SiteChrome page="gallery">
      <section className="page-head">
        <h1 className="page-title">City gallery</h1>
        <p className="page-lead">
          Stored analyses of {gallery.cities.length} areas. Each figure shows the trust label stored with it.
          A stored result never changes, so these labels are as they were on the day of the run; the
          current labels for each method are on the <a href={PAGES.honesty.path}>validation and limits page</a>.
        </p>
      </section>
      <div className="g-grid">
        {gallery.cities.map((c) => <Card key={c.key} c={c} />)}
      </div>
      <p className="caption g-credit">Imagery: Esri World Imagery (Esri, Vantor, Earthstar Geographics, and the GIS User Community).</p>
    </SiteChrome>
  )
}
