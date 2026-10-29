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
  data layer outranks the base map, which stays dark and quiet.
- **Vercel**: a monochrome interface, so the few colours on screen are data.

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

## Screens (Step A)

Image generation was not available in this environment, so these four
written screen specs stand in for the reference images.

**1. Empty world.** A dark globe, slowly turning, fills the screen. Top left:
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
