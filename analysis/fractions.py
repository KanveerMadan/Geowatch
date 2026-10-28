"""
Swappable fraction producers.

The pipeline asks a producer for two things and nothing else:

    produce(layer, transform, shape, window)
        -> fraction rasters on the pipeline's 10 m grid, with per-fraction
           observed masks, labels, sources and the fractions it does NOT
           compute (and why)
    hydrology_inputs(layer, fset, transform, shape, k)
        -> the `impervious` and `infiltration` surfaces pluvial and
           waterlogging read (susceptibility/inputs.py's declared shape),
           on the hydrology grid, which is the 10 m grid coarsened by k

Item 21's spectral-regression model drops in as another producer with the
same two methods: it would list impervious_total / paved / bare in FRACTIONS
instead of NOT_COMPUTED, and its artifact() would carry the model file's
sha256, which enters model_version and therefore the cache key.

StandInFractions is the producer until then:

    built        Open Buildings (or OSM) footprint area per pixel, from the
                 item 19 layer. `experimental`.
    vegetation   Sentinel-2 NDVI / MNDWI index thresholds (vector/fractions.py).
    water        `placeholder`: stand-ins for item 21's regression.
    impervious_total, paved, bare
                 not_computed, `placeholder`: they need item 21.
"""
from __future__ import annotations

from analysis.contract import sha256_json

ITEM_21_REASON = "requires item 21's spectral regression, which is not built"


class StandInFractions:
    name = "standin_footprint_s2index"
    version = "1"
    FRACTIONS = ("built", "vegetation", "water")
    NOT_COMPUTED = {"impervious_total": ITEM_21_REASON, "paved": ITEM_21_REASON,
                    "bare": ITEM_21_REASON}
    S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
    CLOUD_COVER_THRESHOLD = 60                 # vector/fractions.py's default

    def __init__(self, mask_occlusion: bool = True):
        # Item 33: shadowed (SCL 3) and snow (SCL 11) observations leave the
        # composite and the clear-observation count, as cloud and no-data
        # already did, so the denominator is Decision 14's. The filter runs on
        # the raw collection before mask_s2_clouds.
        from analysis.observability import OCCLUSION_MASKED_SCL, occlusion_filter
        self.collection_filter = occlusion_filter if mask_occlusion else None
        self.occlusion = {"masked_scl": sorted({0, 1, 8, 9, 10}
                                               | (set(OCCLUSION_MASKED_SCL) if mask_occlusion
                                                  else set()))}

    # ── identity ──
    def artifact(self) -> dict:
        from vector import fractions as vf
        from vector.sources import OPEN_BUILDINGS_ASSET
        params = {"producer": self.name, "version": self.version,
                  "water_mndwi_min": vf.WATER_MNDWI_MIN,
                  "vegetation_ndvi_min": vf.VEGETATION_NDVI_MIN,
                  "min_valid_obs": vf.MIN_VALID_OBS, "pixel_m": vf.PIXEL_M,
                  "s2_collection": self.S2_COLLECTION,
                  "cloud_cover_threshold": self.CLOUD_COVER_THRESHOLD,
                  "footprints": OPEN_BUILDINGS_ASSET, "occlusion": self.occlusion}
        return {"name": self.name, "params": params, "sha256": sha256_json(params)}

    def labels(self) -> dict:
        from vector.fractions import FRACTION_VALIDATION_STATUS
        out = {f: FRACTION_VALIDATION_STATUS[f] for f in self.FRACTIONS}
        out.update({f: "placeholder" for f in self.NOT_COMPUTED})
        return out

    def sources(self, layer, window: dict) -> dict:
        s2 = f"{self.S2_COLLECTION} median composite {window['start']}..{window['end']}"
        fp = {"open_buildings_v3": "GOOGLE/Research/open-buildings/v3/polygons",
              "osm_building": "OpenStreetMap building=* ways (Overpass)",
              "none": "no footprint source"}[layer.footprint_source]
        return {"built": [f"{fp} (item 19 layer {layer.layer_id})"],
                "vegetation": [s2], "water": [s2],
                **{f: ["none: not computed"] for f in self.NOT_COMPUTED}}

    # ── production ──
    def fetch_composite(self, layer, transform, shape, window: dict) -> dict:
        """The Earth Engine part: a median NDVI / MNDWI composite and the
        per-pixel clear-observation count, on the pipeline's grid."""
        from vector import fractions as vf
        return vf.s2_index_composite(layer, window["start"], window["end"],
                                     cloud_cover_threshold=self.CLOUD_COVER_THRESHOLD,
                                     collection_filter=self.collection_filter,
                                     grid=(transform, shape))

    def produce(self, layer, transform, shape, window: dict) -> dict:
        import numpy as np
        from vector import fractions as vf
        comp = self.fetch_composite(layer, transform, shape, window)
        cls = vf.classify_indices(comp["ndvi"], comp["mndwi"], comp["valid_obs"])
        built = vf.built_raster(layer, transform, shape)
        return {
            "rasters": {"built": built, "vegetation": cls["vegetation"], "water": cls["water"]},
            "observed": {"built": np.full(built.shape, layer.footprint_source != "none"),
                         "vegetation": cls["observed"], "water": cls["observed"]},
            "valid_obs": comp["valid_obs"],
            "transform": transform, "shape": shape,
            "fractions": self.FRACTIONS, "not_computed": dict(self.NOT_COMPUTED),
            "labels": self.labels(), "sources": self.sources(layer, window),
            "method": dict(vf.PROXY_METHOD), "producer": dict(vf.PRODUCER),
            "window": comp.get("window", window),
            "source_image_count": comp.get("source_image_count"),
            "observation_quality": comp.get("observation_quality"),
        }

    def hydrology_inputs(self, layer, fset: dict, transform, shape, k: int) -> dict:
        from susceptibility.inputs import (block_nanmean, impervious_built_area,
                                           infiltration_vegetation)
        return {"impervious": impervious_built_area(layer, transform, shape),
                "infiltration": infiltration_vegetation(
                    block_nanmean(fset["rasters"]["vegetation"], k))}
