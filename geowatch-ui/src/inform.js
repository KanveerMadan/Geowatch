/*
 * INFORM display guard — 04_FINDINGS_LEDGER.md C8, build item 53.
 *
 * App.jsx rendered `raw_score` straight into "x / 10" with no type check, so
 * a null, a string or an object from a bad cell displayed as if it were a
 * score.
 *
 * THIS IS A TYPE GUARD, NOT A RANGE CHECK. The backend validates the range
 * (ingestion/vulnerability_sources.py, INFORM_VALID_RANGES) and sets status
 * to "unavailable" when a cell is out of range. Repeating 0-10 here would be
 * a second copy of that rule, which is the C31 drift pattern. This module
 * only refuses to print something that is not a number at all.
 *
 * Kept as plain JS, separate from App.jsx, so node can test it directly.
 */

export const MISSING = '—'

/** A finite number, formatted to `digits`, or MISSING for anything else. */
export function formatInformNumber(value, digits = 1) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return MISSING
  return value.toFixed(digits)
}

/** pct_missing_indicators is a 0-1 fraction (the source cell format is
 *  "0%"). Returns e.g. "12.0%" (the display App.jsx already used) or MISSING. */
export function formatInformFraction(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return MISSING
  return `${(value * 100).toFixed(1)}%`
}
