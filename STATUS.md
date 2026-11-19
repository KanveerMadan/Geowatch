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
| 6 | Density metrics fix (item 23) | done: diagnosed, fixed metrics, v2 pre-registered (c29ab06) and run: still FAIL (2 hold, 1 reversed); see experiments/density_fix/REPORT.md |

## Failures / open

- Item 23 v2 FAILED (pre-registered; no bar moved). Next: held-out pair (Kanveer).
- Docker images not built (SFINCS container running all session). Build per DEPLOY.md §3 when free.
- Gallery result IDs not on any local store: re-run the three cities where the site is served (DEPLOY.md §7).
- Explorer's two pre-existing axe findings (D6).

## Done

All six phases. Final report: REPORT.md. Last full run: pytest 1076 passed /
4 skipped; node web tests 67 passed.

## Notes

- Docker: daemon up but an SFINCS container (sfincs-b3aedda0) is running, so
  image builds are skipped this session (brief rule).
