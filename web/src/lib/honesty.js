/*
 * The honesty page's content, from web/src/generated/honesty.json, which is
 * generated from analysis/contract.py (python -m product.site_data). No
 * figure on the page is typed by hand: everything is read from that file.
 */
const AUC = new Intl.NumberFormat('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const fmtAuc = (v) => (typeof v === 'number' ? AUC.format(v) : 'not run')

const EVENT_NAME = (e) => e.replace(/_(\d{4})$/, ' $1').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
export const eventName = EVENT_NAME

/** The flood types sorted into the page's sections, in taxonomy order. */
export function floodSections(h) {
  const rows = h.flood ?? []
  return {
    validated: rows.filter((r) => r.built && r.label === 'validated'),
    experimental: rows.filter((r) => r.built && r.label === 'experimental'),
    failed: rows.filter((r) => r.built && r.label === 'failed'),
    notBuilt: rows.filter((r) => !r.built),
  }
}

/** One sentence: how a built module's verdict was reached. */
export function evidenceSentence(r, bar) {
  const ev = r.evidence
  if (!ev) return 'Not tested yet.'
  const n = ev.qualifying ?? ev.events?.length
  const what = ev.auc_kind
  const outcome = ev.verdict === 'failed' ? 'below' : 'at or above'
  return `Round ${ev.round}: ${what} ${fmtAuc(ev.auc)}${n ? ` over ${n} ${ev.auc_kind.includes('sites') ? 'sites' : 'events'}` : ''}, ${outcome} the bar of ${fmtAuc(bar.validated_if_auc_at_least)}.`
}

/** The page's headline counts, for the landing page too. */
export function floodCounts(h) {
  const s = floodSections(h)
  return { total: (h.flood ?? []).length, built: (h.flood ?? []).filter((r) => r.built).length,
    validated: s.validated.length, experimental: s.experimental.length, failed: s.failed.length,
    notBuilt: s.notBuilt.length }
}

const NUM_WORD = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']
export const numWord = (n) => NUM_WORD[n] ?? String(n)
