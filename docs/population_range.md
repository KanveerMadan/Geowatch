# Population as a range: WorldPop and GHS-POP (item 67)

**Rule.** Report population as the range spanned by two independent
gridded models, never as a point estimate from either one.

## 1. The two sources

| | WorldPop | GHS-POP |
|---|---|---|
| GEE asset | `WorldPop/GP/100m/pop` (`configs/exposure_constants.py:46`) | `JRC/GHSL/P2023A/GHS_POP/2020` |
| band | `population` | `population_count` |
| native grid | EPSG:4326, ~92.77 m (`exposure_constants.py:49`) | World Mollweide, 100 m (read from `.projection()` 2026-10-28) |
| newest observation epoch | 2020 | 2020 (2025, 2030 are projections; `03_EVIDENCE.md` §C.4) |

**Method.** A zonal **sum** over the AOI rectangle, in each image's **own**
`crs`/`crsTransform` and with no `scale=`. This is the method
`exposure/compute.py:182-189` uses. `scale=` silently resamples and
mis-sums (`exposure_constants.py:26-37`). GHS-POP's projection carries a WKT
instead of an EPSG code, so the WKT is passed as `crs`. WorldPop is filtered
to the AOI's country and to `year == 2020`, which returns exactly one image
per AOI.

## 2. Measured, 2026-10-28

| AOI (run it came from) | WorldPop 2020 | GHS-POP 2020 | **range** | spread, max/min − 1 |
|---|---:|---:|---|---:|
| Dharavi canonical, 72.836, 19.037, 72.862, 19.060 (`verify_worldpop_scale.py:4`) | 282,983 | 261,569 | **261,569 – 282,983** | 8.2 % |
| Mumbai multitile, 72.80, 19.00, 72.88, 19.08 (`phase1_multitile_20260820_130117`) | 2,133,519 | 2,336,858 | **2.13 M – 2.34 M** | 9.5 % |
| Mumbai 3-ward, 72.804, 18.894, 72.851, 18.965 (`pilot_3ward_20260807_162911`) | 766,366 | 845,387 | **766 k – 845 k** | 10.3 % |
| Delhi, 77.20, 28.60, 77.24, 28.64 (`phase6_delhi_recheck_20260730_161429`) | 70,357 | 138,555 | **70 k – 139 k** | 96.9 % |
| Accra, −0.21, 5.53, −0.17, 5.57 (`phase6_accra_coastal_check_20260728_154557`) | 231,082 | 256,773 | **231 k – 257 k** | 11.1 % |

The Dharavi WorldPop sum reproduces `exposure_constants.py:35`'s recorded
282,983.025. The query therefore follows the code's path.

**What this changes in the existing record.** `03_EVIDENCE.md` §C.4 and
item 67's text say the sources "disagree by ~7.6% at 2020". Re-derived:

- **7.6 % is (WP − GHS) / WP** = 21,414 / 282,983 = 7.57 %. Divided by GHS
  instead, the same gap is 8.19 %. The figure never named its denominator.
  The range above sidesteps the choice.
- **It is one AOI.** On the four other AOIs, **the sign flips**: GHS-POP is
  higher by 9.5–11.1 %. On the Delhi AOI, GHS-POP is nearly **double**
  WorldPop. "The sources differ by ~8%" is not a property of the two models.
  The disagreement is AOI-dependent in both size and direction.

So the range must be computed **per AOI, every time**. A fixed ± band derived
from Dharavi would be wrong elsewhere.

## 3. A third model is now in GEE, and is not in the range

Running the WorldPop query now prints a deprecation warning: *"This dataset
has been superseded by `WorldPop/GP/100m/R2025A/v1/pop`."* That asset exists,
covering 2015–2030 (16 yearly images per country, EPSG:4326 at 1/1200°).
**This contradicts `03_EVIDENCE.md` §C.4**, which records R2025A as absent
from GEE. That was true when probed and is stale now.

Its 2020 sums, by the same method (country-filtered, own projection), differ
from both models above by a large factor:

| AOI | R2025A 2020 | R2025A 2025 |
|---|---:|---:|
| Dharavi canonical | 78,964 | 81,342 |
| Mumbai multitile | 661,187 | 680,932 |
| Mumbai 3-ward | 208,723 | 215,626 |
| Delhi | 442,110 | 468,454 |
| Accra | 82,816 | 91,041 |

Against the GP/GHS range (range end ÷ R2025A), R2025A is 2.8–4.1× lower on
Dharavi, the two Mumbai AOIs and Accra, and 3.2–6.3× higher on Delhi. **These were not
investigated** (methodology, constrained vs unconstrained variant, units).
R2025A is therefore **not** folded into the range, and adopting it is a
source decision, not a constant edit. The numbers are recorded so the gap is
not rediscovered from scratch.

## 4. Constraint: no enumerated Indian microdata before 2027–28

Every population figure for an Indian AOI is **modelled**: extrapolated from
the 2011 census or produced by a gridded model. None is enumerated.

- Census 2027 Phase I (house-listing) ran April–September 2026, staggered by
  state. Phase II (population enumeration) is scheduled for **February 2027**,
  reference date **1 March 2027**, with earlier enumeration in snow-bound
  areas (reference date 1 October 2026).
- **No official date for results has been announced** (checked 2026-10-28).
  Non-government sources expect late 2027 to 2028 for preliminary data.

Sources: [Census 2027 begins](https://www.newsonair.gov.in/worlds-largest-and-first-digitallly-conducted-indias-census-2027-begins-today),
[first-phase notification](https://www.newsonair.gov.in/centre-issues-notification-for-first-phase-of-census-2027),
[DD News: first fully digital census](https://ddnews.gov.in/en/india-to-conduct-first-fully-digital-census-in-2027-nationwide-exercise-to-begin-april-1/),
[2027 census of India](https://en.wikipedia.org/wiki/2027_census_of_India).

**Consequence.** Until enumerated microdata is released, no Indian
population figure here can be validated against a count, only against
another model. Section 2 is exactly that comparison, and the models disagree
by 8–97 %.

## Reproduce

```python
# run from the repo root with the project env; needs an initialised EE session
import ee
from ingestion.gee_client import initialize_gee
initialize_gee()

def zsum(img, band, g):
    p = img.select(band).projection().getInfo()
    crs = p.get("crs") or img.select(band).projection().wkt().getInfo()  # GHS-POP: WKT only
    return img.select(band).reduceRegion(ee.Reducer.sum(), g, crs=crs, crsTransform=p["transform"],
                                         maxPixels=1e9, bestEffort=False).getInfo()[band]

g = ee.Geometry.Rectangle([72.836, 19.037, 72.862, 19.060])
wp = (ee.ImageCollection("WorldPop/GP/100m/pop").filterBounds(g)
      .filter(ee.Filter.eq("country", "IND")).filter(ee.Filter.eq("year", 2020)).first())
print(zsum(wp, "population", g), zsum(ee.Image("JRC/GHSL/P2023A/GHS_POP/2020"), "population_count", g))
r25 = (ee.ImageCollection("WorldPop/GP/100m/R2025A/v1/pop")
       .filter(ee.Filter.eq("country", "IND")).filter(ee.Filter.eq("year", 2020)).first())
print(zsum(r25, "population", g))
```
