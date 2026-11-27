# M6–M8 v2: status in plain words

## Step 0, protect the evidence: done (2026-11-27)

**What was done**
- Started a separate v2 branch from the reviewed design (bfa85d0).
- Pinned every source by its exact commit.
- Locked away all of v1's reserve:
  - 19 clusters and 70 incidents can never be used in v2, for training or testing;
  - the 18 v1 reserve labels that had been built are on disk with no read permission.
- v1 will never run its one-shot test.
- Listed which old data v2 may learn from:
  - round 3's 449 DEV units;
  - v1's 14 DEV incidents.
- Listed what a new reserve event must avoid: 961 round-3 footprints.
- Gave DEV and reserve separate storage. The reserve folder cannot be opened by anything except the final one-shot scorer.

**Also done (round 3, owner fixes)**
- The scorer no longer lets a baseline "pass" against the weaker baseline. Elevation or HAND can now never pass on their own, and a tie fails. A test checks this.
- The flash-flood MRMS DEV result (AUC 0.720, gain +0.071, CI 0.051 to 0.091) is pinned in round 3's STATUS with date and commit.
- Pushed as exp/flood-round3 5ca318f.

**Numbers**
- registry.json sha256 `19632c94…` (see decisions.md).

**Next: step 1, a new metadata-only seal**
- Define incidents, submodes, windows, reach anchors, footprints and independence first.
- Recruit events from open sources:
  - DFO;
  - national breach investigations;
  - the USACE levee database;
  - the CRREL ice-jam database;
  - Canadian ice flags and the Canadian River Ice Database;
  - Nordic agencies;
  - NVE;
  - GLOF v4.2;
  - gauges.
- Join related storms, then split into DEV and reserve by whole clusters.
- Push the seal before any v2 model work.
