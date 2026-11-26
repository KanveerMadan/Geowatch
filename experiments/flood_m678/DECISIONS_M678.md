# M6–M8 decisions

2026-11-25. Started from master in an isolated worktree. Use round-3 commit 5287883 as the reference for its evaluator and conventions. Its final DEV run completed independently.

2026-11-25. Separate historical inundation from the probability of failure. Classify events by documented cause, since debris deposits and tailings footprints can otherwise become false water labels. Screen acquisition timing at the downstream reach and preserve uncertainty about peak time.

2026-11-26. Use the two pinned discovery catalogues as leads. Their source coordinates and reported dates do not locate downstream peak inundation. Keep a separate incident catalogue and exclusion ledger. A recurring flood at one gauge supplies multiple temporal observations from one geographic setting.

2026-11-26. Use recorded stage and a crest bracket wherever the approved gauge record supports it. The bracket includes the observations before and after all tied maxima. Use full local civil days for published dates and the intersection of permissible image windows. Leave a documented timing conflict unresolved. Count a scene only when its footprint covers the complete prelocated 8 km box. These are pre-pixel checks.

2026-11-26. Withhold the reserve seal. The public round-3 metadata include candidate pools and historical records, but its official criteria are still marked draft at commit 5287883. Also exclude Derna from eligibility because it was previously evaluated. Keep candidates with rain or compound drivers closed while checking incident identity. No model training or threshold selection has taken place.

2026-11-26. Trialled the USGS Midland before/after Landsat pair on DEV only. The first pass checked vegetation on the event date and yielded 926 candidate wet cells. Because a green pre-event canopy also obscures the ground, the final diagnostic requires visibility on both dates. It yields 133 wet proxy cells. Both choices were made on a seen development event and neither is pre-registered or validated for another region.

2026-11-26. The user does not have a separate round-3 manifest location. Continue with the known metadata union, keep multi-driver incidents quarantined wherever overlap is unresolved, and revisit public metadata at freeze time. A missing list does not prevent development-only observation work.

2026-11-26. Geolocated the Skaftá V299 gauge from the published station table and the projection in the same archive. Screened the 2015 and 2023 measured peaks. The two-pulse 2021 event remains unresolved. The Kherson waterfront box uses the ministry's port position and the local crest day reported by UNEP. The Hassanabad reach is established, but a discharge estimate paired with the event date is insufficient evidence for the clock time or day of the downstream maximum.

2026-11-27 (Claude Code takes over from Codex; same branch, same rules). The working methods are round 3's, imported unchanged from a pinned read-only checkout of `exp/flood-round3` at f28d714 (`git worktree add --detach ~/gw-r3pin f28d714`). Nothing in round 3 is edited. Earth Engine calls from M6–M8 take the exclusive lock on `/private/tmp/geowatch-change-round2-ee.lock`, so they never run alongside round 3's shared-lock calls.

2026-11-27. Image-timing window, restated before any reserve selection and before any label pixel of a new incident. The brief asks for a same-day or next-day image for the fast types. The pushed criteria encoded this as 24 hours either side of the crest, and the screen intersects that window over every possible crest time. With a crest known only to the local day, that leaves the crest day itself, which is narrower than "same day or next day". The rule is now:
- M6, M7 and abrupt M8 ice-jam releases: image minus crest in [−24 h, +48 h] for every possible crest time. With a day-resolution crest D this is exactly an image on day D or D+1. A precisely timed crest gets the same window around its bracket.
- Sustained M8 melt: [−24 h, +72 h], unchanged (round 3's river window).
- M7 levee and embankment breaches: the crest is the river crest at the breached reach (approved gauge bracket, NWS crest day, or published reading). The image must also be later than the reported breach time, because before the breach the protected land is dry by construction. Dam failures keep the downstream crest at the evaluation reach.
- Crest sources, in order of preference: an approved continuous gauge bracket; an agency crest record (NWS NWPS historic crests, national hydrological services); a published measured reading with its clock time; a published local day; GEOGloWS v2 retrospective daily peak (UTC day), only where no gauge or published crest exists, and never for dam or lake failures, which GEOGloWS does not simulate. The source kind is recorded per incident.
The window applies identically to DEV and reserve. Out-of-window scenes stay logged and are never scored. The change is metadata-level. No label, feature or score of any incident has been read under it.

2026-11-27. Clusters. Every incident gets a cluster id: one per river reach, lake or storm, whichever is coarser. The 2019 Missouri levee breaches at Hamburg and in Holt County share the March 2019 cyclone, so they form one cluster. Incidents of that storm are not used for M8, so one storm never counts for two types. Repeated floods from one lake or at one gauge form one cluster (Mendenhall, Skaftá, Red River at Fargo). CV folds are leave-cluster-out, and the reserve count is in clusters.
