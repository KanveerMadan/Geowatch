from collections import Counter
import csv
import json
from datetime import date

from experiments.change_history import amazon_clearing as clearing
from experiments.change_history import amazon_default as default


def test_paired_default_and_optical_receipts_match_sealed_grid_and_dates():
    refs = {r["notice"]: r for r in default.registry()}
    primary = json.loads(clearing.RESULT.read_text())
    secondary = json.loads((clearing.HERE / "amazon_default_result.json").read_text())
    assert primary["lock"] == clearing.digest(clearing.LOCK)
    assert secondary["seal"] == clearing.digest(default.SEAL)
    hits = []
    for rows in (primary["cells"], secondary["rows"]):
        assert Counter(r["notice"] for r in rows) == Counter(refs.keys())
        for row in rows:
            ref = refs[row["notice"]]
            x, y = int(ref["x"]), int(ref["y"])
            assert row["cell_id"] == f"EPSG:{ref['epsg']}/{x}/{y + 100}"
            assert row["date"] == ref["date"]
            for field in ("confirmed","next_usable"):
                if row[field] is not None:
                    assert default.PERIOD[0] <= row[field] < default.PERIOD[1]
            assert row["next_usable"] is None or row["next_usable"] >= row["date"]
        hits.append({r["notice"] for r in rows if r["confirmed"]})
    first, second = hits
    counts = {"both":len(first & second),"neither":len(refs.keys() - (first|second)),
              "s2_only":len(first-second),"default_only":len(second-first)}
    assert +Counter(counts) == Counter(secondary["pair_counts"])
    assert primary["summary"]["positive"] == len(first)
    assert secondary["full_ndvi_windows"] == sum(r["full_ndvi_window"] for r in secondary["rows"])


def test_registration_does_not_count_reserved_reference_rows_as_test():
    with clearing.REGISTRY.open() as f:
        rows = list(csv.DictReader(f))
    lock = json.loads(clearing.LOCK.read_text())
    assert len(rows) == len({r["notice"] for r in rows}) == lock["eligible"]
    assert {r["split"] for r in rows} == {"test","reference_only"}
    assert all(date.fromisoformat(r["date"]).strftime("%Y-%m") == "2024-07" for r in rows)
    assert len(clearing.load_locked()) == sum(s[2] for s in lock["selected"])
