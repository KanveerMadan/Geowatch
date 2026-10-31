/*
 * Geometry for the Change tab's swipe overlay. The before / after pictures
 * are Web Mercator PNGs of the analysed box, and the changed cells are drawn
 * in the same box, so everything lives in one square laid over the map by a
 * projective transform from its four projected corners: it stays the box on
 * a tilted or rotated map. Plain functions, tested under node.
 */

const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))

/** lon/lat -> [x, y] in [0, 1] across the box, y down (north at 0). */
export function toUnit([w, s, e, n]) {
  const yn = mercY(n), ys = mercY(s)
  return ([lon, lat]) => [(lon - w) / (e - w), (yn - mercY(lat)) / (yn - ys)]
}

/** The CSS matrix3d taking an L x L square (corners (0,0), (L,0), (L,L),
 *  (0,L)) to four screen points, in that order: NW, NE, SE, SW. */
export function homography(L, [p0, p1, p2, p3]) {
  // Unit square -> quad (Heckbert), then pre-scale by 1/L.
  const [x0, y0] = p0, [x1, y1] = p1, [x2, y2] = p2, [x3, y3] = p3
  const dx1 = x1 - x2, dx2 = x3 - x2, dy1 = y1 - y2, dy2 = y3 - y2
  const sx = x0 - x1 + x2 - x3, sy = y0 - y1 + y2 - y3
  const den = dx1 * dy2 - dx2 * dy1
  const g = den ? (sx * dy2 - dx2 * sy) / den : 0
  const h = den ? (dx1 * sy - sx * dy1) / den : 0
  const a = x1 - x0 + g * x1, b = x3 - x0 + h * x3, c = x0
  const d = y1 - y0 + g * y1, e = y3 - y0 + h * y3, f = y0
  // Column-major 4x4 for matrix3d; z passes through.
  const m = [a / L, d / L, 0, g / L, b / L, e / L, 0, h / L, 0, 0, 1, 0, c, f, 0, 1]
  return `matrix3d(${m.map((v) => +v.toPrecision(10)).join(',')})`
}

/** Apply a homography's math to a point, for tests. */
export function applyHomography(L, quad, [x, y]) {
  const m = homography(L, quad).slice(9, -1).split(',').map(Number)
  const X = m[0] * x + m[4] * y + m[12]
  const Y = m[1] * x + m[5] * y + m[13]
  const W = m[3] * x + m[7] * y + m[15]
  return [X / W, Y / W]
}

const outer = (g) => (g?.type === 'Polygon' ? [g.coordinates[0]] : g?.type === 'MultiPolygon' ? g.coordinates.map((p) => p[0]) : [])

/** Each cell's rings in unit coordinates, with its bounds for hit tests. */
export function unitCells(fc, bbox) {
  const u = toUnit(bbox)
  return (fc?.features ?? []).map((f) => {
    const rings = outer(f.geometry).map((r) => r.map(u))
    const xs = rings.flat().map((p) => p[0]), ys = rings.flat().map((p) => p[1])
    return { id: f.id ?? f.properties?.unit_index, props: f.properties ?? {}, rings,
      box: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] }
  })
}

const r5 = (v) => Math.round(v * 1e5) / 1e5

/** One SVG path string for a set of unit cells (viewBox 0 0 1 1). */
export function pathOf(cells) {
  let d = ''
  for (const c of cells) {
    for (const ring of c.rings) {
      d += `M${ring.map(([x, y]) => `${r5(x)} ${r5(y)}`).join('L')}Z`
    }
  }
  return d
}

function inRing([x, y], ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

/** The cell under a unit-space point, or null. */
export function cellAt(cells, p) {
  for (const c of cells) {
    const [x0, y0, x1, y1] = c.box
    if (p[0] < x0 || p[0] > x1 || p[1] < y0 || p[1] > y1) continue
    if (c.rings.some((r) => inRing(p, r))) return c
  }
  return null
}
