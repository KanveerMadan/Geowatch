"""
The vector track (Part 4, items 19, 20, 22-25).

One road/footprint layer per AOI (item 19, `vector.roads.RoadLayer`). Every
road-derived output -- rasterised, aggregated, network -- is a method of that
layer and carries its `layer_id`, so no consumer builds its own roads.

Status: PROPOSED RESEARCH DESIGN under the Part 4 validation-first mandate
(05_BUILD_MANUAL.md, decided 2026-09-24). Nothing here has been validated
against independent reference data, and no output is an established claim.
"""
