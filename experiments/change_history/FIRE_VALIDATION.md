# Wildfire incident validation

GeoWatch confirmed greenness loss at **8 of 10 verified wildfire cells**. Among the eight, confirmation came 10–57 days after the recorded incident ignition, with a median of 18 days. Electra had a fully observed greenness series and no confirmation. Quartz also went unconfirmed and lacked continuous greenness coverage.

The study sampled one high-severity 100 m cell per selected incident from the 2022 contiguous-US MTBS wildfire archive. The register started with 419 wildfire features. Of these, 188 had a unique incident and independently verified Landsat pre-fire and post-fire acquisitions spanning ignition. The original spatial screening identified 65 incident candidates. The fixed geography rule selected ten for testing. The 55 reserved incidents would need the same coordinate audit before future use.

## Correction to the registered locations

The original spatial selector returned coordinates that lay inside each fire boundary. A separate reduction at the exact coordinates found all 25 fixed 20 m centres in the high-severity class for only three cells. Seven original cells contained between three and 20 high-severity centres. The original run is retained as an audit record. Its detections cannot establish sensitivity on the intended high-severity sample.

Before inspecting original wildfire detection scores, an amendment fixed the same incident IDs, detector settings, dates and outcome. It searched a 4.1 km square around each original cell and selected the geographically nearest eligible square, with ties resolved by easting and northing. A second direct calculation required all 25 centres at each corrected location to be high severity and in a single mapped fire perimeter, plus containment of the full square in its incident. Seven cells moved 100 m and three kept their coordinates. Every incident remained in the sample.

The independent references are the USGS/USFS Monitoring Trends in Burn Severity perimeters and severity classes based on dated Landsat scenes. The detector uses Sentinel-2. The primary outcome is confirmation of a greenness decrease within 90 days of regional ignition. Greenness loss can have other causes, and the local burn date may be later than ignition. This design tests large, documented fires. It does not estimate accuracy for small fires, wildfire-cause classification or false alarms.

The verified replay uses the distributed locked manifest and a dedicated source cache. Set GEE_PROJECT_ID for an authenticated Earth Engine project, then run:

```sh
python -m experiments.change_history.fire_support_replay --cache /tmp/gwc-fire-verified
```

[Original protocol](known_change_fire_protocol.md) · [Original incident roster](known_change_fire_manifest.json) · [Corrected coordinates, verification counts and amendment](fire_support_verified.json) · [Verified results](fire_support_result.json) · [USGS/USFS MTBS](https://www.mtbs.gov/)
