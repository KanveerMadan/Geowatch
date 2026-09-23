"""
Parameter sensitivity sweep for Decision 13's `built` endmember extraction.

`diagnose_open_buildings_aoi.py` measures ONE point on the surface: a -2m
inward buffer with a 100 m^2 usable-area bar. That point looked bad on every
AOI tried (Dharavi 8.5%, Khayelitsha 0.5%, formal Cape Town suburbs 18.2%).
This script asks whether that is a structural limit of 10m unmixing against
Open Buildings v3, or an artifact of two thresholds we picked by hand.

Sweep: 3 inward buffers x 3 usable-area bars x 3 AOIs = 27 combinations.

Alongside raw yield, two bias metrics are reported at every combination,
because a setting that raises yield while making the surviving sample LESS
representative of the AOI's actual roofing is not progress:

  bias_shrunk  survivor mean SHRUNK area / confident-set mean PRE-shrink area
               -- the ratio already reported for the -2m/100m^2 point. Note
               it mixes two effects: selection bias, and the shrink itself
               removing area. Kept for continuity with that earlier number.

  bias_select  survivor mean ORIGINAL area / confident-set mean ORIGINAL area
               -- pure selection bias, independent of how much the buffer
               ate. 1.0 would mean survivors are a representative sample of
               the AOI's buildings by size. This is the honest metric.

Reuses AOI resolution and constants from diagnose_open_buildings_aoi.py
(importing it also performs GEE initialization).

Usage:
    python sweep_open_buildings_params.py
"""

import diagnose_open_buildings_aoi as diag
import ee

BUFFERS_M = [-1.0, -1.5, -2.0]
AREA_BARS_M2 = [50, 75, 100]

# The formal-fabric control probed earlier -- an ad-hoc rectangle over
# Rondebosch/Claremont, not a pipeline-run AOI.
FORMAL_CT_BBOX = [18.455, -33.985, 18.495, -33.950]


def build_aois():
    """(label, ee.Geometry) for the three AOIs measured so far."""
    aois = []

    aois.append((
        "Dharavi",
        ee.Geometry.Rectangle(diag.DHARAVI_BOUNDS),
    ))

    ct_bounds, ct_run_dir = diag.aoi_bounds_from_run("capetown")
    print(f"  capetown AOI from {ct_run_dir}")
    aois.append((
        "Khayelitsha (capetown run)",
        ee.Geometry.Rectangle(list(ct_bounds)),
    ))

    aois.append((
        "Cape Town formal suburbs",
        ee.Geometry.Rectangle(FORMAL_CT_BBOX),
    ))

    return aois


def sweep_aoi(label, aoi):
    """Run every (buffer, area_bar) combination for one AOI.

    Requests are batched one-per-buffer rather than one-per-combination:
    Khayelitsha carries ~93k confident footprints, and mapping the buffer is
    the expensive part, so the three area bars share a single mapped
    collection and a single round trip.
    """
    print(f"\n[{label}] querying...")

    area_km2 = aoi.area(1).getInfo() / 1e6
    buildings = ee.FeatureCollection(diag.BUILDINGS_ASSET).filterBounds(aoi)
    confident = buildings.filter(
        ee.Filter.gte("confidence", diag.CONFIDENCE_THRESHOLD)
    )

    # Baselines fetched in one call
    baseline = ee.Dictionary({
        "raw": buildings.size(),
        "confident": confident.size(),
        "pop_mean_area": confident.aggregate_mean("area_in_meters"),
    }).getInfo()

    raw_count = baseline["raw"]
    confident_count = baseline["confident"]
    pop_mean_area = baseline["pop_mean_area"]
    print(f"  area {area_km2:.2f} km^2 | raw {raw_count} | "
          f"confident {confident_count} | pop mean area {pop_mean_area:.1f} m^2")

    rows = []
    for buf in BUFFERS_M:
        def shrink_and_flag(feature, _buf=buf):
            shrunk = feature.geometry().buffer(_buf)
            return feature.set({"shrunk_area_m2": shrunk.area(1)})

        shrunk_fc = confident.map(shrink_and_flag)

        # All three area bars for this buffer in a single round trip
        per_bar = {}
        for bar in AREA_BARS_M2:
            survivors = shrunk_fc.filter(
                ee.Filter.gte("shrunk_area_m2", bar)
            )
            per_bar[str(bar)] = ee.Dictionary({
                "count": survivors.size(),
                # null when the survivor set is empty -- handled below
                "mean_shrunk": survivors.aggregate_mean("shrunk_area_m2"),
                "mean_original": survivors.aggregate_mean("area_in_meters"),
            })

        print(f"  buffer {buf}m ...", flush=True)
        result = ee.Dictionary(per_bar).getInfo()

        for bar in AREA_BARS_M2:
            r = result[str(bar)]
            count = r["count"]
            mean_shrunk = r["mean_shrunk"]
            mean_original = r["mean_original"]

            rows.append({
                "aoi": label,
                "area_km2": area_km2,
                "buffer_m": buf,
                "area_bar_m2": bar,
                "raw": raw_count,
                "confident": confident_count,
                "pop_mean_area": pop_mean_area,
                "count": count,
                "pct_of_raw": 100.0 * count / raw_count if raw_count else 0.0,
                "per_km2": count / area_km2 if area_km2 else 0.0,
                "bias_shrunk": (mean_shrunk / pop_mean_area) if count else None,
                "bias_select": (mean_original / pop_mean_area) if count else None,
            })

    return rows


