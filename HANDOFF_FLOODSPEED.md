# Flood-speed handoff for Round 3

The local OSM query matched the archived water features in all three Chicago comparisons. The rain export reproduced all 15 direct rasters. Its first run took longer. Reuse of the cached export took less than a second. The survey package adds 427 distinct 30 m cells with field evidence of peak inundation across four hurricanes. These are sparse development observations.

## Local OSM

Run with Python 3.11+, pyosmium (Python package `osmium`), Shapely 2, SQLite with R-tree support, and the `osmium` command-line program. The ten Geofabrik extracts are already in the local disk cache. Other machines can fetch just the regions they need.

```python
from pathlib import Path
from tools.osm_local import query

cache = Path.home() / ".cache/geowatch/floodspeed"
features = query((-87.68, 41.70, -87.65, 41.73),
                 cache / "pbf/IL.osm.pbf", cache / "index")
for feature in features["features"]:
    classes = feature["properties"]["classes"]
```

The feature classes are `water_bodies`, `waterways`, `drains_canals`, `embankments`, `rail_bridges` and `buildings`. A feature may have several classes. The first query reads the regional extract and builds a padded local SQLite spatial index. Subsequent boxes inside that envelope reuse the index. Very long objects crossing the padded extract without a node inside it can be missed. Query each relevant extract and deduplicate by OSM element ID for cross-border boxes.

