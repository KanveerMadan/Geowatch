"""
Build item 19 — the vector road layer.

Synthetic OSM and footprint inputs, so nothing touches the network. Live
results per AOI are recorded in 05_BUILD_MANUAL.md item 19.

Run from the repo root:  pytest tests/test_vector_roads.py
"""
import math
import re

import pytest
from shapely.geometry import box

from ingestion.overpass import OverpassServerError
from vector import roads, sources
from vector.aois import BASELINE_AOIS
from vector_synth import (BBOX, M_PER_DEG_LON, _fix_ns, _highways, _layer,
                          _rows_of_huts, _way, grid_layer)  # noqa: F401  (grid_layer is a fixture)

# ── groupings ──

def test_narrow_and_broad_are_separate_groupings():
    assert roads.NARROW_PEDESTRIAN_CLASSES < roads.BROAD_PEDESTRIAN_CLASSES
    assert {"service", "residential", "track"} <= roads.BROAD_PEDESTRIAN_CLASSES
    assert not ({"service", "residential", "track"} & roads.NARROW_PEDESTRIAN_CLASSES)


def test_lengths_by_grouping(grid_layer):
    L = grid_layer.lengths_km()
    ew_km = 0.010 * M_PER_DEG_LON / 1000
    assert L["arterial"] == pytest.approx(ew_km, rel=0.01)
    assert L["narrow_pedestrian"] == pytest.approx(1.112, rel=0.02)
    # residential is broad but not narrow; footway is both.
    assert L["broad_pedestrian"] == pytest.approx(L["narrow_pedestrian"] + ew_km, rel=0.01)
    assert L["all"] == pytest.approx(2 * ew_km + L["narrow_pedestrian"], rel=0.01)


def test_widths_are_labelled_defaults():
    assert hasattr(roads, "HIGHWAY_WIDTH_M_DEFAULT")
    assert not hasattr(roads, "HIGHWAY_WIDTH_M"), "the name must say these are defaults"
    src = open(roads.__file__).read()
    assert "DEFAULTS, NOT MEASUREMENTS" in src


# ── surface tag coverage is measured ──

def test_surface_coverage_is_measured_by_length(grid_layer):
    sc = grid_layer.surface_coverage()
    # Only the primary (one third of total length, roughly) carries a tag.
    total = grid_layer.lengths_km()["all"]
    assert sc["all"]["tagged_share"] == pytest.approx(grid_layer.lengths_km()["arterial"] / total, rel=0.01)
    assert sc["arterial"]["paved_share"] == pytest.approx(1.0)
    assert sc["narrow_pedestrian"]["untagged_share"] == pytest.approx(1.0)


@pytest.mark.parametrize("value,cls", [("asphalt", "paved"), ("dirt", "unpaved"),
                                       ("weird", "other"), (None, "untagged")])
def test_surface_class(value, cls):
    assert roads.surface_class(value) == cls


def test_paved_status_records_its_basis(grid_layer):
    by_hw = {w.highway: grid_layer.paved_status(w) for w in grid_layer.ways}
    assert by_hw["primary"] == (True, "surface_tag")
    assert by_hw["residential"] == (True, "class_default")
    assert by_hw["footway"] == (False, "class_default")


# ── one source, many representations ──

