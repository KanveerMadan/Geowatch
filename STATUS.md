# Product track status (build/product)

Resume from here after any interruption. Worktree `~/gw-product`, branch
`build/product` off origin/master 87f52cb. Merges LAST, after the flood and
change branches (see MERGE_NOTES.md).

| Phase | What | State |
|---|---|---|
| 0 | Setup: worktree, read-first, STATUS/DECISIONS/MERGE_NOTES | done |
| 1 | Landing page | done: Lighthouse mobile perf 100 / a11y 100, axe 0 |
| 2 | City gallery | done (IDs not on local store, D4) |
| 3 | Honesty page, generated from analysis/contract.py | done; test fails on disagreement |
| 4 | Downloads with provenance | done; verified end to end (850 grid units) |
| 5 | Deployment config (prepared, not deployed) | done; image build skipped (SFINCS container running, D15) |
| 6 | Density metrics fix (item 23) | layers cached; baseline FAIL reproduced exactly |

## Failures / open

- none yet

## Notes

- Docker: daemon up but an SFINCS container (sfincs-b3aedda0) is running, so
  image builds are skipped this session (brief rule).
