"""
Item 21 Phase A, part 7 — hand-labelling tooling for LABELLING_GUIDE.md.

  tiles.py      stratified random ~200 m tile frame on the native S2 grid
  fractions.py  label polygons -> per-class 10 m fractions (area, never
                eyeballed), cell exclusion for unsure + shadow_full
  records.py    per-tile metadata record, versioned label store, sealed
                validation batches
  qc.py         blind re-label comparison, polygon IoU and 10 m fraction level

The five numbers LABELLING_GUIDE.md §9 leaves open are UNSET in
configs/labelling.yaml; anything that needs one raises OpenNumberUnset.
"""
