# Annotation expansion — 12 recommended cities

Measurement only. Nothing annotated, no training, no build-manual change.

All 39 sites (28 candidates + the existing 11 as baseline) measured over an
identical **5 × 5 km, 25 km² box**. The existing AOIs range from 6.8 km²
(Kigali) to 123.2 km² (HCMC), so using them as-is would have made the distance
matrix partly a measure of AOI size; each existing city's box is centred on the
centroid of its real AOI instead.

Candidate centres target dense/informal fabric, not the CBD — Cité Soleil not
downtown Port-au-Prince, Orangi not central Karachi. **This choice materially
affects the terrain result and is called out where it does.**

---

## Hard gates

**Cloud — every candidate passes.** None dropped.

All four flagged risks clear the bar comfortably: Monrovia 65 clear dates,
Freetown 69, Kinshasa 44, Lima 75 (dates with <10% AOI cloud over three years).

This depends on measuring the AOI rather than the granule. `CLOUDY_PIXEL_PERCENTAGE`
describes a ~110 × 110 km tile; a 25 km² box is 0.2% of one. Measured directly
from SCL over the box, Monrovia has **65** usable dates where the granule
metadata reports **11**. Had the literal metadata test been used, Manila (5),
Caracas (5) and Bogotá (5) would all have looked marginal. Both numbers are in
the table.

**Open Buildings — two candidates fail and are dropped:**

| dropped | reason |
|---|---|
| **Amman** | **0 polygons** in the AOI. Open Buildings v3 does not cover Jordan. |
| **Casablanca** | **0 polygons**. Not covered for Morocco. |

Footprints are the vector half of the merged `impervious` class, so zero
coverage breaks it. Both were otherwise attractive — Amman is the only
non-American candidate above the existing slope maximum (9.29°), and both have
very high dry-season bare fractions.

### The MENA gap is fillable, but by exactly one city

Three MENA candidates were tested. Two fail the footprint gate. **Cairo passes
with 73,858 polygons and 30.0% built fraction** — Open Buildings does cover
Egypt, contrary to the assumption that MENA as a whole is outside its extent.

So MENA can be filled, by Cairo alone, and Cairo has **no OAM validation
imagery**. That is the honest position: the region is representable but with a
single city and no free ground truth. If Cairo is rejected for any reason, MENA
cannot be filled from this candidate list.

---

## Two premises in the brief that the measurement corrects

**1. "NONE of the current 11 are hillside settlements" — not quite.**
Measured mean slope over the AOI: **Kigali 8.61°** (sd 4.99) and **Guatemala
City 6.49°** (sd 8.10). Both are genuinely hilly; Kigali is a thousand-hills
city. The gap is real but narrower than stated — it is the *steep* end
(>10°) that is missing, not hillside terrain altogether. Five candidates clear
the existing maximum: Medellín 14.26, Bogotá 12.24, Lima 10.98, Niterói 10.88,
Caracas 10.49.

**2. OSM building completeness does not predict road completeness.** The
published figures (~9% South Asia, ~12% MENA) describe buildings. Measured on
roads, **South Asian cities are among the best-mapped in the whole set**:
Karachi 38.5 km/km² — the highest of all 39 sites — Delhi 28.9, Kolkata 25.7,
against an existing-11 median of 23.1. Candidate median (23.8) is
indistinguishable from the existing median. **OSM road coverage is not a
discriminator here**, and inferring it from building completeness would have
wrongly demoted South Asia.

The one real OSM risk is the opposite case: **Monrovia at 5.1 km/km² is below
the existing minimum** (Nusantara 5.8), with only 29.6 intersections/km².

---

## Morphological distance

Nine descriptors, z-scored across all 39 sites, two log1p-transformed
(population density, median footprint area) because both are strongly
right-skewed: built fraction, median footprint, footprint IQR, road density,
intersection density, slope mean, slope sd, GHSL built, GHSL population.

Reported two ways, because they answer different questions:

- **d_centroid** — distance from the average of the existing 11. *How unlike
  our training set in general?*
- **d_nearest** — distance to the single closest existing city. *Do we already
  have one of these?*

**The recommendation ranks on `d_nearest`.** The centroid of eleven quite
different cities is not itself a real place, so a candidate can be far from it
while being a near-twin of one city we already have. Only `d_nearest` catches
redundancy. Maputo (d_nearest 0.76, nearest Accra), Mexico City (0.78, nearest
HCMC) and Addis Ababa (0.87, nearest HCMC) are the clearest examples of
candidates that would add little.

---

## The recommended 12