`python -m tools.osm_fetch ~/.cache/geowatch/floodspeed/pbf IL NY CA LA FL PK BD IN SS NG` fetches the configured regions and checks the supplier MD5. Add a Geofabrik path to `tools/regions.json` to add a region. Current PBFs on this machine are contemporary OSM snapshots. For as-of-event historical predictors, supply date-appropriate PBFs. [Extract sizes and hashes](tools/floodspeed_results/osm_extracts.json) · [OSM attribution and ODbL](https://www.openstreetmap.org/copyright)

| Archived Chicago unit | Matched / archived | Jaccard |
|---|---:|---:|
| 2019-04-29 b03_07 | 53 / 53 | 100% |
| 2019-05-27 b02_06 | 284 / 284 | 100% |
| 2021-06-24 b02_07 | 304 / 304 | 100% |

The comparison used the common water-feature query and element IDs. It measures water-feature identity on these three boxes. Polygon geometry and the other feature classes still lack an archived comparison. [OSM test receipts](tools/floodspeed_results/osm_comparison.json)

## Rain export

Use the project’s Earth Engine Python environment with Earth Engine and Google Drive access. The code imports the existing rain reducers from `susceptibility.hydro_rasters`. Run from the repository root with the existing project environment loaded.

```python
import json
import os
from pathlib import Path
from tools.ee_batch import export, unit_layers

units = json.loads(Path("tools/rain_dev.json").read_text())
cache = Path.home() / ".cache/geowatch/floodspeed/rain"
table = export(units, cache, os.environ["GEE_PROJECT_ID"])
for unit in units:
    layers = unit_layers(unit, table)
    # Each array is on this unit's snapped 30 m UTM grid.
```

For the five shipped units, pass `Path("tools/floodspeed_results/rain_native.csv")` directly to `unit_layers` for fully offline use. Each input specifies a unique `id`, ISO `date` and WGS84 `bbox` in west, south, east, north order. Use modest lists of historical boxes. Earth Engine exports the distinct native CHIRPS and IMERG cells to Drive, then the local code reconstructs annual rainfall, design-day rainfall and heavy-rain intensity. The 30 m output repeats coarser observations. Missing precipitation remains NaN. The shared local EE lock serializes cooperating clients. Keep other synchronous EE callers on that same lock.

| Five-unit test | Result |
|---|---:|
| Maximum absolute difference across 15 layers | 0 |
| Nodata disagreements | 0 pixels |
| Cold batch export | 20 min 30 s |
| Direct builds | 16 min 35 s |
| Cached lookup and reconstruction of all 15 layers | 0.18 s on the test Mac |

The units were Beira, Dharavi, Kerala 2018, Ida–Lafitte and Laura–Cameron. The stopwatch for the first cache lookup in the comparison includes contention with another caller. The separate hot-cache benchmark measures local reuse. There is no timing result for a whole four-degree tile. [Pixel comparisons](tools/floodspeed_results/rain_comparison.json) · [Cached timing](tools/floodspeed_results/rain_hot.json)

## Peak inundation from field surveys

| Storm | Incident anchor | Screened marks | Wet cells | Ambiguous cells |
|---|---|---:|---:|---:|
| Harvey | 2017-08-25 | 1,456 | 254 | 827 |
| Irma | 2017-09-10 | 352 | 80 | 245 |
| Florence | 2018-09-14 | 21 | 0 | 21 |
| Michael | 2018-10-10 | 420 | 88 | 185 |
| Laura | 2020-08-27 | — | 0 | — |
| Sally | 2020-09-16 | — | 0 | — |
| Ida, Manville NJ | 2021-09-02 | 22 | 5 | 14 |

Each storm ZIP contains a `marks.csv` audit and UTM tiles with `flooded`, `valid`, `state` and JSON `meta`. State 0 is unobserved, 1 observed dry, 2 observed flooded, and 3 ambiguous. The Boolean valid mask includes states 1 and 2 only. Unknown and ambiguous cells contribute no negatives. Each survey cell represents inundation near its centre, without an inferred flood extent across neighboring land. Multiple marks can fall in one cell. All four states are supported and surveyed water heights alone supply zero dry cells.

The terrain source is the US 10 m 3DEP mosaic used by Round 3. Compare NAVD88 heights at the survey mark, accept only the containing 30 m cell with a mark no farther than 15 m from centre, and require water above terrain by more than 1 m plus the survey margin. The 1 m allowance is a screening choice for vertical and spatial error. Site-specific error may exceed it. The minimum mark margin is 0.2 ft. JRC permanent water (occurrence ≥80%) and locations without valid water-history observations are excluded. Differing supported states within a cell abstain. The terrain and water mask are retrospective. Keep the source dependence in mind when testing terrain predictors.

The primary STN endpoint was inaccessible from this run. Historical storm-specific ArcGIS mirrors retain the survey records. Florence covers one South Carolina corridor. For Laura and Sally, accessible reports had coordinates too coarsely rounded for a 30 m cell or cartographic positions without a verifiable 30 m location. The Manville subset is inland flooding during Ida. Attribute USGS, the mirror and EC JRC/Google. Use the Rutgers-derived Manville subset for research until its mirror terms are confirmed. [Source and licence ledger](tools/floodspeed_results/peak_sources.json) · [Per-tile counts, dates and SHA256](tools/floodspeed_results/peak/tiles.csv)

Every storm has a NOAA six-minute verified gauge maximum within the specified event window. Its time applies to that station. MLLW gauge heights are kept out of the NAVD88 terrain comparison. For Harvey and Irma, the audit links individual marks to local peak timestamps where published, including the source's estimated-time flag. For other marks the exact local time is unknown. A later field visit can measure a physical trace left at the peak. Survey dates and over-48-hour flags are recorded separately. Ida's Louisiana gauge cannot date the New Jersey flood. [Station peaks and observation coverage](tools/floodspeed_results/tide_peaks.json) · [Local timing joins](tools/floodspeed_results/local_peaks.csv)

## Same-day optical evidence

A local peak and conditions in a later photo answer different questions. Use the optical labels for visible surface conditions on their recorded acquisition date. Each accepted US cell has an image crop with its actual 30 m footprint outlined. The US images come from NOAA NGS. USDA pre-storm aerials and SpaceNet/Maxar pre-event imagery help identify surfaces where the water hides the original land use. GeoWatch's new visual readings were made by an assistant. They have not undergone independent human adjudication. [Per-cell evidence, dates and rights](tools/floodspeed_results/optical/review.json) · [Per-file counts and hashes](tools/floodspeed_results/optical/tiles.csv)

| Incident and place | Optical date | Wet / dry with same-day counterpart | Additional exposed cells without a local counterpart |
|---|---|---:|---:|
| Harvey, Houston | 2017-08-30 | 2 / 2 | 0 |
| Florence, Kinston and New Bern | 2018-09-19 | 2 / 2 in Kinston | 1 in New Bern |
| Ida, Plaquemines Parish and LaPlace | 2021-08-31 and 2021-09-01 | 5 / 2 in Plaquemines | 1 in LaPlace |
| Irma, Jacksonville | 2017-09-14 | — | 1 urban parking cell |
| Michael, Mexico Beach area | 2018-10-11 | — | 1 |
| Laura, Cameron | 2020-08-29 | — | 1 |
| Sally, Gulf Shores | 2020-09-19 | — | 1 |
| Idai, Beira | 2019-03-26 | 1 / 2, research diagnostic | 0 |
| Nile flooding, Khartoum | 2020-08-29 | — | 0 |
| Honduras flooding, San Pedro Sula | 2020-11-25 | — | 0 |

In Houston, standing water surrounds cars on a road approach, while a nearby exposed intersection shows lane markings. In Kinston, water covers paths and grass clearly visible before the storm. In Plaquemines, the raised access road was exposed while adjacent low land and refinery surfaces were underwater. The two dry Plaquemines cells represent the levee access road and verge. The urban LaPlace street was observed on a different date. The Beira dry samples cover an exposed port yard and a road/yard junction. Their same-day wet companion comes from a published hand-annotated PlanetScope product in the same incident. The Maxar readings come from the earlier urban-flood study and add **zero new independent incidents**. Keep them in their separate research file. [Urban Flood Observations](https://doi.org/10.5281/zenodo.19698577)

For Khartoum and San Pedro Sula, the dated chips contain mapped flooding, but the reviewed urban squares mix roof, shade and street at PlanetScope resolution. No defensible dry street cell was obtained. For Irma, Michael, Laura and Sally, the exposed samples describe the photo date. A recovery-date dry label can penalize a model that correctly predicts peak inundation. Keep these samples out of peak and paired-wet/dry training. [Search and abstention receipts](tools/floodspeed_results/optical/search_receipts.json)

The separate SpaceNet file contains 23 explicitly attributed road segments from three 2021 Louisiana training chips. Its source's positive class includes water **or rubble**. The inspected raw GeoJSON also has missing flood attributes, even where a downstream CSV encodes false. We omitted those negatives. These features can support a road-obstruction diagnostic. The model importer never reads them as surface-water cells. Their exact image day was unverified. The annotations are CC BY-SA 4.0. The original Maxar Open Data imagery is CC BY-NC 4.0. [Selected road features](tools/floodspeed_results/optical/Ida_expert_roads.geojson) · [SpaceNet licence](https://spacenet.ai/sn8-challenge/) · [Authors’ annotation definitions](https://openaccess.thecvf.com/content/CVPR2022W/EarthVision/papers/Hansch_SpaceNet_8_-_The_Detection_of_Flooded_Roads_and_Buildings_CVPRW_2022_paper.pdf)

The Maxar inventory records historical collections for Harvey, Irma, Florence, Michael and Ida. The sampled Maxar view of the Houston road was uniformly white. NOAA supplies the usable Houston observation. No corresponding Laura or Sally imagery was verified in the checked legacy prefixes. A collection's presence alone supplies zero observed pixels. [Maxar source inventory](tools/floodspeed_results/maxar_inventory.json)

## Import and split

```python
from tools.floodspeed_labels import iter_labels

for meta, state in iter_labels("peak", event="Harvey"):
    observed = (state == 1) | (state == 2)
    flooded = state == 2
    grid = meta["grid"]

for meta, state in iter_labels("paired_development", event="Florence"):
    pass  # Visible-water targets at the acquisition date.
```

The reader checks each tile's SHA256, grid shape, four states, Boolean masks and pre-2022 development status. Choose one target explicitly. The other collections are `acquisition_only` and `paired_research_diagnostic`. Keep these separate. Use each tile's CRS and affine transform to place it on the model grid. Group all observations from one incident into the same development split, including different dates, sensors, cities and survey archives. A positive-only HWM tile cannot estimate false alarms or AUC on its own.

The direct gaps are precise Laura and Sally survey positions, full-surface dry labels in the two unresolved UFO cities, and same-date wet counterparts for four US storm samples. More returning light from a roof or a coordinate rounded to a kilometer would not resolve those gaps. The transferable additions here are the dated observation, exact footprint, explicit unknown mask and source receipt for each label. [File checksums](tools/floodspeed_results/SHA256SUMS)
