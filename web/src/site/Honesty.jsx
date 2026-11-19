import h from '../generated/honesty.json'
import { humanize } from '../lib/contract.js'
import { floodName } from '../lib/flood.js'
import { eventName, evidenceSentence, floodSections, fmtAuc } from '../lib/honesty.js'
import TrustBadge from '../components/TrustBadge.jsx'
import SiteChrome from './SiteChrome.jsx'

// No figure in this file: every number below is read from honesty.json,
// which python -m product.site_data generates from analysis/contract.py.
// tests/test_site_data.py fails when the two disagree.

// Display names only; which causes exist is read from honesty.json.
const CAUSE = { cloud_nodata: 'gaps from cloud and missing data', fully_shadowed: 'fully shadowed ground', transient_snow: 'passing snow' }
const causeName = (c) => CAUSE[c] ?? c.replace(/_/g, ' ')
const sentence = (t) => t.charAt(0).toUpperCase() + t.slice(1)
const list = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}` : xs[0] ?? '')

function EventList({ events }) {
  if (!events?.length) return null
  return (
    <ul className="h-events">
      {events.map((e) => (
        <li key={e.event}><span>{eventName(e.event)}</span><span className="num">{fmtAuc(e.auc)}</span></li>
      ))}
    </ul>
  )
}

function Validated({ r }) {
  const sc = r.scope
  return (
    <article className="h-card h-card-validated" aria-labelledby={`h-${r.module}`}>
      <header className="h-card-head">
        <h3 id={`h-${r.module}`}><span className="h-id num">{r.id}</span>{floodName(r.module)}</h3>
        <TrustBadge of={{ validation_status: 'validated', validated_scope: sc }} />
      </header>
      <p>{evidenceSentence(r, h.bar)}</p>
      <dl className="h-facts">
        <div><dt>Where it holds</dt><dd>{list(sc.regions)}</dd></div>
        <div><dt>Held-out test events</dt><dd><ul className="h-plain">{sc.events.map((e) => <li key={e}>{e}</li>)}</ul></dd></div>
        <div><dt>Tuned on (never tested on)</dt><dd><ul className="h-plain">{sc.tuning_events.map((e) => <li key={e}>{e}</li>)}</ul></dd></div>
        <div><dt>Inputs it was validated with</dt><dd className="num" translate="no">{Object.entries(sc.input_versions).map(([k, v]) => `${k} ${v}`).join(', ')}</dd></div>
      </dl>
      {sc.not_covered && (
        <div className="h-warn">
          <h4>Tested and not shown to hold</h4>
          <p>
            {list(sc.not_covered.regions)}: mean AUC {fmtAuc(sc.not_covered.round4_mean_auc)}, below the bar.
            The validation does not extend to these places.
          </p>
          <ul className="h-plain caption">{sc.not_covered.events.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
      <p className="caption">
        Outside exactly this configuration ({r.validated_method.replace(/_/g, ' ')}, the inputs above) the same module is labelled{' '}
        <TrustBadge of={r.outside_scope} compact />.
      </p>
      <p className="caption h-src" translate="no">Evidence: {r.evidence.file}</p>
    </article>
  )
}

function Failed({ r }) {
  return (
    <article className="h-card" aria-labelledby={`h-${r.module}`}>
      <header className="h-card-head">
        <h3 id={`h-${r.module}`}><span className="h-id num">{r.id}</span>{floodName(r.module)}</h3>
        <TrustBadge of="failed" />
      </header>
      <p>{evidenceSentence(r, h.bar)}</p>
      <EventList events={r.evidence?.events} />
      <p className="caption">{sentence(r.status_text)}. Shown on the map for transparency, never as a basis for decisions.</p>
      <p className="caption h-src" translate="no">Evidence: {r.evidence?.file}</p>
    </article>
  )
}

export default function Honesty() {
  const s = floodSections(h)
  const notMeasured = h.ground.filter((g) => !g.measured)
  return (
    <SiteChrome page="honesty">
      <section className="page-head">
        <h1 className="page-title">What we can and cannot tell you</h1>
        <p className="page-lead">
          This page is generated from the code that labels every result, so it cannot drift from what
          the explorer shows. A method is validated only when it passed a test fixed in advance, on
          events it was never tuned on, and only for the places those events cover.
        </p>
      </section>

      <section className="band" aria-labelledby="rule-title">
        <h2 id="rule-title" className="band-title">The test</h2>
        <p>
          For each event, flooded and dry {h.limits.find((l) => l.id === 'terrain').facts.evaluation_cell_m} m cells are
          compared with an independent flood map (Copernicus EMS, an official map, or Sentinel-1 radar). The score
          must separate them: ROC AUC, where 0.5 is chance. A method passes when its mean AUC is at least{' '}
          <strong className="num">{fmtAuc(h.bar.validated_if_auc_at_least)}</strong> over at
          least {h.bar.min_events} held-out events, each with at least {h.bar.min_flooded_cells} flooded and {h.bar.min_dry_cells} dry cells.
        </p>
        <p className="caption">
          Labels, worst first: {h.label_order.map((k) => humanize(k)).join(', ')}. An output takes the worst label that applies.
        </p>
      </section>

      <section className="band" aria-labelledby="val-title">
        <h2 id="val-title" className="band-title">Validated, and where</h2>
        {s.validated.length ? s.validated.map((r) => <Validated key={r.id} r={r} />)
          : <p>Nothing is validated yet.</p>}
      </section>

      <section className="band" aria-labelledby="exp-title">
        <h2 id="exp-title" className="band-title">Experimental</h2>
        <p className="band-lead">Real methods that have not passed an independent test. Use with care.</p>
        <ul className="h-rows">
          {s.experimental.map((r) => (
            <li key={r.id}><span>{floodName(r.module)} flood susceptibility</span><TrustBadge of="experimental" compact /></li>
          ))}
          {h.ground.filter((g) => g.label === 'experimental').map((g) => (
            <li key={g.key}><span>{humanize(g.key)} share of ground</span><TrustBadge of="experimental" compact /></li>
          ))}
          {h.observation.filter((o) => o.label === 'experimental').map((o) => (
            <li key={o.cause}><span>Observed share, {causeName(o.cause)}</span><TrustBadge of="experimental" compact /></li>
          ))}
          <li><span>Street and building metrics (road length, density, access, map coverage)</span><TrustBadge of={h.vector_default_label} compact /></li>
          {s.validated.map((r) => (
            <li key={r.id}><span>{floodName(r.module)}, outside its validated configuration</span><TrustBadge of={r.outside_scope} compact /></li>
          ))}
        </ul>
        <h3 className="h-sub">Placeholders</h3>
        <p className="band-lead">Stand-ins until the proper method exists. Indicative only.</p>
        <ul className="h-rows">
          {h.ground.filter((g) => g.measured && g.label === 'placeholder').map((g) => (
            <li key={g.key}><span>{humanize(g.key)} share of ground, from an index threshold</span><TrustBadge of="placeholder" compact /></li>
          ))}
          {h.observation.filter((o) => o.label === 'placeholder').map((o) => (
            <li key={o.cause}><span>Observed share, {causeName(o.cause)}</span><TrustBadge of="placeholder" compact /></li>
          ))}
        </ul>
      </section>

      <section className="band" aria-labelledby="fail-title">
        <h2 id="fail-title" className="band-title">Failed</h2>
        <p className="band-lead">Tested against independent data and below the bar. The bar was not moved.</p>
        <div className="h-grid">{s.failed.map((r) => <Failed key={r.id} r={r} />)}</div>
      </section>

      <section className="band" aria-labelledby="nb-title">
        <h2 id="nb-title" className="band-title">Not built, or not measurable</h2>
        <ul className="h-rows">
          {s.notBuilt.map((r) => (
            <li key={r.id}>
              <span><span className="h-id num">{r.id}</span>{floodName(r.module)}<span className="caption h-why">{sentence(r.reason)}</span></span>
              <span className="nm-chip"><i aria-hidden="true" />Not measured</span>
            </li>
          ))}
          {notMeasured.map((g) => (
            <li key={g.key}>
              <span>{humanize(g.key)} share of ground<span className="caption h-why">{sentence(g.reason)}</span></span>
              <span className="nm-chip"><i aria-hidden="true" />Not measured</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="band" aria-labelledby="lim-title">
        <h2 id="lim-title" className="band-title">Known limits</h2>
        <div className="h-limits">
          {h.limits.map((l) => <Limit key={l.id} l={l} />)}
        </div>
      </section>

      <section className="band" aria-labelledby="src-title">
        <h2 id="src-title" className="band-title">Where this page comes from</h2>
        <p className="caption">Generated by <span className="num">python -m product.site_data</span> from:</p>
        <ul className="h-plain caption num" translate="no">{h.generated_from.map((f) => <li key={f}>{f}</li>)}</ul>
        <p className="caption">Each round’s result file is read only if its SHA-256 matches the one pinned in the contract.</p>
      </section>
    </SiteChrome>
  )
}

function Limit({ l }) {
  const f = l.facts
  if (l.id === 'terrain') {
    return (
      <article className="h-limit">
        <h3>{l.title}</h3>
        <p>
          Flood scores are tested on {f.evaluation_cell_m} m cells and come from global terrain models at that
          resolution or coarser: {list(f.terrain_sources)}. A wall, kerb, culvert or drain narrower than a cell is
          invisible to them, so in dense streets a score describes the neighbourhood’s ground, not a single plot.
        </p>
      </article>
    )
  }
  if (l.id === 'clouds') {
    return (
      <article className="h-limit">
        <h3>{l.title}</h3>
        <p>
          A {f.pixel_m} m pixel needs at least {f.min_clear_observations_per_pixel} clear Sentinel-2 views in the window
          to be measured. A 100 m cell or ward needs at least {Math.round(f.min_unit_coverage * 100)}% of its area
          measured to get a value. Below that it is shown as not measured, and the observed share is reported with
          every result.
        </p>
      </article>
    )
  }
  return (
    <article className="h-limit">
      <h3>{l.title}</h3>
      <p>
        OpenStreetMap is complete in some places and thin in others. Each area is graded into one of{' '}
        {f.regimes.length} coverage regimes ({list(f.regimes.map((r) => r.replace(/_/g, ' ')))}). In the{' '}
        {list(f.warned_regimes.map((r) => r.replace(/_/g, ' ')))} regimes a warning is shown; in the{' '}
        {list(f.topology_suppressed_in.map((r) => r.replace(/_/g, ' ')))} regimes street-network metrics such as
        orthogonality are withheld.
      </p>
    </article>
  )
}