| # | city | tier | region | d_near | why it earns a slot |
|---|---|---|---|---|---|
| 1 | **Lima** | A | LatAm | **3.28** | Highest distance of any gate-passing candidate. Hillside (10.98°, slope sd 11.49 — the most broken terrain measured). Bare 30.2%, seven times the existing maximum. Coastal desert, a climate absent from the set. |
| 2 | **Kinshasa** | A | Africa-C | 2.95 | New subregion. 42.8% built fraction, near the top of the set. Equatorial cloud regime, and it clears the gate (44 dates). |
| 3 | **Karachi** | none | S-Asia | 2.73 | Fills the S-Asia gap. Densest road network measured (38.5 km/km²), 49.2% built, bare 15.7%. No OAM — accepted deliberately. |
| 4 | **Medellín** | A | LatAm | 2.64 | Steepest site measured (14.26°). The canonical hillside informal settlement. |
| 5 | **Bogotá** | B | LatAm | 2.63 | High-altitude Andean, 12.24°. **Tier B licence caveat below.** |
| 6 | **Port-au-Prince** | A | Caribbean | 2.48 | Entirely new region. 696 waterway features — by far the most of any site, directly relevant to the flood model. |
| 7 | **Monrovia** | A | Africa-W | 2.45 | The OSM-sparsity stress case (5.1 km/km², below the existing floor) and the wettest site (~4600 mm/yr), which it survives at 65 clear dates. |
| 8 | **Harare** | none | Africa-S | 2.38 | Only second Africa-S site. Median footprint 64.8 m², much larger than the informal-fabric norm — distinct morphology. |
| 9 | **Freetown** | A | Africa-W | 2.11 | Slope sd 6.26 on a 4.51° mean — steep-but-patchy, a different terrain signature from the Andean cities. |
| 10 | **Kathmandu** | A | S-Asia | 2.07 | Second S-Asia slot. Valley basin, 274.7 intersections/km², 37.2% built. |
| 11 | **Cairo** | none | MENA | 1.95 | **The only viable MENA city.** Bare 24.1%. Taken for the regional gap, with the no-OAM cost accepted. |
| 12 | **Niterói** | A | LatAm | 1.90 | Median footprint 91.2 m² — the largest of all 39 sites. Formal/favela juxtaposition on a 10.88° hillside. |

**Balance achieved:** 8 Tier A + 1 Tier B + 3 no-OAM (9 of 12 with validation
imagery); regions LatAm 4, S-Asia 2, Africa-W 2, Africa-C 1, Africa-S 1,
Caribbean 1, MENA 1; four sites above the existing slope maximum; three sites
with bare fractions above anything in the existing set. Mean d_nearest 2.46
against a candidate-pool mean of 2.08.

### The Americas weighting is forced, not a preference

Five of the twelve are in the Americas. That follows from the terrain
requirement rather than from taste: **every candidate above the existing slope
maximum is American except Amman, which fails the footprint gate.** There is no
way to add steep terrain from this list without weighting the Americas. If that
concentration is unacceptable, the trade is to drop Niterói (lowest d_nearest
of the four) for **Luanda** (d 2.19, Africa-C) or **Antananarivo** (d 1.83,
Tier B, Africa-E, 5.60°) — both cost hillside coverage or validation imagery.

### Caveats I would not want buried

- **Port-au-Prince is not a hillside site as specified here.** Its AOI targets
  Cité Soleil, which is coastal and flat (1.52°). PAP's hillside fabric
  (Jalousie, Pétionville) is a different AOI. It earns its slot on region and
  hydrology, not terrain — and if hillside PAP is wanted, the centre must move.
- **Bogotá is Tier B**, so its imagery is likely CC BY-NC under an OSM-scoped
  waiver. That is probably fine for *validation* but is unverified, and it is
  restricted for *training* until checked per scene. It is the only Tier B pick
  and the first to swap out if the licence does not clear.
- **Manila was dropped on distance, not cloud** (d_nearest 1.66, nearest
  Dharavi) — but it is also the weakest cloud candidate at 22 clear dates and a
  best window of 10. Both reasons point the same way.
- **`bare` remains the thinnest class even after this.** Only Lima, Cairo and
  Karachi exceed the existing maximum WorldCover bare fraction (Cape Town
  4.37%). The dry-season BSI/NDVI screen reads much higher everywhere
  (candidate median 62%) because it counts dry non-vegetated ground that
  WorldCover labels grassland — Ouagadougou is 1.2% by WorldCover and 65% by
  screen. The two disagree by an order of magnitude, and which one matches
  annotator judgement is untested. **Do not treat the bare class as solved by
  this selection.**

---

## Reproduction

| script | test |
|---|---|
| `aois.py` | the 39 AOIs, one 25 km² box each |
| `test1_cloud.py` | S2 availability, granule- and AOI-level |
| `test2_osm.py` | Overpass roads and waterways (see C44) |
| `test345_descriptors.py` | Open Buildings, terrain, GHSL, WorldCover, BSI |
| `analyse.py` | join, z-score, distance matrix, table |

Raw per-site results in `cache/`; `joined.json` carries every field used above.
