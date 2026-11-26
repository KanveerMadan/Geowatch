# Selecting the M6–M8 evaluation events

These rules precede candidate selection. They apply to the historical evaluation of inundation conditional on a documented event. The score cannot establish the probability that a lake or dam will fail.

## Catalogue and separation

Record one row per physical incident, including its date, mechanism, location, source identifier, peak-time evidence, image-time evidence, and any exclusion reason. Keep all reaches, maps and acquisitions of one incident in one split and one event cluster. Group shared storms and cascades across mechanisms for uncertainty. Catalogue pre-2022 incidents for development. Screen incidents from 2022 onward using metadata only. Retain an exclusion ledger, including plausible candidates for which timing cannot be established.

Use event reports, inventory records, activation text, product footprints, acquisition times and published licence terms for selection. Record search coverage and catalogue version or retrieval date. Cross-check identities, aliases, date and footprint against prior used events and round-3 metadata. Exclude overlapping round-3 test incidents, including compound events. Do not inspect reserve flood pixels, polygons, image quicklooks, thumbnails, feature values or scores during selection.

## Driver evidence and timing

- M6 requires documented release of water from a glacial lake. Track rock/ice avalanches and debris flows separately when lake drainage lacks independent support. Sediment deposits alone cannot label inundation.
- M7 requires a reported breach or failure with downstream flooding. Distinguish embankment, water-storage and tailings failures. Exclude tailings deposits from the water-extent endpoint unless free-water inundation is independently distinguishable.
- M8 requires documented snowmelt, rain on snow or ice jamming with inundation. Record the subtype. Snow or ice in an image does not establish flooding.

Use the downstream crest at the evaluation reach when available. Record the source, time zone and uncertainty interval. A failure timestamp alone does not establish the downstream crest. For the primary endpoint, require acquisition within 24 hours either side of the crest in M6/M7 or an abrupt M8 ice-jam release, reflecting the brief's same-day or next-day requirement. For sustained M8 melt, use the round-3 river window of one day before to three days after the crest. When peak or image timing is an interval, require eligibility for every possible lag. Log out-of-window observations separately. Fix the study footprint from reach or published coverage metadata before inspecting extent.

## Eligibility and freeze

Use all qualifying independent incidents from the declared search, recording gaps by region and subtype. An acquisition must cover the study reach and have an identifiable source and permitted use. Hold unsettled licences or indistinguishable mechanism cases out of scoring. A published product's acquisition date and coverage must be distinguishable from its publication date. A SAR candidate needs a compatible same-track baseline. Check availability using acquisition metadata only.

Push the criteria before selecting. Push the manifest with its SHA256 and record evidence of remote publication before model work. Freeze methods and the one-shot scoring protocol before opening reserve labels. Four states are flooded, independently observed dry, ambiguous and unobserved. Follow the round-3 cell and spatial-block eligibility rules at scoring time and document every dropout. Never replace a dropout based on scores. Report achieved power and independent event counts. Fewer than five usable independent events cannot validate a type.

## Addendum, 2026-11-27, before any reserve selection

This addendum supersedes the timing sentence above where they differ. DECISIONS_M678.md has the reasons.

- **Window, for every possible crest time:**
  - M6, M7 and abrupt M8 ice-jam releases: [crest − 24 h, crest + 48 h]. For a crest known to the local day D, this is an image on D or D+1.
  - Sustained M8 melt: [crest − 24 h, crest + 72 h].
- **M7 levee and embankment breaches:** the crest is the river crest at the breached reach, and the image must also be later than the reported breach time.
- **Crest source:** record the source kind per incident, in this order of preference:
  1. an approved gauge bracket;
  2. an agency crest record;
  3. a published reading with its clock time;
  4. a published local day;
  5. a GEOGloWS v2 daily peak, only where none of the above exists and never for a dam or lake failure.
- **Clusters:** one per river reach, lake or storm, whichever is coarser. Leave-cluster-out CV. The reserve and the five-event floor count clusters, not incidents. An incident from a storm used for one type is not used for another type.
- **Box:** the 8 km box is placed by round 4's `place()` on the flood centre inside a 20 km search square around the reach point, as round 3's Sentinel-1 route does. The search square, not the box, must be covered by the label image. Placement runs mechanically at build time, identically for DEV and reserve.
- **Maximum lag per label:** recorded per label as image minus crest, in hours, with both bounds.
