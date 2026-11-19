# Deploying GeoWatch

Step by step, for Kanveer. **Nothing here has been deployed, no account
has been created and nothing has been bought.** Every step that creates an
account, spends money or makes something public is yours to do.

Target: **Render** (why: DECISIONS.md D10). Files: `render.yaml`,
`deploy/Dockerfile.api`, `deploy/Dockerfile.web`, `deploy/nginx.conf`,
`docker-compose.yml`, `.env.example`, `deploy/asgi.py`, `deploy/runtime.py`,
`deploy/worker.py`, `deploy/code_commit.sh`.

```
browser ──> geowatch-web (Render static site: landing, gallery, honesty,
            │                explorer, reports; free CDN + HTTPS)
            │  /api/*, /health  rewritten (same origin, no CORS needed)
            ▼
          geowatch-api (Render web service, Docker, 1 instance, 2 GB)
            deploy/asgi.py gateway: /health, rate limits, CORS, public
            explorer routes, partner-only building units, JSON logs
            └─ api.py (unchanged) ─ analysis pipeline ─ Earth Engine
            disk /app/data: results store, vector cache, boundaries
          geowatch-worker (later): SFINCS long jobs, never in the web process
```

---

## 0. Before anything goes public: four checks only you can make

1. **Esri World Imagery terms.** The explorer's default base map, the
   gallery thumbnails and the report pictures use Esri World Imagery tiles.
   `web/DESIGN.md` already says its terms must be checked before any public
   deployment. If they do not allow this use, switch the default to the dark
   OpenFreeMap style and drop the imagery thumbnails before step 6.
2. **Earth Engine licence.** Earth Engine is free for non-commercial and
   research use with a registered Cloud project; commercial use needs a paid
   Earth Engine plan. If funders or insurers pay for access, that is
   commercial. Register the project accordingly (step 2).
3. **Data licences of the outputs.** FABDEM (CC BY-NC-SA 4.0) and MERIT Hydro
   (CC BY-NC 4.0 option) are non-commercial, and every flood output is built
   on them. The downloads say so (DECISIONS.md D8). Decide GeoWatch's own
   licence; the download notes currently say "not yet chosen".
4. **Nominatim usage policy.** Place search calls the public OSM Nominatim
   server (max 1 request/second, no heavy use). Fine for a launch; if the
   site gets real traffic, move to a paid geocoder or your own instance.

## 1. Accounts you need

| Account | For | Cost |
|---|---|---|
| GitHub (have it) | Render deploys from `KanveerMadan/Geowatch` | free |
| Render (render.com) | API, static site, disk | pay as you go, card needed |
| Google Cloud (have it, for `GEE_PROJECT_ID`) | Earth Engine service account | EE free for non-commercial |
| A domain registrar (optional) | `geowatch.<tld>` | about $10–20 / year |
| An uptime monitor (optional) | alerts when `/health` fails | free tiers exist (e.g. UptimeRobot, Better Stack) |

## 2. Earth Engine service account (once)

The server cannot use your personal `earthengine authenticate` login. It
needs a service account and a key **file** that never enters the repo or an
image.

```sh
PROJECT=<your GEE_PROJECT_ID>
gcloud config set project $PROJECT
gcloud iam service-accounts create geowatch-server --display-name "GeoWatch server"
SA=geowatch-server@$PROJECT.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding $PROJECT --member serviceAccount:$SA \
  --role roles/earthengine.writer
gcloud projects add-iam-policy-binding $PROJECT --member serviceAccount:$SA \
  --role roles/serviceusage.serviceUsageConsumer
# The key goes OUTSIDE the repo, e.g. ~/secrets/ (the repo also gitignores
# *service-account*.json, *-sa.json and .env).
mkdir -p ~/secrets && gcloud iam service-accounts keys create ~/secrets/ee-key.json --iam-account $SA
chmod 600 ~/secrets/ee-key.json
```

Confirm the project is registered for Earth Engine
(console.cloud.google.com/earth-engine) with the right use type (step 0.2).

How the server uses it: `GEE_SERVICE_ACCOUNT_KEY_FILE` names the file;
`deploy/runtime.py` wraps `ee.Initialize` so every existing call in the
pipeline uses the service account. In production a missing key file stops
the server at start-up instead of failing on the first analysis.

## 3. Local full-stack test (Docker)

