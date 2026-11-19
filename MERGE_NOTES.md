# Merge notes (build/product)

This branch merges LAST, after the flood and change branches. Every file
outside the new product/deploy files that this branch changes is listed here
with the reason.

| File | Change | Why |
|---|---|---|
| web/src/main.jsx | Rewritten as a router (route.js): landing / explore / gallery / honesty / report, each lazy | New public pages. If a branch edits main.jsx, keep its change inside the `explore` (App) or `report` route |
| web/src/design/tokens.js | Added `type.hero` only | Landing headline (D3) |
| web/index.html | Added a meta description | SEO / link previews |
| web/src/report/ReportPage.jsx | Imports DownloadBar into the actions bar; one caption line in Data sources | Phase 4 downloads. Conflicts unlikely; keep both if the flood/change branches edit the report body |
| web/src/styles/report.css | `.rbar` wraps; `.rdl*` rules added after `.rbar :focus-visible` | Download bar styling |
| web/src/lib/api.js | Appended `getWardPage()` | Paging units for downloads |
| (none in Phase 5) | api.py, analysis/, ingestion/ untouched; deploy/ is new | The gateway wraps api.app instead of editing it |

## Things the other branches' merges will trip, on purpose

- `tests/test_deploy.py::test_every_env_var_the_code_reads_is_in_env_example`
  fails if the flood or change branch adds an `os.getenv("X")` (e.g.
  `GEOWATCH_CONTACT_EMAIL` from ingestion/contact.py, if it lands). Add the
  variable to `.env.example` with a comment.
- `tests/test_site_data.py` fails if the flood branch changes
  `analysis/contract.py` (verdicts, scope, taxonomy, pinned round files) or
  the round result files. Run `python -m product.site_data` after the merge
  and commit the regenerated `web/src/generated/*.json`.
- `deploy/requirements-api.txt`: if the flood/change branches import a new
  third-party package in analysis/, vector/, susceptibility/ or ingestion/,
  pin it here, or the image will fail at import.
- The flood branch's SFINCS runner registers as
  `deploy.worker.HANDLERS["sfincs"]`; it must not run in the API process.
- `deploy/Dockerfile.api` copies `experiments/flood_validation/result_*.json`
  (the contract's pinned verdict files). New pinned files under another
  directory must be added to the COPY lines and `.dockerignore`.
| vector/density.py | Added `MASS_GAP_M`, `built_masses()`, `_mass_block()`, a `built_mass` block in `density_metrics()`, and `SEPARATION_TEST_V2`. v1 untouched | Phase 6, item 23 fix. **vector/ is in contract.CODE_PATHS: the merge changes code_commit, so results computed after it get a new version_id and new result IDs** (stored results stay; nothing is recomputed silently). Is `density_metrics` called by analysis/run.py? No (checked: no import of vector.density in analysis/), so no output value changes, only the version stamp |
| tests/test_vector_density.py | 8 tests appended | Built masses invariant to fragmentation; v1 and v2 pinned |
