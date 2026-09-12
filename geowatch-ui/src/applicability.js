/*
 * Applicability reading — 04_FINDINGS_LEDGER.md C32, build item 41.
 *
 * `applicability` appeared exactly once in all of geowatch-ui/src/, as
 * `layer.intersection_type === 'aoi_total_given_layer_applicability'` — an
 * unrelated string comparison. `result.applicability` itself was never read,
 * and it was not in NAV_SECTIONS. C14 -> C20 -> C32 is one signal dying three
 * times; item 40 fixed the first two deaths, this is the third.
 *
 * THIS MODULE READS, IT NEVER RE-DERIVES.
 *
 * Item 40 attaches an `applicability` flag to every susceptibility, exposure
 * and risk block in the backend, including the dependency chain that produced
 * it. The temptation here is to recompute trust in JavaScript from
 * `unknown_pct` and a threshold. That would recreate C31 exactly: a Python
 * comment asserting a JavaScript constant must match, with 0 of 8 categories
 * actually matching. Two sources of truth for one rule drift, and the drift is
 * silent.
 *
 * So every function below is a reader. The only judgement it makes is
 * presentation: how loud to be, and which of the backend's own words to show.
 *
 * Kept as plain JS, separate from App.jsx, so it can be tested without a
 * browser or a component renderer.
 */

// Worst first. Mirrors _TRUST_ORDER in perception/applicability_gate.py; the
// ordering is only used to pick the loudest thing to say, never to decide a
// verdict, so the two cannot disagree about a result.
export const TRUST_RANK = {
  out_of_distribution: 0,
  degraded: 1,
  in_distribution: 2,
  unknown: 3,
}

export const TRUST_META = {
  out_of_distribution: {
    label: 'Model out of distribution',
    severity: 'alert',
    headline: 'These land-cover results are not reliable for this area.',
    plain:
      'Too much of this scene could not be confidently labelled at all, so the ' +
      'land-cover model is operating outside the range it was tested on. ' +
      'Numbers derived from it are still shown, with the reason attached, ' +
      'rather than hidden — but they should not be used as findings.',
  },
  degraded: {
    label: 'Model degraded',
    severity: 'warn',
    headline: 'These land-cover results are weaker than usual for this area.',
    plain:
      'Across a large share of this scene the model was torn between ' +
      'categories it is known to confuse. The results are usable with care, ' +
      'but read the affected numbers as indicative rather than settled.',
  },
  in_distribution: {
    label: 'Model in distribution',
    severity: 'ok',
    headline: 'The land-cover model is operating within its tested range here.',
    plain:
      'Enough of this scene was confidently labelled that the model is inside ' +
      'the conditions it was validated against.',
  },
  unknown: {
    label: 'Not checked',
    severity: 'unknown',
    headline: 'No reliability verdict was recorded for this run.',
    plain:
      'This run carries no applicability block. That most likely means it was ' +
      'produced before reliability gating existed, so treat the absence as ' +
      '"not checked" — not as "checked and fine".',
  },
}

/** The root of the dependency chain: the semantic model's own verdict. */
export function landcoverTrust(result) {
  const status = result?.applicability?.urban_landcover_model?.status
  return status && status in TRUST_RANK ? status : 'unknown'
}

/** The backend's reason string for that verdict, if it gave one. */
export function landcoverReason(result) {
  return result?.applicability?.urban_landcover_model?.reason || null
}

/**
 * The flag a single block carries, as emitted by the backend.
 *
 * Returns null when the block has no flag at all. That is deliberately NOT
 * normalised into a cheerful default: a missing flag means nobody gated this
 * value, which is the precise condition C14 described, and a UI that renders
 * it as trusted would reintroduce the bug at the last hop.
 */
export function blockFlag(block) {
  const flag = block?.applicability
  return flag && typeof flag === 'object' ? flag : null
}

/** True when a block is explicitly flagged untrustworthy by the backend. */
export function isFlagged(block) {
  const flag = blockFlag(block)
  if (!flag) return false
  return flag.out_of_distribution === true || flag.degraded === true
}

/**
 * Everything the report needs to decide how loudly to speak, derived only from
 * what the backend emitted.
 */
export function reportApplicability(result) {
  const trust = landcoverTrust(result)
  const meta = TRUST_META[trust]

  const susceptibility = result?.susceptibility || {}
  const riskLayers = result?.risk?.by_evidence_layer || {}
  const exposureLayers = result?.exposure?.by_evidence_layer || {}

  const affected = []
  const unaffected = []
  const ungated = []

  const visit = (group, key, block) => {
    const flag = blockFlag(block)
    const entry = { group, key, flag }
    if (!flag || flag.gate === 'not_wired') ungated.push(entry)
    else if (flag.out_of_distribution || flag.degraded) affected.push(entry)
    else unaffected.push(entry)
  }

  Object.entries(susceptibility).forEach(([k, v]) => visit('susceptibility', k, v))
  Object.entries(exposureLayers).forEach(([k, v]) => visit('exposure', k, v))
  Object.entries(riskLayers).forEach(([k, v]) => visit('risk', k, v))

  return {
    trust,
    meta,
    reason: landcoverReason(result),
    severity: meta.severity,
    // The banner shouts only when there is something to shout about. A banner
    // that fires on every run teaches readers to skip it, which is how C33's
    // `{pct ? ... : '0.0%'}` made "0.0%" meaningless.
    isAlert: trust === 'out_of_distribution' || trust === 'degraded',
    hasBlock: Boolean(result?.applicability),
    affected,
    unaffected,
    ungated,
    affectedCount: affected.length,
  }
}

/** Per-mechanism rows for the reliability section's table. */
export function mechanismRows(result) {
  const app = result?.applicability || {}
  return Object.entries(app)
    .filter(([key]) => !key.startsWith('_'))
    .map(([key, value]) => ({
      key,
      status: value?.status ?? 'unknown',
      reason: value?.reason ?? null,
      isRoot: key === 'urban_landcover_model',
    }))
}