def print_sweep_table(rows):
    print("\n" + "=" * 94)
    print("PARAMETER SENSITIVITY SWEEP -- Open Buildings v3 `built` endmember yield")
    print("(confidence >= 0.7 applied in all cases)")
    print("=" * 94)
    header = (f"{'AOI':<28} {'buffer':>7} {'bar':>6} {'usable':>8} "
              f"{'% raw':>7} {'per km2':>9} {'bias_sel':>9} {'bias_shr':>9}")
    print(header)
    print("-" * 94)

    last_aoi = None
    for r in rows:
        if last_aoi is not None and r["aoi"] != last_aoi:
            print("-" * 94)
        last_aoi = r["aoi"]
        bias_sel = f"{r['bias_select']:.2f}x" if r["bias_select"] else "n/a"
        bias_shr = f"{r['bias_shrunk']:.2f}x" if r["bias_shrunk"] else "n/a"
        print(f"{r['aoi']:<28} {r['buffer_m']:>6}m {r['area_bar_m2']:>5} "
              f"{r['count']:>8} {r['pct_of_raw']:>6.1f}% {r['per_km2']:>9.1f} "
              f"{bias_sel:>9} {bias_shr:>9}")
    print("=" * 94)


def print_bias_check(rows):
    """The explicit yield-vs-bias trade-off at the loosest (highest-yield)
    setting versus the current one."""
    loosest = (min(BUFFERS_M, key=abs), min(AREA_BARS_M2))
    current = (-2.0, 100)

    print(f"\nBIAS CHECK -- does the highest-yield setting buy yield with "
          f"representativeness?")
    print(f"  current setting : buffer {current[0]}m, bar {current[1]} m^2")
    print(f"  loosest setting : buffer {loosest[0]}m, bar {loosest[1]} m^2")
    print(f"  bias_select = survivor mean original area / all-confident mean "
          f"original area (1.00x = representative)")
    print()
    print(f"{'AOI':<28} {'yield now':>10} {'yield loose':>12} "
          f"{'bias now':>9} {'bias loose':>11} {'bias delta':>11}")
    print("-" * 86)

    for aoi in dict.fromkeys(r["aoi"] for r in rows):
        cur = next(r for r in rows if r["aoi"] == aoi
                   and r["buffer_m"] == current[0] and r["area_bar_m2"] == current[1])
        loo = next(r for r in rows if r["aoi"] == aoi
                   and r["buffer_m"] == loosest[0] and r["area_bar_m2"] == loosest[1])
        delta = loo["bias_select"] - cur["bias_select"]
        arrow = "worse" if delta > 0 else "better"
        print(f"{aoi:<28} {cur['pct_of_raw']:>9.1f}% {loo['pct_of_raw']:>11.1f}% "
              f"{cur['bias_select']:>8.2f}x {loo['bias_select']:>10.2f}x "
              f"{delta:>+9.2f}x {arrow}")


def main():
    aois = build_aois()

    all_rows = []
    for label, aoi in aois:
        all_rows.extend(sweep_aoi(label, aoi))

    print_sweep_table(all_rows)
    print_bias_check(all_rows)


if __name__ == "__main__":
    main()
