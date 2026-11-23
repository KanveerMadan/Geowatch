# Independent optical evidence

The radar detector can be checked against dated imagery acquired by a different sensor. Report analyst-interpreted VHR, official mapped extents and automatically classified Sentinel-2 evidence separately. An EMS or UNOSAT delineation derived from the same Sentinel-1 acquisition belongs in the shared-sensor comparison. Retain observation dates, covered area, source, attribution and licence for every reference.

## Public Sentinel-2 corroboration

Use the Level-2A scene classification (SCL) delivered by Earth Search. Sen2Cor classifies water as 6 and vegetated/non-vegetated land as 4/5. Treat all other classes, including cloud, shadow, snow and undefined coverage, as unknown. SCL has native 20 m support. A street with a roof or tree canopy in the line of sight may appear dry even when water is present below. [Copernicus S2 processing](https://sentiwiki.copernicus.eu/web/s2-processing) · [Earth Search source and access](https://registry.opendata.aws/sentinel-2-l2a-cogs/)

* Require observed land on two distinct baseline dates and no baseline water return. Two dates reject a one-image anomaly. Consider the previous 60 days, stopping 10 days before reported onset to reduce contamination from early inundation. Clip both periods to the authorized time interval.
* Compare observations on the SAR UTC date and immediately adjacent calendar dates, limited to the reported incident interval. This accommodates the different acquisition schedules. Publish actual acquisition timestamps so users can tighten the tolerance. A one-day shift can miss street flooding that has already drained.
* On each date, overlapping granules give at most one land and one water vote per subpixel. Any observed land/water conflict during the event makes that subpixel indeterminate. Unobserved dates contribute zero votes.
* Sample SCL at the nine nested 10 m centres in a model cell. Retain a label only when all nine agree and qualify. The centroid sampling approximates a homogeneous 30 m area and does not improve native resolution. Cloud, heterogeneous boundaries and unidentified shifts create abstentions. The eligible sample will favour exposed, homogeneous surfaces. Report its denominator.
* Compare radar wet alerts with positive optical detections and clear-surface controls. A visibly dry roof provides no proof about the street beneath. Permanent water handling is inherited from the packaged detector's domain; exclude it when scoring. Coherent seasonal expansion or irrigated fields can still mimic flood water.

Writes `independent/{event}/s2_ref.tif` (1 new visible water, 0 visible non-water, 255 unknown) and `reference.json` with acquisition identifiers, timing, effective resolution, label counts and provenance. An all-255 file records an opportunity without usable optical evidence. Preserve the exact affine, CRS and shape of the consumer grid.

## Positive-only and higher-resolution references

An EMS activation AOI is the requested geography. Only reference areas with documented observation and wet/dry classification can supply both classes. When a product supplies only flood polygons, evaluate supported positive recall, and leave the complement unknown. Use the source acquisition time for matching. [CEMS product manual](https://emergency.copernicus.eu/mapping/sites/default/files/files/JRCTechnicalReport_2020_Manual%20for%20Rapid%20Mapping%20Products_final.pdf)

Groundsource geocodes news accounts. A geocoded city's polygon or centroid does not locate a flooded street. Use a dated independent report near a precise, described landmark only when the uncertainty and full supported area are known. A news point checks a site and cannot label a 30 m pixel without verifying footprint alignment. GFD aggregates MODIS observations over events at nominal 250 m support, so it can identify incidents and coarse flooded landscapes. [Google Groundsource](https://www.research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/) · [Global Flood Database](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1)

Vantor/Maxar Open Data before/after imagery can resolve streets where weather, shadows, viewpoint and acquisition time permit. Check each source independently of the detector's labels; keep non-commercial VHR-derived annotations in a separately attributed reference product. [Maxar Open Data protocol](https://maxar-marketing.s3.amazonaws.com/files/downloads/119757_opendataprotocol_2020_04.pdf)
