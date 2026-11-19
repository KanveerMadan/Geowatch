import { tileWindow } from '../lib/tiles.js'

const ESRI = (z, y, x) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`
const W = 352
const H = 176

/** The analysed box outlined on Esri World Imagery. Decorative: the card's
 *  text says what it shows. */
export default function TileThumb({ bbox }) {
  const { z, tiles, box, tileSize } = tileWindow(bbox, W, H)
  return (
    <div className="thumb" aria-hidden="true">
      <div className="thumb-inner" style={{ width: W, height: H }}>
        {tiles.map((t) => (
          <img key={`${t.x},${t.y}`} src={ESRI(z, t.y, t.x)} alt="" loading="lazy" decoding="async"
            width={tileSize} height={tileSize} style={{ left: t.left, top: t.top }} />
        ))}
        <span className="thumb-box" style={{ left: box.left, top: box.top, width: box.width, height: box.height }} />
      </div>
    </div>
  )
}