def test_every_representation_traces_to_the_layer(grid_layer):
    from rasterio.transform import from_origin
    lid = grid_layer.layer_id
    assert lid
    minx, miny, maxx, maxy = grid_layer.aoi.bounds
    tr = from_origin(minx, maxy, 10, 10)
    shape = (int((maxy - miny) // 10), int((maxx - minx) // 10))
    assert grid_layer.lengths_km()["source_layer_id"] == lid
    assert grid_layer.surface_coverage()["source_layer_id"] == lid
    assert grid_layer.rasterize(tr, shape)["source_layer_id"] == lid
    assert grid_layer.graph().graph["source_layer_id"] == lid


def test_raster_area_matches_vector_road_space(grid_layer):
    from rasterio.transform import from_origin
    minx, miny, maxx, maxy = grid_layer.aoi.bounds
    tr = from_origin(minx, maxy, 10, 10)
    shape = (int(math.ceil((maxy - miny) / 10)), int(math.ceil((maxx - minx) / 10)))
    r = grid_layer.rasterize(tr, shape, supersample=10)
    raster_m2 = float(r["fraction"].sum()) * 100.0
    assert raster_m2 == pytest.approx(grid_layer.road_space().area, rel=0.03)


def test_graph_uses_shared_osm_nodes(grid_layer):
    G = grid_layer.graph()
    assert G.degree[2] == 4      # primary and footway cross at node 2
    assert G.has_edge(6, 7)
    assert sum(d["length_m"] for *_, d in G.edges(data=True)) == pytest.approx(
        grid_layer.lengths_km()["all"] * 1000, rel=0.01)


def test_layer_id_changes_with_inputs():
    a = _layer([_fix_ns(_way(2, "footway", 0, 0, 0, [4, 2, 5]))])
    b = _layer([_fix_ns(_way(2, "path", 0, 0, 0, [4, 2, 5]))])
    assert a.layer_id != b.layer_id


# ── negative space ──

def test_negative_space_is_derived_only_below_the_trigger():
    thin = _layer([], footprints=_rows_of_huts())
    assert thin.negative_space_triggered
    assert thin.negative_space.area > 0
    # The 4 m alley is about 4 m x 210 m = 840 m^2, plus the 3 m gaps.
    assert 600 < thin.negative_space.area < 2500

    many_footways = [_fix_ns(_way(10 + k, "footway", 0, 0, 0, [100 + 3 * k, 101 + 3 * k, 102 + 3 * k]))
                     for k in range(2)]
    dense = _layer(many_footways, footprints=_rows_of_huts())
    assert dense.lengths_km()["narrow_pedestrian"] / dense.area_km2 > roads.NEGATIVE_SPACE_TRIGGER_KM_PER_KM2
    assert not dense.negative_space_triggered
    assert dense.negative_space.is_empty


def test_negative_space_never_enters_the_network():
    thin = _layer([], footprints=_rows_of_huts())
    assert thin.graph().number_of_edges() == 0
    assert thin.road_space(include_negative_space=True).area > 0


# ── fetching ──

def _clause_matches(clause, hw):
    for key_op, pattern in re.findall(r'\["highway"(=|~|!~)"([^"]+)"\]', clause):
        if key_op == "=" and hw != pattern:
            return False
        if key_op == "~" and not re.search(pattern, hw):
            return False
        if key_op == "!~" and re.search(pattern, hw):
            return False
    return True


@pytest.mark.parametrize("hw", ["motorway", "primary_link", "tertiary", "residential",
                                "service", "footway", "steps", "path", "pedestrian",
                                "track", "living_street", "unclassified", "cycleway",
                                "bridleway", "construction"])
def test_highway_clauses_partition_highway_star(hw):
    matches = [g for g, c in sources.HIGHWAY_CLAUSES.items() if _clause_matches(c, hw)]
    assert len(matches) == 1, (hw, matches)


def test_unretrievable_clause_is_recorded_not_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "CACHE_DIR", str(tmp_path))

    def run(query, **k):
        if sources.HIGHWAY_CLAUSES["narrow_pedestrian"] in query:
            raise OverpassServerError("busy", status=503)
        return [_fix_ns(_way(1, "primary", 0, 0, 0, [1, 2, 3]))]

    out = sources.fetch_osm_highways("t", BBOX, run=run)
    assert out["clauses"]["narrow_pedestrian"] is None
    assert out["unavailable"] == ["narrow_pedestrian"]
    assert len(out["ways"]) == 1


def test_fetched_clauses_are_cached_per_clause(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "CACHE_DIR", str(tmp_path))
    calls = []

    def run(query, **k):
        calls.append(query)
        return []

    sources.fetch_osm_highways("t", BBOX, run=run)
    sources.fetch_osm_highways("t", BBOX, run=run)
    assert len(calls) == len(sources.HIGHWAY_CLAUSES)


def test_cache_key_is_bound_to_the_box():
    assert sources.bbox_key("x", BBOX) != sources.bbox_key("x", (0, 0, 1, 1))


def test_baseline_aois_match_run_all_cities():
    import run_all_cities
    assert {k: tuple(v) for k, v in run_all_cities.CITIES.items()} == BASELINE_AOIS


def test_too_heavy_clause_is_split_and_deduped(tmp_path, monkeypatch):
    """A 504 query-timeout is the one failure a smaller box fixes. A way
    crossing the split line comes back from two quarters and is kept once."""
    from ingestion.overpass import OverpassQueryTooHeavy
    monkeypatch.setattr(sources, "CACHE_DIR", str(tmp_path))
    full = sources._overpass_bbox(BBOX)
    calls = []

    def run(query, **k):
        calls.append(query)
        if full in query:
            raise OverpassQueryTooHeavy("timed out", status=504)
        return [_fix_ns(_way(7, "primary", 0, 0, 0, [1, 2, 3]))]

    out = sources.fetch_osm_highways("t", BBOX, run=run)
    assert [w["id"] for w in out["ways"]] == [7]
    assert out["unavailable"] == []
    assert len(calls) == len(sources.HIGHWAY_CLAUSES) * 5   # 1 refused + 4 quarters each


def test_blocks_partition_the_aoi(grid_layer):
    """The network splits the box into blocks that tile it exactly."""
    blocks = grid_layer.blocks()
    assert len(blocks) == 6        # 2 vertical x 3 horizontal strips
    cut = grid_layer.BLOCK_CUT_WIDTH_M * grid_layer.lengths_km()["all"] * 1000
    assert grid_layer.aoi.area - sum(b.area for b in blocks) == pytest.approx(cut, rel=0.05)


def test_no_roads_means_one_block(tmp_path):
    layer = _layer([])
    assert len(layer.blocks()) == 1
