# GeoWatch web: design spec

**Read:** a global geospatial analysis product for planners and researchers,
in a restrained dark, Mapbox Studio / Linear register: the map is the
product, everything else floats over it and earns its place.
Dials: variance 4, motion 6, density 5.

Tokens live in one file, `src/design/tokens.js`. This page says how they are used.

Borrowed rigour, not looks:
- **Linear**: one type family, a tight scale, hierarchy from weight and
  colour rather than size; hairlines instead of boxes; a command palette
  that reaches every action.
- **Mapbox Studio**: the map stays full-bleed and live under every panel; the
  data layer outranks the base map.
- **Vercel**: a monochrome interface, so the few colours on screen are data.

**Base map (changed 2026-10-29 on review):** Esri World Imagery is the
default, on the globe too; the quiet dark map is a toggle. Both live in one
style and switch by visibility. Attribution is Esri's own service text.
**Esri's terms must be checked before any public deployment.**

## Rules

1. **Colour is meaning.** The interface is monochrome. Hue appears only for
   a fraction (built, vegetation, water), a trust label, or the area limit
   (warn, over). Selection is white.
2. **One badge** for trust: a pill with the label's colour, the label, and
   on hover or focus a plain sentence. Validated adds its scope note.
3. **Absent is drawn, never zero.** On the map, cells with no measurement
   are a grey hatch listed separately in the legend. In text it is
   "Not measured" with the reason one click deeper.
4. **Plain language first.** Each panel opens with one sentence. Figures and
   their units sit under "Details".
5. **Never block.** No overlay covers the map. Progress is the scan line over
   the area, plus skeletons in the panel sections still waiting.
6. **Shape lock:** controls 8 px, panels 14 px, badges full pill.
7. **The drawn box is the analysed box.** Rectangle, lasso (its bounding
   box) and point + fixed box (10 x 10 km by default, adjustable to the
   limit) all end as one `[w, s, e, n]`; its outline is drawn densified along
   parallels and meridians, so it stays a true geographic rectangle on the
   globe and on a tilted map. Drawing levels the map first.

## Screens (Step A)

Image generation was not available in this environment, so these four
written screen specs stand in for the reference images.

**1. Empty world.** A satellite globe, slowly turning, fills the screen. Top left:
the search bar (wordmark glyph, "Search a place, address or coordinates",
`/` hint) with "Draw an area" beside it. Top centre: tabs Ground / Flood /
Change, disabled until there is an area. Nothing else on screen.

**2. Search, fly-to.** Results drop below the bar (name, then the region in
`text3`). Choosing one stops the rotation and the camera eases to the place;
the globe flattens into the map as it zooms. A 2 km box (the default area,
editable) is outlined in white with its km² beside it, and the right panel
slides in: the place name, "Analyse this area", the area readout.

**3. Analysis streaming.** A white scan line sweeps across the box, over
cells that are not there yet. The right panel lists the analysis stages in
plain words, each with a state (waiting / reading / done / failed or timed
out, with a retry). Sections whose stage has finished fill in and their
numbers count up; the rest stay skeletons of the same height, so nothing
moves.

**4. Ground results.** The box fills with 100 m cells in the chosen
fraction's hue, sharpening from a blur, one fraction after another. The
panel: a one-sentence summary, three fraction rows (built, vegetation, water:
value, bar, badge) and three "Not yet measured" rows (impervious, paved,
bare). Then the notes for this area: coverage, observation and data
sources. Hovering a cell shows a small stacked bar that morphs between
cells; clicking pins the cell's breakdown in the panel. Tilting the map
raises the building footprints in 3D.

## Screens (Step B)

**5. Flood.** The 100 m cells take one flood type at a time, coloured by its
tier on one cool-to-hot ramp (`color.flood`, the contract's breaks, shared by
all five types). The panel: one sentence (the highest trusted reading, then
what failed validation, then what does not apply), one row per type (name,
what it means, tier, a five-step meter, badge), then the ward ranking. A
type with no per-pixel map is marked "area-wide" and is never painted. A
failed type can be drawn, and its legend says it is for transparency only.

**6. Change.** The analysed box carries two Sentinel-2 pictures of the same
season, split by a swipe handle; a scrubber below sets their years, with the
analysed years marked. Changed cells of one fraction lie over both: up is
filled, down is striped, unjudged is the not-measured hatch. Pictures,
cells and handle sit in one square fitted to the box's four projected
corners (`lib/overlay.js`), so they stay on the box when the map tilts.

**7. Area report.** A paper page (`color.print`), screen and A4: the box on
imagery, then Ground, Flood and Change each as a sentence, a table with
printed badges (validated adds its scope) and a small map; what the labels
mean; every data source.

**Mobile (720 px and below).** The panel is a bottom sheet over the map
(peek and full, dragged by its grip), tabs below it, and the map's dock
(legend, flood types, scrubber) moves into the sheet.
