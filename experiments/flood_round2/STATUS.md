# flood_round2: status

Branch `exp/flood-round2`, in worktree gw-floodproto: exp/flood-final plus build/flood-learned (PR #1). Read this first on any restart, and never redo a phase marked done. Judgement calls are in DECISIONS.md.

## Open questions for the owner
- none

## Phases
| # | phase | state | notes |
|---|---|---|---|
| A | PR #1 decisions + blocking secrets scan | done | build/flood-learned d206554; PR #1 ready for review (not merged); C78 demoted; tools/secrets_scan.py + safe_push.sh; LICENCES.md |
| B | EMSR683 fetch bug | done | `_mosaic` takes the selected band's projection; regression test; control DEM unchanged (diff 0.0) |
| C | Fort Myers coastal SFINCS | todo | |
| D | coastal forcing + features | todo | |
| E | flash-flood features | todo | |
| F | urban flood references | todo | |
| G | better terrain | todo | |
| H | model v3 (DEV) | todo | |
| I | SFINCS rain / coastal / compound | todo | |
| J | pre-register round 2, freeze | todo | |
| K | one held-out pass | todo | |
| L | evidence packs | todo | |
| M | production PR | todo | |
| N | M7 / M6 / M8 scenarios | todo | |

## Running now
- nothing

## Next steps
1. Phase C (Fort Myers SFINCS), started early because it is long. Meanwhile, screen new reserved candidates from metadata only.
