import { ArrowRight } from '@phosphor-icons/react'
import honesty from '../generated/honesty.json'
import gallery from '../generated/gallery.json'
import { TRUST, TRUST_ORDER } from '../lib/contract.js'
import { floodCounts, numWord } from '../lib/honesty.js'
import { PAGES } from '../lib/route.js'
import TrustBadge from '../components/TrustBadge.jsx'
import SiteChrome from './SiteChrome.jsx'
import TrySearch from './TrySearch.jsx'
import BoxDiagram from './BoxDiagram.jsx'

/** "one validated within a stated scope, four failed ..." from the counts. */
function builtParts(fc) {
  const parts = [
    [fc.validated, 'validated within a stated scope'],
    [fc.experimental, 'experimental, not yet tested'],
    [fc.failed, 'failed their test and are shown only for transparency'],
  ].filter(([n]) => n > 0).map(([n, t]) => `${numWord(n)} ${t}`)
  return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}` : parts[0] ?? 'none tested yet'
}
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)
// The labels a pipeline output can carry, best first (retired belongs to the
// old pipeline and is not shown here).
const LABELS = [...TRUST_ORDER].reverse().filter((k) => k !== 'retired')

export default function Landing() {
  const fc = floodCounts(honesty)
  const notMeasured = honesty.ground.filter((g) => !g.measured).length
  return (
    <SiteChrome page="landing">
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-text">
          <h1 id="hero-title" className="hero-title">
            Pick an area. See what is there, how it is changing, and where it floods.
          </h1>
          <p className="hero-lead">
            GeoWatch reads satellite imagery, open building and street maps and terrain for any box
            you draw, and puts a trust label on every number it returns. Where it cannot measure
            something, it says so, and never shows a zero.
          </p>
          <TrySearch />
        </div>
        <BoxDiagram />
      </section>

      <section className="band" aria-labelledby="what-title">
        <h2 id="what-title" className="band-title">What it does</h2>
        <ol className="three">
          <li>
            <h3>What is there</h3>
            <p>Built, vegetation and water shares for the area and for each 100 m cell, from building footprints and Sentinel-2.</p>
            <p className="caption">{cap(numWord(notMeasured))} more ground covers (impervious, paved, bare) are listed as not yet measured until their method exists.</p>
          </li>
          <li>
            <h3>How it is changing</h3>
            <p>Two pictures of the same season in different years, and the cells where a cover rose or fell by more than the measured noise.</p>
            <p className="caption">Cells that cannot be judged, for cloud or missing imagery, are drawn as unjudged, not as unchanged.</p>
          </li>
          <li>
            <h3>Where it floods</h3>
            <p>Susceptibility per 100 m cell for each flood type the method covers, and wards ranked by it.</p>
            <p className="caption">
              Of {numWord(fc.total)} flood types, {numWord(fc.built)} are built: {builtParts(fc)}.{' '}
              <a href={PAGES.honesty.path}>See which.</a>
            </p>
          </li>
        </ol>
      </section>

      <section className="band" aria-labelledby="who-title">
        <h2 id="who-title" className="band-title">Who it is for</h2>
        <ul className="who">
          <li><strong>Humanitarian and NGO teams</strong> comparing where flood exposure and dense building coincide, before fieldwork.</li>
          <li><strong>Municipal planners</strong> who need ward-level readings with their sources, not a single score.</li>
          <li><strong>Development funders</strong> checking an area’s conditions with numbers that say how far they can be trusted.</li>
          <li><strong>Researchers</strong> who want the method, the version and the validation record behind each figure.</li>
        </ul>
        <p className="caption who-note">
          Insurers: area-level readings only. Public detail stops at wards and 100 m cells; building-level
          detail is for named partners, because it can be used to target evictions. Dense areas are
          described as high-density built-up areas, never by the kind of settlement.
        </p>
      </section>

      <section className="band" aria-labelledby="trust-title">
        <h2 id="trust-title" className="band-title">How the trust labels work</h2>
        <p className="band-lead">Every number carries one label. An output takes the worst label that applies to any part of it.</p>
        <dl className="labels">
          {LABELS.map((k) => (
            <div key={k} className="label-row">
              <dt><TrustBadge of={k === 'validated' ? { validation_status: k, validated_scope: 'Holds only in the places and events named with it.' } : k} /></dt>
              <dd>{TRUST[k].explain}</dd>
            </div>
          ))}
          <div className="label-row">
            <dt><span className="nm-chip"><i aria-hidden="true" />Not measured</span></dt>
            <dd>No value, with the reason one click deeper. On the map it is a grey hatch, listed separately in the legend. It is never drawn or counted as zero.</dd>
          </div>
        </dl>
      </section>

      <section className="band band-split" aria-labelledby="go-title">
        <div>
          <h2 id="go-title" className="band-title">Look before you trust it</h2>
          <p className="band-lead">
            Stored results for {gallery.cities.map((c) => c.name).join(', ').replace(/, ([^,]*)$/, ' and $1')}, each with its labels as stored, and the
            full record of what has been validated, what failed and what is not built.
          </p>
        </div>
        <div className="go-links">
          <a className="go" href={PAGES.gallery.path}><span>City gallery</span><ArrowRight size={18} aria-hidden="true" /></a>
          <a className="go" href={PAGES.honesty.path}><span>What we can and cannot tell you</span><ArrowRight size={18} aria-hidden="true" /></a>
          <a className="go" href={PAGES.explore.path}><span>Open the explorer</span><ArrowRight size={18} aria-hidden="true" /></a>
        </div>
      </section>
    </SiteChrome>
  )
}
