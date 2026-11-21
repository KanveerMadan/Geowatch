"""Paired default-source test on the locked INPE notice cells, independent of every input sensor."""
import argparse
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

from pyproj import CRS, Transformer
from shapely.geometry import box
from shapely.ops import transform, unary_union

from .amazon_clearing import HERE, ROOT, LOCK, digest, load_locked
from analysis.change_history import _tile_arrays, _observations
from vector.change_detection import detect_cell
from vector.change_observations import DEFAULT_SOURCES, open_history

SEAL = HERE / "amazon_default_lock.json"
PERIOD = ("2024-06-01", "2024-09-01")


def lock():
    load_locked()
    paths = (LOCK, Path(__file__).resolve(), ROOT / "analysis/change_history.py")
    with SEAL.open("x") as f:
        json.dump({"files": {str(p.relative_to(ROOT)): digest(p) for p in paths},
                   "sources": DEFAULT_SOURCES, "period": PERIOD,
                   "design": "Paired secondary run on all July INPE test notices with identical "
                   "spatial support, target, policy, decision window and history. Compare confirmed "
                   "greenness loss with the S2-only result within notices. Report paired gains and "
                   "losses. No substitutions, score tuning, promotion or pooled global claim."}, f, indent=2)


def registry():
    seal = json.loads(SEAL.read_text())
    if seal["sources"] != list(DEFAULT_SOURCES) or any(
            digest(ROOT / name) != expected for name, expected in seal["files"].items()):
        raise ValueError("paired protocol mismatch")
    return load_locked()


def run(cache, state):
    refs = [r for r in registry() if r["state"] == state]
    crs = CRS.from_epsg(int(refs[0]["epsg"]))
    cells = {}
    for r in refs:
        x, y = int(r["x"]), int(r["y"])
        cells[f"{crs.to_string()}/{x}/{y+100}"] = (box(x, y, x+100, y+100), r)
    area = unary_union([geom for geom, _ in cells.values()])
    inverse = Transformer.from_crs(crs, 4326, always_xy=True).transform
    layer = SimpleNamespace(aoi=area, crs=crs, bbox=transform(inverse, area).bounds)
    results = []
    history = open_history(layer, "2019-06-01", PERIOD[1], cache_dir=cache/"source")
    for tile in history.tiles():
        if any(d["errors"] for d in tile["diagnostics"]):
            raise RuntimeError(str(tile["diagnostics"]))
        obs = tile["observations"]
        meta = [{k:v for k,v in o.items() if k not in ("values","coverage")} for o in obs]
        arrays = _tile_arrays(obs, 0, len(tile["cells"]))
        for i, cell in enumerate(tile["cells"]):
            _, ref = cells[cell["cell_id"]]
            rows = _observations(meta, arrays, i, cell["support_id"])
            result = detect_cell(cell["cell_id"], rows, start=PERIOD[0], end=PERIOD[1])
            hits = [e for e in result["events"] if e["transition"] == "greenness_loss" and e.get("confirmed_on")]
            dates = sorted({r["date"] for r in rows if r["date"] >= ref["date"] and "ndvi" in r["values"]})
            results.append({"notice": ref["notice"], "date": ref["date"], "state": state,
                            "cell_id": cell["cell_id"], "next_usable": dates[0] if dates else None,
                            "confirmed": min((e["confirmed_on"] for e in hits), default=None),
                            "full_ndvi_window": any(s["signal"] == "ndvi" and s["status"] == "observed"
                                                    for s in result["series"])})
    with (cache/f"default-{state}.json").open("x") as f:
        json.dump({"seal":digest(SEAL),"rows":results}, f)


def combine(cache):
    refs = registry()
    primary = json.loads((HERE/"amazon_clearing_result.json").read_text())
    if primary["lock"] != digest(LOCK):
        raise ValueError("primary study mismatch")
    by_id = {r["notice"]:r for r in primary["cells"]}
    rows = []
    for state in sorted({r["state"] for r in refs}):
        part = json.loads((cache/f"default-{state}.json").read_text())
        if part["seal"] != digest(SEAL):
            raise ValueError("secondary study mismatch")
        rows.extend(part["rows"])
    if Counter(r["notice"] for r in rows) != Counter(r["notice"] for r in refs):
        raise ValueError("incomplete or duplicate scores")
    agreement = Counter()
    for row in rows:
        pair = (bool(by_id[row["notice"]]["confirmed"]), bool(row["confirmed"]))
        key = {(True,True):"both", (True,False):"s2_only", (False,True):"default_only",
               (False,False):"neither"}[pair]
        agreement[key] += 1
    res = {"seal":digest(SEAL), "rows":rows, "pair_counts":dict(agreement),
           "full_ndvi_windows":sum(r["full_ndvi_window"] for r in rows)}
    with (HERE/"amazon_default_result.json").open("x") as f:
        json.dump(res, f, indent=1)
    print(agreement)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["lock","run","combine"])
    parser.add_argument("--cache", type=Path, default=Path("/tmp/gwc-deter-run"))
    parser.add_argument("--state")
    args = parser.parse_args()
    if args.command == "lock":
        lock()
    elif args.command == "run":
        run(args.cache, args.state)
    else:
        combine(args.cache)
