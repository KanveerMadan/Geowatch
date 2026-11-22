# Flash floods from NOAA Storm Events on the Sentinel-1 route (round 3, DRAFT)

**Status: DRAFT.** This becomes part of the round-3 reserve criteria when RESERVE_CRITERIA_R3 is sealed. No label of any candidate has been read.

## Why
- Flash had no fresh peak-time source (STATUS, "sources searched").
- Our v3 Sentinel-1 label is as sound for flash as for river, judged against independent analysts working from radar (DIAGNOSIS §e):

  | type | κ (median) | "AUC" |
  |---|---|---|
  | flash | 0.56 | 0.88 |
  | river | 0.58 | 0.83 |

- Against optical-made maps it is weak for both: flash 0.05, river 0.20. The draft §8 rule 2 took river on this route and refused flash on the optical numbers. That treated two types with the same evidence differently.
- This design applies the river rule to flash, with flash's own 2-day image window (R19).
- **What was missing for flash** was a metadata event list with dates and places. NOAA NCEI Storm Events supplies it. It is public domain (US federal data).

## Events (metadata only, `stormevents.py episodes`)
- **Source:** Storm Events details files, 2015 onwards, event type "Flash Flood" with a begin point.
- **Unit of selection:** one NWS episode.
  - It is kept if its Flash Flood events' summed direct property damage is ≥ $1 M. This is the analogue of EMS's reported affected area: a size signal written before any image is looked at.
  - Its point and date are those of its highest-damage Flash Flood event (ties go to the earliest).
- **Split:**
  - before 2022-01-01: DEV (free for development);
  - from 2022-01-01: round-3 reserve.
  - The same split as 311.
- **Counts:** 542 episodes, 360 DEV and 182 reserve.

## Screen (`stormevents.py screen`), in order
1. **Never used:** more than 20 km from every burned unit, on any date.
2. **Not inside a 311 city (± about 20 km).** The rain source must not share places with flash.
3. **One per place and month:** a later episode within 20 km and 30 days of a taken candidate is refused.
4. **Driver check:** IMERG 3-day peak ≥ 20 mm over the 20 km search square plus 25 km (§2, rain and flash). The peak is in [date − 2 d, date + 1 d].
5. **Timing (R19):**
   - the first Sentinel-1 IW VV pass over the point is in [peak − 1 d, peak + 2 d];
   - ≥ 2 same-orbit baseline passes in [t0 − 60 d, t0 − 6 d], or the same window a year earlier.
6. **Order:** ascending date, then episode id. No other ordering.

## DEV yield (2015–2021; reserve not screened)
- **Screen:** 360 DEV episodes give 106 candidates. Refused:
  - 195: no Sentinel-1 pass inside 2 days;
  - 45: IMERG below 20 mm;
  - 9: too few baseline passes;
  - 3: same place and month;
  - 2: inside a 311 city.
- **Labels** (`build_r3 s1route`):
  - 77 of 106 have ≥ 50 flooded and ≥ 50 dry cells.
  - 10 dropped because round 4's `place()` found no January–March baseline image on the search square.
  - The rest have too few flooded cells.
- **By damage:**

  | damage | candidates | qualifying |
  |---|---|---|
  | ≥ $1 M | 106 | 77 |
  | ≥ $3 M | 58 | 43 |
  | ≥ $10 M | 34 | 27 |

- **The $1 M threshold stays.** Raising it does not improve the qualifying rate.
- **Reserve projection:** 182 episodes × ~0.25 passing the screen × ~0.7 qualifying ≈ 30 units. That is above the 5-event floor even at lower post-2021 revisit.

## Unit and label (at build time, after the freeze)
- **Unit:** the 8 km box (R25), placed by round 4's `place()` inside the 20 km Sentinel-1 search square centred on the point.
- **Label:** v3 Sentinel-1 (labels_r3), the same code as the river route.
- **Dropouts:** units with fewer than 50 flooded or 50 dry cells drop out under the bar's rule, and each is reported.
- **Clusters:** one cluster per episode.

## Known limits (to be stated in the pre-registration)
- US only.
- Sentinel-1 sees open water left 0–2 days after the peak. Water that has already drained is missed, so flash labels are conservative.
- Since Sentinel-1B was lost (Dec 2021) until Sentinel-1C (2025), US revisit is about 12 days. The reserve years therefore yield fewer passes inside 2 days.
