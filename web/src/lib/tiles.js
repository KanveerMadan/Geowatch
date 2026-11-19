/*
 * A box on imagery without a map library: the Web Mercator tiles that cover
 * a w x h pixel window centred on the box, and the box's outline in that
 * window. For the gallery's thumbnails, where a WebGL map per card would
 * cost more than the page.
 */
const TILE = 256
const lonX = (lon, z) => ((lon + 180) / 360) * TILE * 2 ** z
const latY = (lat, z) => {
  const s = Math.sin((lat * Math.PI) / 180)
  return (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * TILE * 2 ** z
}

/** {z, tiles: [{x, y, left, top}], box: {left, top, width, height}}, the box
 *  filling at most `fill` of the window. */
export function tileWindow([w, s, e, n], width, height, { fill = 0.62, maxZoom = 18 } = {}) {
  let z = maxZoom
  while (z > 1 && (lonX(e, z) - lonX(w, z) > width * fill || latY(s, z) - latY(n, z) > height * fill)) z -= 1
  const cx = (lonX(w, z) + lonX(e, z)) / 2
  const cy = (latY(n, z) + latY(s, z)) / 2
  const x0 = cx - width / 2
  const y0 = cy - height / 2
  const tiles = []
  for (let ty = Math.floor(y0 / TILE); ty <= Math.floor((y0 + height) / TILE); ty += 1) {
    for (let tx = Math.floor(x0 / TILE); tx <= Math.floor((x0 + width) / TILE); tx += 1) {
      tiles.push({ x: tx, y: ty, left: tx * TILE - x0, top: ty * TILE - y0 })
    }
  }
  const box = { left: lonX(w, z) - x0, top: latY(n, z) - y0, width: lonX(e, z) - lonX(w, z), height: latY(s, z) - latY(n, z) }
  return { z, tiles, box, tileSize: TILE }
}
