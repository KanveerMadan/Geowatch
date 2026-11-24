# Beira independent optical review

Two reviewers agreed that two 30 m cells had visibly dry exposed ground on 26 March 2019. Neither identified a flooded cell that the other could also confirm. The nine-site diagnostic supplies no training labels.

The comparison used 4 March and 26 March Maxar Open Data RGB images from the legacy Cyclone Idai collection. The second image matched the Sentinel-1 observation date, 11 days after the flood incident anchor. It describes visible conditions that day. The study window contains 21,300 model cells. Nine centres were fixed at the 20%, 50% and 80% positions along each grid axis. Each reviewer inspected the same dated pair over 150 m of context and classified its marked central 30 m cell before seeing the radar classification. The source TIFFs have approximately 0.5 m pixel spacing. The review used the vendor's first approximately 1 m pyramid level.

| Site | First reading | Second reading | Interpretation |
|---|---|---|---|
| S01 | Dry | Dry | Paved container yard with exposed ground between vehicles. |
| S02 | Ambiguous | Ambiguous | Haze in the earlier view; structures, debris and dark surfaces in the later view. |
| S03 | Ambiguous | Ambiguous | Roofs and vegetation obscure the ground. |
| S04 | Dry | Dry | Exposed road junction and yard around a corner building. |
| S05 | Ambiguous | Ambiguous | A road crosses the cell, with substantial structures on both sides. |
| S06 | Ambiguous | Ambiguous | Canopies and roofs conceal the ground. |
| S07 | Ambiguous | Wet | A smooth dark surface spread around a shed. One reviewer judged it new muddy water; the other could not distinguish water from wet vegetation. |
| S08 | Dry | Ambiguous | The track is exposed, but the reviewers differed on whether low vegetation permitted a dry label. |
| S09 | Ambiguous | Ambiguous | Dense roofs and trees obscure the ground. |

The consensus raster therefore holds two dry cells, zero wet cells and 21,298 unknown cells. The first-reader snapshot holds three dry cells. Both reviewers were AI assistants. The two votes capture interpretation disagreements; human adjudication and field confirmation remain outstanding. Keep the raster as a non-commercial DEV diagnostic. This sample cannot establish city-wide sensitivity, peak flooding or precision.

The two receipts and GeoTIFFs sit under `artifacts/independent/beira/` as `maxar_review.{json,tif}` (both readings) and `maxar_single_review.{json,tif}` (first reading). The receipts include acquisition links, source rights, cell locations, observation coverage and reasons. Source imagery and local review sheets stay outside the repository. [Maxar Open Data protocol](https://maxar-marketing.s3.amazonaws.com/files/downloads/119757_opendataprotocol_2020_04.pdf) · [4 March before image](https://s3.amazonaws.com/dg-opendata/cyclone_idai/pre-event/2019-03-04/103001008ECDC900/0023320.tif) · [26 March after image](https://s3.amazonaws.com/dg-opendata/cyclone_idai/post-event/2019-03-26/103001008FABA300/0023320.tif)