Only when no SFINCS container is running (`docker ps`): the images are
large and the Mac has 8 GB.

```sh
cd ~/geowatch          # or the merged checkout
cp .env.example .env   # then fill: GEOWATCH_API_KEY, GEE_PROJECT_ID,
                       # GEE_KEY_FILE_HOST=$HOME/secrets/ee-key.json
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'   # -> GEOWATCH_API_KEY
GEOWATCH_CODE_COMMIT=$(deploy/code_commit.sh) docker compose up --build
open http://localhost:8080            # landing; /explore, /gallery, /honesty
curl -s localhost:8000/health         # {"status": "ok", ...}
docker compose down                   # data stays in the geowatch-data volume
```

`deploy/code_commit.sh` refuses to run with uncommitted changes under the
analysis code: commit first, so the version stamped on results is real.

Check in the browser: search a place, analyse a small box, open its report,
download GeoJSON and CSV. `curl localhost:8000/api/results/<id>/wards/footprint`
must answer 403.

## 4. Render: create the services (from the Blueprint)

1. Sign up at render.com with GitHub; add a payment card (the API plan and
   the disk are paid).
2. Dashboard → **New → Blueprint** → pick the `Geowatch` repo, branch
   `master` (after this branch is merged). Render reads `render.yaml` and
   shows two services: `geowatch-api`, `geowatch-web`. Apply.
3. `autoDeploy` is off: nothing redeploys on push until you choose.

## 5. Render: secrets and settings for `geowatch-api`

Dashboard → `geowatch-api` → **Environment**:

| Variable | Value |
|---|---|
| `GEOWATCH_API_KEY` | generated by Render (leave it). You need it only for partner and admin calls: copy it to your password manager |
| `GEE_PROJECT_ID` | your project id |
| `GEOWATCH_CODE_COMMIT` | output of `deploy/code_commit.sh` on the commit you deploy |
| `GEOWATCH_CORS_ORIGINS` | `https://geowatch-web.onrender.com` (and later your domain) |
| others | already set by `render.yaml` (`GEOWATCH_ENV=production`, limits, proxy) |

**Secret Files** (same page): add `ee-key.json` with the contents of
`~/secrets/ee-key.json`. Render mounts it at `/etc/secrets/ee-key.json`,
which `GEE_SERVICE_ACCOUNT_KEY_FILE` already points to. Never paste the key
into an environment variable, a commit or a chat.

Then **Manual Deploy → Deploy latest commit**. Watch the logs for
`runtime ready` with `"ee": "service_account"`, then:

```sh
curl -s https://geowatch-api.onrender.com/health
# {"status":"ok","code_commit":"…","checks":{"results_store_writable":true,"earth_engine_credentials":"service_account"}}
```

If `GEOWATCH_CODE_COMMIT` is empty the server falls back to Render's
`RENDER_GIT_COMMIT` (safe: more cache misses, never a stale result) and logs
a warning.

## 6. Render: the static site

`geowatch-web` builds `web/` with `npm ci && npm run build`, serves `dist/`,
and rewrites `/api/*` and `/health` to the API. If you rename the API
service, update the two `destination` URLs in `render.yaml`. Open
`https://geowatch-web.onrender.com`: landing, `/gallery`, `/honesty` and
`/explore` should all load (the SPA rewrite handles the paths).

## 7. Seed the gallery's results on the server

The gallery's three result IDs (from the 28 Oct live runs) are not on any
server (DECISIONS.md D4), so "Open the report" fails until the cities are
re-run there. With the API key:

```sh
API=https://geowatch-api.onrender.com; KEY=<GEOWATCH_API_KEY>
# Dharavi (with the Mumbai ward layer once it is ingested), Lagos, Chandigarh:
curl -s -X POST $API/api/jobs -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"west":72.836,"south":19.037,"east":72.862,"north":19.06,"aoi_label":"dharavi","start_date":"2026-01-01","end_date":"2026-03-31"}'
# poll GET $API/api/jobs/<job id> until done; note result_id
```

Then record the new IDs in a new run record (or rerun
`analysis/live_runs.py` against the server), point
`product/gallery_cities.json` at it, run `python -m product.site_data`,
commit, and redeploy the static site. The gallery shows exactly what is in
that record, labels included.

## 8. Domain and HTTPS

