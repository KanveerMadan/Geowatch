/*
 * GeoWatch design tokens: the one source for type, spacing, colour, radius,
 * elevation, layering and motion. CSS reads them as custom properties
 * (applyTokens writes them onto :root); MapLibre paint and Motion springs
 * import them directly. Nothing else in web/ defines a colour, size or timing.
 *
 * Colour carries meaning, so the interface itself is monochrome. Hue is
 * spent only on data (one hue per fraction), on trust (one per label) and
 * on the area limit (warn / over).
 */

export const font = {
  sans: "'Geist Variable', ui-sans-serif, system-ui, sans-serif",
  mono: "'Geist Mono Variable', ui-monospace, SFMono-Regular, monospace",
}

// [size px, line-height px, weight, letter-spacing em]
export const type = {
  micro: [11, 14, 520, 0.01],      // legend ticks, badge labels
  caption: [12, 16, 460, 0],       // secondary lines, sources
  body: [13, 19, 420, 0],          // panel text
  lead: [15, 22, 460, -0.005],     // the plain-language headline of a panel
  title: [17, 24, 560, -0.01],     // panel titles
  figure: [26, 30, 520, -0.02],    // key numbers (mono, tabular)
  display: [30, 34, 600, -0.025],  // the place name
}

// 4 px grid.
export const space = { 0: 0, 0.5: 2, 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48, 16: 64 }

// Rule: controls 8, panels 14, badges and chips full pill. Nothing else.
export const radius = { control: 8, panel: 14, pill: 999 }

export const color = {
  canvas: '#0a0c0f',                 // behind the map, and the page while it loads
  surface: 'rgba(17, 19, 23, 0.84)', // floating panels, over a 20 px blur
  surfaceSolid: '#121418',           // the same panel with transparency reduced, and print
  raised: '#1b1e24',                 // hover / pressed rows, inputs
  hairline: 'rgba(255, 255, 255, 0.08)',
  hairlineStrong: 'rgba(255, 255, 255, 0.16)',
  text: '#eceef1',                   // 15.9:1 on surfaceSolid
  text2: '#a8aeb8',                  // 8.3:1
  text3: '#858c97',                  // 5.4:1, the faintest text allowed
  focus: '#9ecbff',                  // focus ring only
  select: '#ffffff',                 // selected cell outline, drawn area, scan line
  warn: '#f4b740',                   // area near the limit
  danger: '#ff6b5b',                 // area over the limit, stage failed
  data: {
    built: '#ff5fa2',
    vegetation: '#46d18c',
    water: '#4aa8ff',
    notMeasured: '#5d636d',          // drawn as a hatch, never as a value on a scale
  },
  trust: {
    validated: '#2dd4bf',
    experimental: '#b5a3ff',
    placeholder: '#a3a9b3',
    failed: '#ff6b5b',
    retired: '#7a808a',
  },
}

export const elevation = {
  panel: '0 0 0 1px rgba(255,255,255,0.06) inset, 0 16px 40px -12px rgba(0,0,0,0.6), 0 2px 8px rgba(0,0,0,0.35)',
  popover: '0 0 0 1px rgba(255,255,255,0.08) inset, 0 24px 60px -16px rgba(0,0,0,0.7)',
  blur: 20,
}

// Systemic layers only.
export const layer = { map: 0, mapOverlay: 10, panel: 20, popover: 30, palette: 40, toast: 50 }

export const breakpoint = { mobile: 720 }

export const motion = {
  // Panels, sheets and the hover chart: physical, settles without overshoot.
  spring: { type: 'spring', stiffness: 420, damping: 38, mass: 0.9 },
  springSoft: { type: 'spring', stiffness: 220, damping: 30 },
  ease: [0.16, 1, 0.3, 1],
  duration: { fast: 0.12, base: 0.2, slow: 0.36 },
  flyTo: { ms: 2600, curve: 1.6 },          // search: camera flies, the globe flattens on arrival
  globe: { degPerSecond: 2.4, idleZoom: 1.6 },
  countUpMs: 700,                          // numbers arriving
  scan: { periodMs: 2200 },                // the sweep while stages run
  reveal: { blurPx: 8, ms: 650, staggerMs: 180 }, // cells resolving, one fraction after another
  layerCrossfadeMs: 280,                   // tab switches
  // prefers-reduced-motion: every animation above becomes this cross-fade or nothing.
  reduced: { duration: 0.12 },
}

export function applyTokens(root = document.documentElement) {
  const set = (k, v) => root.style.setProperty(k, v)
  set('--font-sans', font.sans)
  set('--font-mono', font.mono)
  for (const [name, [size, lh, weight, track]] of Object.entries(type)) {
    set(`--t-${name}-size`, `${size}px`)
    set(`--t-${name}-lh`, `${lh}px`)
    set(`--t-${name}-weight`, String(weight))
    set(`--t-${name}-track`, `${track}em`)
  }
  for (const [k, v] of Object.entries(space)) set(`--s-${String(k).replace('.', '_')}`, `${v}px`)
  for (const [k, v] of Object.entries(radius)) set(`--r-${k}`, `${v}px`)
  for (const [k, v] of Object.entries(color)) {
    if (typeof v === 'string') set(`--c-${k}`, v)
    else for (const [kk, vv] of Object.entries(v)) set(`--c-${k}-${kk}`, vv)
  }
  set('--e-panel', elevation.panel)
  set('--e-popover', elevation.popover)
  set('--e-blur', `${elevation.blur}px`)
  for (const [k, v] of Object.entries(layer)) set(`--z-${k}`, String(v))
  set('--ease', `cubic-bezier(${motion.ease.join(',')})`)
  for (const [k, v] of Object.entries(motion.duration)) set(`--d-${k}`, `${v * 1000}ms`)
}
