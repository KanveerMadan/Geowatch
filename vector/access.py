"""
Item 24 — access indicators, from the vector layer alone.

  * Network connectivity of the layer's graph: components, largest-component
    length share, intersection density, dead-end ratio, link-node ratio.
    These are network-topology metrics, so under item 20's low-coverage
    policy they are SUPPRESSED, not emitted with a caveat. A missing alley
    turns a through-route into a dead end, so dead-end ratio under thin
    mapping measures the mapping, not the place.
  * Distance to the nearest paved access, per building and per block.
    Euclidean (footprint edge to centreline), not network distance. Paved is
    decided by RoadLayer.paved_status(): the surface tag where present, else
    a highway-class DEFAULT. The share resting on that default is reported.
    Distances stay meaningful at low coverage but are biased UPWARD when
    roads are missing, so they carry the coverage confidence flag.

Degradation is never silent: every output embeds the item 20 coverage block.
"""
from __future__ import annotations

import numpy as np
from shapely import STRtree

from vector import coverage

# Reporting cut-offs for the distance distribution. Descriptive bins, NOT a
# standard of adequate access.
ACCESS_DISTANCE_BINS_M = (25, 50, 100, 250)


def network_connectivity(layer, cov: dict) -> dict:
    if cov["topology_metrics_suppressed"]:
        return {"status": "suppressed_low_coverage",
                "reason": f"coverage_regime_flag={cov['coverage_regime_flag']}",
                "value": None}
    import networkx as nx
    G = layer.graph()
    if G.number_of_nodes() == 0:
        return {"status": "no_network", "value": None}
    deg = dict(G.degree())
    total_len = sum(d["length_m"] for *_, d in G.edges(data=True))
    comps = list(nx.connected_components(G))
    largest = max(comps, key=lambda c: sum(d["length_m"] for *_, d in G.subgraph(c).edges(data=True)))
    largest_len = sum(d["length_m"] for *_, d in G.subgraph(largest).edges(data=True))
    # Only true intersections (degree >= 3) and true ends (degree 1) count.
    # Degree-2 nodes are shape vertices along a way.
    n_int = sum(1 for v in deg.values() if v >= 3)
    n_dead = sum(1 for v in deg.values() if v == 1)
    n_topo = n_int + n_dead
    fs = layer.fetch_status("network")
    return {"status": "available" if fs["status"] == "complete" else "partial_fetch",
            "fetch": fs, "value": {
        "components": len(comps),
        "largest_component_length_share": largest_len / total_len if total_len else 0.0,
        "intersections_per_km2": n_int / layer.area_km2,
        "dead_end_ratio": n_dead / n_topo if n_topo else 0.0,
        "link_node_ratio": G.number_of_edges() / G.number_of_nodes(),
    }}


def _distance_summary(d) -> dict:
    d = np.asarray(d, dtype=float)
    return {"n": int(d.size), "median_m": float(np.median(d)),
            "p90_m": float(np.percentile(d, 90)), "max_m": float(d.max()),
            **{f"share_within_{b}m": float((d <= b).mean()) for b in ACCESS_DISTANCE_BINS_M}}


def paved_access(layer, cov: dict) -> dict:
    """Per-building and per-block distance to the nearest paved way."""
    paved, basis = [], []
    for w in layer.ways:
        ok, why = layer.paved_status(w)
        if ok:
            paved.append(w.line)        # whole way: a road just outside the AOI still serves it
            basis.append(why)
    conf = cov["footprint_metrics_confidence"]
    if not paved:
        return {"status": "no_paved_ways", "value": None, "confidence": conf}
    if not layer.footprints:
        return {"status": "no_footprints", "value": None, "confidence": conf}

    tree = STRtree(paved)
    idx = tree.nearest(layer.footprints)
    dist = np.array([fp.distance(paved[i]) for fp, i in zip(layer.footprints, idx)])
    on_default = float(np.mean([basis[i] == "class_default" for i in idx]))

    blocks = layer.blocks()
    btree = STRtree(blocks) if blocks else None
    per_block = {}
    if btree is not None:
        rep = [fp.representative_point() for fp in layer.footprints]
        for k, j in zip(*btree.query(rep, predicate="within")):
            per_block.setdefault(int(j), []).append(dist[k])
    block_medians = [float(np.median(v)) for v in per_block.values()]

    fs = layer.fetch_status("network")
    # A missing clause can only remove candidate paved ways, so distances
    # are then UPPER bounds rather than lower ones; fetch.note says "lower
    # bound" generically, so this output states its own direction.
    return {"status": "available" if fs["status"] == "complete" else "partial_fetch",
            "fetch": ({**fs, "note": "distances are UPPER BOUNDS: paved ways in the missing "
                                     "clauses were not available as access"}
                      if fs["missing_clauses"] else fs),
            "confidence": conf, "value": {
        "per_building": _distance_summary(dist),
        "per_block": (_distance_summary(block_medians) if block_medians else None),
        "blocks_with_buildings": len(per_block),
        "blocks_total": len(blocks),
        "nearest_paved_on_class_default_share": on_default,
        "distance_kind": "euclidean_footprint_edge_to_centreline",
    }, "per_building_distances_m": dist.round(2).tolist()}


def access_indicators(layer, reference=None) -> dict:
    cov = coverage.score_layer(layer, reference)
    return layer.stamp({
        "network_connectivity": network_connectivity(layer, cov),
        "paved_access": paved_access(layer, cov),
        "coverage": cov,
    })
