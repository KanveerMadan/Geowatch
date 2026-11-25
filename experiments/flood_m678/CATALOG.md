# M6–M8 event catalogue

The catalogue contains one reviewed row per named physical incident. The incident date can denote the start of flooding, the failure, or a reported crest. Use the dedicated UTC crest columns to match observations. A blank scene count means the screen could not run. Zero means the three queried collections returned no qualifying scene. Neither value describes dry ground.

The separate source leads file is a discovery index. It contains 2,239 records from the confirmed GLOF worksheet and 230 cause-matched Flood Observatory records. The latter include one additional GLOF lead. Reports can overlap, contain uncertain dates or describe releases without breaches. Lake coordinates locate the flood source. Country-only records need an independent downstream location. These rows do not measure statistical power. See the attribution and reuse terms in the root licence file.

## What the screen establishes

1. The investigator records independent incident and crest evidence in `event_evidence.json`. Approximating a downstream peak using the date a dam failed can shift the satellite match by days.
2. At USGS sites the script queries only stage observations in the documented incident window. It accepts one unqualified approved series with regular coverage and an interior maximum. Tied maxima expand the uncertainty bracket from the measurement before the earliest maximum through the one after the latest. A missing measurement prevents refinement. A conflict between a published date and the sampled maximum holds the incident for review.
3. A dated crest with no usable continuous series spans the whole local civil day. The acquisition window is the intersection of eligible windows for every possible peak time. Eight-kilometre boxes match the round-3 unit width and are fixed at the reach independently of imagery. A scene must cover the entire box. Multi-tile mosaics and partial swath coverage remain unassessed.
4. The STAC client reads only satellite identifiers, times, footprints and radar acquisition properties. Landsat Collection 2 Level 2, Sentinel-2 L2A and Sentinel-1 GRD are queried separately. Sentinel-1 needs two distinct prior acquisition days with IW, VV, the same relative orbit and direction. The search follows the round-3 60-to-6-day baseline and prior-year fallback. Matched baselines still need a check for antecedent flooding at label time. Cloud, terrain shadow, partial canopy and peak extent remain unknown from metadata. Optical and radar scene counts can include acquisitions from the same day.
5. The overlap check reads named registry and candidate metadata files at round-3 commit 5287883. It checks intersecting footprints and centres within 20 km. Repeated visits to one basin belong together when testing geographic transfer. A clean spatial screen still requires storm-alias, physical-incident and product-level checks, including the final round-3 list.

## Reproduction

From this directory, use the GeoWatch Python environment with requests, pyproj and Shapely. CACHE is an external directory for downloads. The two discovery archives are publisher-checksummed. Live gauge and satellite catalogues can be revised. Keep the cache for byte-for-byte reproduction and use a separate output directory to inspect changes.

```sh
python discover.py "$CACHE" source_leads.csv
python gauge_crests.py "$CACHE/stage"
python screen_acquisitions.py "$CACHE/stac"
python overlap.py "$(git rev-parse --show-toplevel)"
python -m unittest -q test_catalog
```

The committed CSV and JSON receipts are the recorded observation. Inspect changes before replacing a checkpoint. No command in this catalogue reads image pixels, computes a hazard score or seals a test set. The overlap command requires the pinned round-3 commit in the local Git object database.
