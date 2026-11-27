"""
M6–M8 v2, step 0: pinned sources, the v1 quarantine, round 3's DEV whitelist and the metadata
exclusions. Everything is read from git objects at the pinned SHAs, never from a working tree, so
later edits on other branches cannot change what v2 excludes.

    python -m experiments.flood_m678.v2.registry      # writes v2/registry.json (+ sha256 in stdout)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(HERE, "registry.json")

PINS = {
    "v2_parent_design": "bfa85d0d207ee6d19619085e21a280b2a52abce7",      # origin/design/m678-v2
    "v1_branch_head": "a0bfe89",                                           # feat/flood-m6-m8 (labeller-defect note)
    "v1_reserve_seal": "fb73a2ead6be1f1c4d9ea837d944ca79d1d46424",        # tag m678-reserve-seal
    "v1_freeze": "222c9045577a07f060e052fc59f7fdb6139e36a5",              # tag m678-freeze
    "round3": "5ca318f26c16272ce20d28bcd72c9db18dea2452",                  # exp/flood-round3 with R35
}
ROUND3_CODE_WORKTREE = "~/gw-r3pin-r35"   # git worktree add --detach ~/gw-r3pin-r35 <PINS['round3']>
R3_REGISTRIES = ("flood_core/registry/events.json", "flood_final/registry_units.json",
                 "flood_round2/registry_units_round2.json")
R3_CANDIDATES = {"r3_ems_candidates": "bounds", "r3_mmflood_candidates": "bbox_at_search_point",
                 "se_flash_candidates": "bbox_at_search_point", "plains_candidates": "square"}


def show(sha, path):
    out = subprocess.check_output(["git", "-C", REPO, "show", f"{sha}:{path}"])
    return out


def _json(sha, path):
    return json.loads(show(sha, path))


def v1_quarantine():
    """Every v1 reserve cluster (all incidents, including the pre-2022 ones withheld from DEV) is
    excluded from v2 training AND testing forever. v1 DEV incidents were inspected: DEV-only."""
    r = _json(PINS["v1_reserve_seal"], "experiments/flood_m678/reserve_m678.json")
    d = _json(PINS["v1_reserve_seal"], "experiments/flood_m678/dev_m678.json")
    clusters = sorted({f"{t}:{c}" for t in r["reserve"] for c in r["reserve"][t]})
    incidents = sorted({x["incident"] for t in r["reserve"] for c in r["reserve"][t] for x in r["reserve"][t][c]}
                       | set(r.get("withheld_dev_incidents", [])) | set(r.get("refused", {})))
    dev_only = sorted({x["incident"] for t in d["dev"] for c in d["dev"][t] for x in d["dev"][t][c]})
    return {"clusters": clusters, "incidents": incidents, "dev_only_incidents": dev_only,
            "dev_only_clusters": sorted({f"{t}:{c}" for t in d["dev"] for c in d["dev"][t]})}


def round3_dev_whitelist():
    """Round 3's DEV units (burned + Sentinel-1-route DEV catalogues) that v2's transfer step may read."""
    out = {}
    for f in ("burned_catalog.json", "s1route_catalog.json"):
        try:
            cat = _json(PINS["round3"], f"experiments/flood_round3/results/{f}")
        except subprocess.CalledProcessError:
            continue
        for n, row in cat.items():
            out[n] = {"tags": row.get("tags"), "region": row.get("region"), "cluster": row.get("cluster"),
                      "event": row.get("event"), "bbox": row.get("bbox"), "source": f}
    return out


def round3_exclusion_geometry():
    """Footprints v2 reserve candidates must not touch (round 3's registries and candidate pools)."""
    geo = []
    for p in R3_REGISTRIES:
        for row in _json(PINS["round3"], f"experiments/{p}")["units"]:
            g = row["geometry"]
            if g["type"] == "boxes":
                geo += [{"src": p, "id": row["event_id"], "bbox": b["bbox"]} for b in g["boxes"]]
            elif g["type"] == "point_approx":
                x, y = g["point"]
                geo.append({"src": p, "id": row["event_id"], "bbox": [x, y, x, y]})
    for name, key in R3_CANDIDATES.items():
        for row in _json(PINS["round3"], f"experiments/flood_round3/results/{name}.json")["candidates"]:
            geo.append({"src": name, "id": row["unit"], "bbox": row[key]})
    for n, row in round3_dev_whitelist().items():
        if row.get("bbox"):
            geo.append({"src": "round3_dev", "id": n, "bbox": row["bbox"]})
    return geo


def build():
    reg = {"pins": PINS, "round3_code_worktree": ROUND3_CODE_WORKTREE, "v1": v1_quarantine(),
           "round3_dev_whitelist": round3_dev_whitelist(), "exclusion_geometry": round3_exclusion_geometry(),
           "v1_scoring": "disabled: v2 never imports or runs v1 score_m678/chain_reserve; v1 reserve labels are "
                         "quarantined on disk with mode 000 (QUARANTINE_v1_reserve)"}
    blob = json.dumps(reg, indent=1, sort_keys=True) + "\n"
    with open(OUT + ".tmp", "w") as fh:
        fh.write(blob)
    os.replace(OUT + ".tmp", OUT)
    return hashlib.sha256(blob.encode()).hexdigest(), reg


def load():
    with open(OUT) as fh:
        return json.load(fh)


def is_quarantined(type_cluster: str | None = None, incident: str | None = None, reg=None) -> bool:
    reg = reg or load()
    return bool((type_cluster and type_cluster in reg["v1"]["clusters"]) or
                (incident and incident in reg["v1"]["incidents"]))


if __name__ == "__main__":
    h, r = build()
    print(h, {"v1_clusters": len(r["v1"]["clusters"]), "v1_incidents": len(r["v1"]["incidents"]),
              "v1_dev_only": len(r["v1"]["dev_only_incidents"]), "r3_dev": len(r["round3_dev_whitelist"]),
              "exclusion_footprints": len(r["exclusion_geometry"])})
