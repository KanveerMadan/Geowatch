# GeoWatch public deployment: audit (2026-11-26)

**Audited:** master `e69b925`, which includes PR #3 (deploy) and PR #4 (Mumbai wards).
- Frontend: https://geowatch-azure.vercel.app
- API: https://geowatch-api-lmzh.onrender.com (the live `/health` reports `code_commit e69b9258ff3f` and a service-account Earth Engine login).

**Method:** read-only. Live checks were limited to safe requests:
- `/health` and `GET /`;
- CORS preflights;
- the public results list;
- one malformed `POST /api/jobs` to confirm keyless access, which starts nothing;
- the served JS bundle.

**Full test suite on master:** 1126 passed, 4 skipped, no failures.

## Already acted on (owner-authorised)
- **PR #5, `fix/deploy-urgent` (open, NOT merged).** The merge was blocked by this session's permission rules, so the owner must merge it. It contains:
  1. the river-flood label withdrawal (C1);
  2. a default cap of 20 public analyses a day (H1).
  - Its full suite: 1127 passed, 4 skipped.
- After the merge, check:
  - `/health` shows the new `code_commit`;
  - a new small analysis returns `susceptibility/fluvial: experimental` with `validated_scope: null`.

## Findings, most severe first

### C1 (critical, honesty): river flooding is shown as "Validated"
- **What:** stored live results return `outputs/susceptibility/fluvial: validated`, and the site renders "Validated" with a scope note.
  - The source is `analysis/contract.py` `VALIDATED_CONFIGS["fluvial"]`: the October HAND check, Hanoi + Kolonnawa.
  - Flood round 2 (Nov 2026) found plain elevation beats that method on river floods (DEV mean AUC 0.80 vs 0.65). The claim was withdrawn in PR #1, which was never merged.
  - No flood type is validated today.
- **Fix:** merge PR #5 (`WITHDRAWN_VALIDATIONS`; `validated_scope()` returns `None`, so the label is `experimental`).
- **Later:** merge or close PR #1 deliberately. It changes the river and waterlogging method to plain elevation.
- **Stale results:** results already on the Render disk keep the old label until that disk is replaced (redeploy or restart).

### H1 (high, cost / quota): anyone can start analyses on the project's Earth Engine quota
- **What:** the gateway (`deploy/asgi.py`) adds the server's key to public `POST /api/jobs`. A keyless request reached validation live.
  - Limits: 4 per hour per client and 100 per day in total (PR #5 makes it 20), 1 worker, 4 km² cap. The area cap is enforced server-side, which was confirmed in `validate_analysis_request`.
- **Client identity (likely wrong):**
  - `render.yaml` starts uvicorn without `--proxy-headers`, and `GEOWATCH_TRUST_PROXY` defaults to 0. So "client" is probably Render's proxy address, and every visitor shares one bucket. That makes it about 4 analyses an hour for the whole internet, which one person can use up.
  - If proxy trust is switched on, do not use the left-most `X-Forwarded-For` entry (`_client()` does today), because a client can forge it. Use the right-most entry that Render's proxy appends.
- **Counters are in memory:** they reset whenever the free instance sleeps and wakes, so the daily cap is per-uptime, not per-day.
- **Fixes, smallest first:**
  1. merge PR #5;
  2. set `GEOWATCH_PUBLIC_JOBS=0` on Render if quota matters more than public analysis;
  3. take the client from the right-most forwarded hop;
  4. if the cap must hold across restarts, persist the daily counter (e.g. a small file or Render KV).

### H2 (high, licences for a public app)
- **Earth Engine:** the registered Earth Engine project is a non-commercial / research registration, and a service account serves public users. Earth Engine's non-commercial terms allow this only for non-commercial use.
  - **Fix:** say on the site: "Non-commercial research tool; uses Google Earth Engine under its non-commercial terms".
- **FABDEM (CC BY-NC-SA 4.0)** is used by the live pipeline (`projects/sat-io/open-datasets/FABDEM`).
  - Non-commercial only, attribution required, and share-alike for derived products.
  - Maps derived from FABDEM inherit CC BY-NC-SA.
  - **Fix:** attribute FABDEM (University of Bristol / Fathom) and label FABDEM-derived layers CC BY-NC-SA.
- **MERIT Hydro** is used for HAND and upstream area. It is dual-licensed CC BY-NC 4.0 / ODbL 1.0.
  - **Fix:** choose ODbL with attribution, or keep it non-commercial and state that.
- **Others:** Copernicus DEM GLO-30, ESA WorldCover, JRC water and the sat-io shorelines need attribution lines. The DataMeet Mumbai ward boundaries' licence should be confirmed and cited.
- **There is no `LICENCES.md` on master** and no attribution or non-commercial notice in the served bundle.
  - **Fix:** add an attributions/licence page linked from the footer.

### M1 (medium, privacy): the public results list shows everyone's analysed areas
- **What:** `GET /api/results` needs no key and returns every stored result's bbox, label, window and time. For example, someone's drawn area near 39.04 E 23.41 N is listed.
- **Fix:** exempt only `/api/results/<id>` from the key, not the bare list. Change `PUBLIC_READ` in `deploy/asgi.py` to require at least one path segment after `/api/results`, or drop the list from the public gateway.

### M2 (medium, user honesty): results vanish
- **What:** free Render storage is ephemeral. Results and report links disappear on sleep, restart or deploy. `DEPLOY.md` says so, but the site does not tell users (no such text in the bundle).
- **Fix:** add a one-line notice by the report link ("Results are temporary on this free server; download or re-run"), or move results to persistent storage.

### L1 (low)
- `/health` is public and shows the code commit and the Earth Engine credential mode. That is acceptable; consider removing the mode.
- CORS works: the Vercel origin gets 204, a foreign origin 403. CORS does not stop non-browser clients; the rate limits are the control (see H1).

## Checked and fine
- **No API key in the frontend.** The production build drops `VITE_GEOWATCH_API_KEY` (`web/src/lib/api.js`). The served bundle (`index-DDsuKqlF.js`) contains no `VITE_*` key, no `X-API-Key` value and no long token strings.
- **The server key** is generated by Render (`generateValue: true`) and never sent to browsers.
- **No secrets in git.** On master: no private keys, `client_email`/`private_key` values, Google/GitHub tokens, `.env`, `ee-key.json` or `.pem` files. The only hit is code reading `client_email` from the mounted key file.
- **The Earth Engine service-account key** is a Render secret file (`/etc/secrets/ee-key.json`), and production refuses to start without it.
- **Keyed routes still need the key:** `/api/runs` and `/api/scheduler/status` return 401 without it, and sync `/api/analyze` and the legacy routes are not in the public list.
- **The area cap** (4 km², `GEOWATCH_MAX_AREA_KM2`) and the single worker are enforced server-side.
