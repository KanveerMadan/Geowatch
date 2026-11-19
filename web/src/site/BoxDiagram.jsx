/** The landing page's picture: an illustration, not data. The drawn box is
 *  the analysed box (DESIGN.md rule 7), cut into 100 m cells; cells with no
 *  measurement are hatched, never shaded as a value (rule 3). Monochrome:
 *  no hue, because there is no data here to mean anything. */
const COLS = 12
const ROWS = 8
const CELL = 24
// Fixed, not random: a cloud-shaped gap in one corner and a stripe of
// missing imagery, the two usual reasons a cell goes unmeasured.
const GAP = new Set(['8,0', '9,0', '10,0', '9,1', '10,1', '11,1', '10,2', '0,6', '1,6', '2,6', '3,6', '4,7'])

export default function BoxDiagram() {
  const w = COLS * CELL
  const h = ROWS * CELL
  const cells = []
  for (let y = 0; y < ROWS; y += 1) {
    for (let x = 0; x < COLS; x += 1) {
      const gap = GAP.has(`${x},${y}`)
      cells.push(<rect key={`${x},${y}`} x={x * CELL} y={y * CELL} width={CELL} height={CELL}
        className={gap ? 'bd-gap' : 'bd-cell'} />)
    }
  }
  return (
    <figure className="box-diagram">
      <svg viewBox={`-12 -12 ${w + 24} ${h + 24}`} role="img" aria-labelledby="bd-cap">
        <defs>
          <pattern id="bd-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" className="bd-hatch-line" />
          </pattern>
        </defs>
        <g>{cells}</g>
        <rect x="0" y="0" width={w} height={h} className="bd-box" />
        <line x1="0" x2={w} y1="0" y2="0" className="bd-scan" />
      </svg>
      <figcaption id="bd-cap" className="caption">
        <span className="bd-key"><i className="bd-key-cell" aria-hidden="true" />Measured 100 m cell</span>
        <span className="bd-key"><i className="bd-key-gap" aria-hidden="true" />Not measured (cloud, no imagery)</span>
        <span className="bd-note">Illustration. The box you draw is the box analysed.</span>
      </figcaption>
    </figure>
  )
}
