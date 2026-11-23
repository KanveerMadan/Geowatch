# Historical development-site nominations

The 23 new city tiles in `historic_sites.json` cover 17 countries. The earliest incident date is 13 June 2015 and the latest is 18 December 2021. Each row cites a public incident report or primary study, gives the settlement and date, and retains a null peak date. In multi-day incidents the anchor can be a reporting day. The source records the city or wider incident and supplies no pixel-level labels.

We chose roughly 4 km tiles centered on named settlements or neighborhoods before inspecting satellite observations. Longitudes are scaled by the cosine of latitude to keep the physical width approximately constant. Flash, cyclone, surge, river and urban rain cases therefore have different chances of being imaged while wet. Mocoa includes debris-flow impacts and Puri includes wind damage. A documented disaster alone cannot establish standing water in a particular neighborhood on a later acquisition.

Each record includes level 4 and level 6 HYBAS_ID and the level 6 MAIN_BAS returned by the HydroBASINS polygons covering its center. An extra intersection test recorded every level 6 and MAIN_BAS touching the full tile expanded by 0.002° on all four sides. We excluded candidates with shared reserved drainage basins, shared geometry/products/storms or qualifying Round 3 proximity and time. We compared the regional storm chronology with the historical Round 3 event titles, which can identify the same storm across multiple activation codes. Final eligibility is always rechecked by the running registry guard. [HydroBASINS documentation](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_6)

Pemba (Kenneth, April 2019) intersected an excluded basin. Nukuʻalofa (Gita, February 2018) lacked an unambiguous center basin. Both are omitted. The original Bad Neuenahr (July 2021) nomination shares the western-European storm behind Round 3 activations EMSR517, EMSR518 and EMSR520. Its omission from these additions and its discovery-time status were reported separately to the study lead.

## Independent optical imagery prospects

The public current Maxar ARD root returned 55 child links when checked. Screening event years/names in that index yielded no verifiable, eligible historical non-US flood activation. Earlier acquisitions listed under the name of a later disaster could simply be pre-event comparisons for that later activation.

The older public S3 bucket exposes separate disaster collections. The root listing verified the existence of the collection names below. Each requires its own site, timestamp and usable-coverage check before serving as evidence. Source terms distinguish the Open Data Program's CC BY-NC 4.0 materials. Record the terms accompanying the specific asset. [Provider listing on AWS](https://registry.opendata.aws/digital-globe-open-data/) · [Current catalog](https://maxar-opendata.s3.us-west-2.amazonaws.com/events/catalog.json)

| Shortlist | Legacy metadata directory |
|---|---|
| Beira, Idai, March 2019 | [cyclone_idai](https://s3.amazonaws.com/dg-opendata/?list-type=2&prefix=cyclone_idai%2F&delimiter=%2F) |
| Sentani, Indonesia, March 2019; geographic and date match requires verification | [papua_indonesia_flooding](https://s3.amazonaws.com/dg-opendata/?list-type=2&prefix=papua_indonesia_flooding%2F&delimiter=%2F) |
| Puri, Fani, May 2019 | [cyclone-fani](https://s3.amazonaws.com/dg-opendata/?list-type=2&prefix=cyclone-fani%2F&delimiter=%2F) |
| Marsh Harbour, Bahamas, Dorian, September 2019 | [hurricane-dorian](https://s3.amazonaws.com/dg-opendata/?list-type=2&prefix=hurricane-dorian%2F&delimiter=%2F) |

The event references and basin lookups are catalogue construction. Accuracy, urban street visibility and the usable coverage of any individual scene require separate measurement.
