/*
 * Category colours — read from the result, never defined here.
 * 04_FINDINGS_LEDGER.md C31, build item 43.
 *
 * This file previously did not exist; App.jsx carried a `CAT_COLORS` literal
 * that was supposed to match `ingestion/inference.py`'s `CATEGORY_COLORS_RGB`,
 * on the authority of a Python comment saying so. 0 of 8 matched. Worst was
 * dense_vegetation, Δ(34, 37, 75) — forest green in the server-rendered
 * overlay, mint green in the legend printed next to it.
 *
 * The deltas were small enough to read as opacity variation, which is what made
 * them dangerous: a user comparing legend to overlay would not conclude "these
 * disagree", they would conclude "that patch is a slightly different shade".
 *
 * THE RULE THIS FILE ENFORCES: there is no palette in the frontend. Colours
 * arrive in `result.landcover.palette`, emitted by configs/palette.py. Drift is
 * not prevented by discipline here, it is impossible, because there is nothing
 * on this side to drift.
 *
 * The one exception is LEGACY_FALLBACK below, and it is deliberately not a
 * palette: see its comment.
 */

/*
 * Runs produced BEFORE item 43 carry no `landcover.palette`. Without something
 * to fall back on, opening an archived result would render every category
 * colourless.
 *
 * These are the OLD frontend values, kept verbatim, precisely BECAUSE they are
 * the wrong ones. An archived run was rendered with these colours when it was
 * produced, so showing it with them now is faithful to what the user saw. They
 * must never be used for a run that carries a palette, and `categoryColor()`
 * only reaches them when `landcover.palette` is absent entirely. A test asserts
 * that.
 *
 * This is not a second source of truth. It is a compatibility shim for data
 * that predates the single source, and it is frozen — no colour is ever added
 * here again.
 */
const LEGACY_FALLBACK = Object.freeze({
  dense_informal_roofing: '#e0625a',
  sparse_informal_roofing: '#e8a35a',
  unpaved_dirt_road: '#b48c50',
  paved_road: '#8888c8',
  open_drainage_channel: '#50a0dc',
  standing_water: '#4a90e2',
  vegetation_clearing: '#d8c85a',
  active_construction: '#c878d0',
  dense_vegetation: '#5ed99b',
  open_waste: '#8c6438',
  unknown: '#716fa0',
})

/** Last resort for a category nobody has a colour for at all. */
export const NO_COLOR = '#888888'

/** The emitted palette block, or null for a run that predates item 43. */
export function paletteOf(result) {
  const p = result?.landcover?.palette
  if (!p || typeof p !== 'object') return null
  if (!p.colors || typeof p.colors !== 'object') return null
  return p
}

/** True when this run carries its own palette (i.e. is not legacy). */
export function hasPalette(result) {
  return paletteOf(result) !== null
}

/**
 * The colour for one category, for this run.
 *
 * Resolution order, and the order matters:
 *   1. the palette emitted with the result — always wins when present;
 *   2. the legacy fallback, ONLY when no palette was emitted at all;
 *   3. NO_COLOR.
 *
 * Step 2 is never reached for a modern run, including for a category the
 * palette happens not to list. That is intentional: falling back per-category
 * would mean a run could render half its legend from the backend and half from
 * here, which is the split-brain state C31 described, just finer-grained.
 */
export function categoryColor(result, category) {
  if (!category) return NO_COLOR
  const palette = paletteOf(result)
  if (palette) return palette.colors[category] || NO_COLOR
  return LEGACY_FALLBACK[category] || NO_COLOR
}

/**
 * Categories to draw in the legend, in emitted order, each with its colour.
 *
 * Reads the palette's own category lists rather than a hardcoded array, so a
 * category added to configs/palette.py appears in the legend with no frontend
 * edit — the same property item 43 requires for colours.
 *
 * `unknown` is excluded: it is a rendering state, not a land-cover type, and
 * the legend has never listed it.
 */
export function legendEntries(result) {
  const palette = paletteOf(result)
  const names = palette
    ? Object.keys(palette.colors)
    : Object.keys(LEGACY_FALLBACK)
  return names
    .filter(name => name !== 'unknown')
    .map(name => ({ category: name, color: categoryColor(result, name) }))
}

/** For tests and diagnostics: is this run rendering from legacy colours? */
export function isLegacyRender(result) {
  return !hasPalette(result)
}