1. Buy the domain (your step).
2. Render → `geowatch-web` → **Settings → Custom Domains** → add
   `geowatch.<tld>` and `www.geowatch.<tld>`. Render shows the DNS records
   (a CNAME to `geowatch-web.onrender.com`; for the apex, an ALIAS/ANAME or
   the A record it gives). Add them at the registrar.
3. Render issues and renews the TLS certificate automatically once DNS
   resolves (minutes to an hour). HTTPS is on by default; HTTP redirects.
4. Add the domain to `GEOWATCH_CORS_ORIGINS` on the API (only needed for
   cross-origin callers; the site itself is same-origin).
5. Optionally give the API its own name (`api.geowatch.<tld>`) and update
   the rewrite destinations.

## 9. The SFINCS worker (later)

`deploy/worker.py` is a stub: a job-queue protocol (pending → running →
done / failed, atomic renames, heartbeat) with no SFINCS handler yet. It is
in `docker-compose.yml` and commented out in `render.yaml` because:

- the flood branch's SFINCS runner must be registered as
  `HANDLERS["sfincs"]`;
- on Render a disk attaches to one service, so the queue and outputs need a
  shared store (S3-compatible bucket such as Cloudflare R2 or Backblaze B2,
  or Render Key Value) before the worker can be a separate service;
- SFINCS runs need several GB of RAM and long CPU time: size the worker
  plan from a measured run (Valencia), and never run it in the API process.

Until then, the API's own analysis jobs (Earth Engine-bound, minutes each)
run in its thread pool (`analysis/jobs.py`, 2 at a time). A redeploy
interrupts running jobs; the browser shows the failure and the user retries.

## 10. Monitoring

- **Health:** Render restarts the API when `/health` fails
  (`healthCheckPath`). Add an external monitor on
  `https://<domain>/health` with email alerts.
- **Logs:** Render → service → Logs. One JSON line per request
  (`method`, `path`, `status`, `ms`, `kind`, `client` = salted hash, never an
  IP). `status: 429` lines show rate limiting; `kind: partner` with 403
  shows attempts at building-level units.
- **Earth Engine:** Cloud console → Earth Engine → quotas / usage. The
  global cap `GEOWATCH_ANALYSIS_PER_DAY` (default 100) bounds public
  analyses per day; lower it if quota is tight, or set
  `GEOWATCH_PUBLIC_JOBS=0` to make analysis key-only (reads keep working).
- **Disk:** Render → `geowatch-api` → Disks. Results are immutable and
  accumulate; 10 GB is a start. Resize there.
- **Metrics:** Render shows CPU and memory per service. If memory nears
  2 GB during analyses, move to the next plan or lower concurrency.

## 11. Costs (approximate; check render.com/pricing before you commit)

| Item | Plan | About |
|---|---|---|
| API web service | Standard, 2 GB RAM | $25 / month |
| Persistent disk | 10 GB | $2.50 / month |
| Static site | | free (bandwidth allowance included) |
| Worker (later) | Standard or above | $25+ / month |
| Earth Engine | non-commercial | free within quota (commercial: paid plan) |
| Domain | | $10–20 / year |
| **Launch total** | API + disk + static | **about $28 / month** |

Starter (512 MB, about $7) is cheaper but too small for a 100 km² run with
the raster stack loaded; measure before downsizing.

## 12. Rollback and updates

- Render → service → **Events** → pick an earlier deploy → **Rollback**.
- A new deploy of changed analysis code gets a new `GEOWATCH_CODE_COMMIT`,
  so new results get new IDs and old links keep resolving to the old
  results (the store is immutable).
- After merging changes to `analysis/contract.py` or the flood validation
  files, run `python -m product.site_data` (the test suite fails until you
  do), commit, and redeploy the static site so the honesty page matches.

## 13. Security notes

- The browser never holds `GEOWATCH_API_KEY`. Do not set
  `VITE_GEOWATCH_API_KEY` for a deployed build: anything `VITE_*` is public.
- Public: stored results, wards, the 100 m grid, the explorer's analysis
  start (rate-limited, capped), imagery for stored results.
  Key-only: building- and street-segment units, legacy runs, sync
  `/api/analyze`, the scheduler.
- Exactly one API instance: rate limits and job state are in memory. Do not
  raise `numInstances` without moving them to a shared store.
