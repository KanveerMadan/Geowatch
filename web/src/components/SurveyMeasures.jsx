import { humanize } from '../lib/contract.js'
import { num } from '../lib/changeHistory.js'

const area = (v) => Number.isFinite(v) ? num(v) + ' m²' : 'Unavailable'
const dates = (interval) => {
  if (!Array.isArray(interval) || interval.length !== 2) return null
  return interval[0] === interval[1] ? interval[0] : interval[0] + ' through ' + interval[1] + ' (inclusive)'
}
function sourceUrl(source) {
  const url = source?.url || source?.resource_url || source?.source
  try {
    const u = new URL(url)
    return ['https:', 'http:'].includes(u.protocol) ? u.href : null
  } catch { return null }
}

export default function SurveyMeasures({ surveys, provenance }) {
  const items = Object.entries(surveys ?? {})
  const sources = new Map((provenance ?? []).map((row) => [row.name, row]))
  if (!items.length) return <p className="caption">Physical gain and loss are unavailable without overlapping dated surveys here.</p>
  return <dl className="kv">{items.map(([name, v]) => {
    const source = sources.get(name)
    const before = dates(v.before_interval ?? source?.before_interval) ?? v.before ?? source?.before
    const after = dates(v.after_interval ?? source?.after_interval) ?? v.after ?? source?.after
    const uncertainty = v.uncertainty_status ?? source?.uncertainty_status
    const url = sourceUrl(source)
    return <div key={name}><dt>{humanize(name)}</dt><dd>
      {area(v.gain_m2)} gained · {area(v.loss_m2)} lost · {area(v.net_m2)} net
      <span className="kv-src">Joint survey area {area(v.joint_area_m2)}</span>
      {before && <span className="kv-src">First survey · {before}</span>}
      {after && <span className="kv-src">Second survey · {after}</span>}
      {uncertainty && <span className="kv-src">{humanize(uncertainty)}.</span>}
      {source && <span className="kv-src">{url ? <a href={url}>{source.source ?? 'Survey source'}</a> : source.source}
        {source.license && <> · {source.license}</>}</span>}
    </dd></div>
  })}</dl>
}
