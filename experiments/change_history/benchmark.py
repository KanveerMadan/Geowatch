"""Lightweight, deterministic engineering benchmark. Run with python -m experiments.change_history.benchmark.

Times the detector with correlated seasonal signals, independent measurement
noise and missing cloudy dates. Generates one cell at a time. The injected
changes are easy, known index shifts. These counts do not validate real maps.
"""
from collections import Counter
from datetime import date, timedelta
import argparse
import json
import math
import random
import time

from vector.change_detection import detect_cell


def acquisitions(start, end):
    optical = ("ndvi", "mndwi", "ndbi")
    sar = ("vv_db", "vh_db")
    tracks = (
        ("sentinel2", "MSI:10", 5, 0, optical),
        ("sentinel2", "MSI:12", 5, 2, optical),
        ("sentinel1", "IW:A:A:10", 12, 0, sar),
        ("sentinel1", "IW:A:D:12", 12, 3, sar),
        ("landsat8", "OLI:34", 16, 7, optical),
        ("landsat9", "OLI:34", 16, 7 + 3 * 365, optical),
    )
    first = start.replace(year=start.year - 5)
    dates = []
    for source, track, cadence, offset, signals in tracks:
        for day_idx in range(offset, (end - first).days, cadence):
            day = first + timedelta(days=day_idx)
            phase = 2 * math.pi * day_idx / 365.2425
            dates.append((source, track, day.isoformat(), signals, phase, (day - start).days))
    return dates


def benchmark(cells=100):
    if cells < 1:
        raise ValueError("at least one cell required")
    start, end = date(2024, 1, 1), date(2024, 4, 1)
    catalogue = acquisitions(start, end)
    counts = {"shift_injected": Counter(), "stable": Counter()}
    elapsed = 0
    for i in range(cells):
        rng = random.Random(i)
        rows = []
        local_phase = 2 * math.pi * i / cells
        for source, track, day, signals, phase, monitored_day in catalogue:
            optical = source != "sentinel1"
            missingness = 0.45 + 0.35 * math.sin(phase + local_phase) if optical else 0.05
            seen = rng.random() > missingness
            shifted = (i % 3 == 0 and 11 < monitored_day < 65) or (i % 6 == 1 and monitored_day > 0)
            level = 0.5 + 0.15 * math.sin(phase + local_phase) - 0.25 * shifted
            values = {}
            if seen:
                for signal in signals:
                    values[signal] = level + rng.gauss(0, 0.04) if optical else level - 14 + rng.gauss(0, 0.8)
            rows.append({"source": source, "track": track, "date": day, "lineage": source,
                         "values": values, "coverage": int(seen)})
        begin = time.monotonic()
        result = detect_cell(f"cell{i}", rows, start=start, end=end)
        elapsed += time.monotonic() - begin
        group = "shift_injected" if i % 3 == 0 or i % 6 == 1 else "stable"
        counts[group][result["state"]] += 1
    return {"cells": cells, "acquisitions_per_cell": len(catalogue), "detector_seconds": elapsed,
            "result_counts": counts, "scope": "synthetic, per-cell detector only"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=int, default=100)
    print(json.dumps(benchmark(parser.parse_args().cells), indent=2))
