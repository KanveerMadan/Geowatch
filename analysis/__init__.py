"""
The end-to-end analysis pipeline that replaces the retired 7-class pipeline
(08_STATE.md §RETIRED; Phase 2 build, 2026-10-28).

    AOI -> vector layer (item 19) -> OSM coverage (20) -> fractions
        -> flood susceptibility (26) -> change (25) -> aggregation (22)
        -> result

No 7-class classifier is reached from here. Every output follows one
contract (analysis/contract.py).
"""
