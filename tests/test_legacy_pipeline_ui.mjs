/*
 * C46 (2026-09-25): every run_pipeline result shown in the UI carries the
 * banner "Legacy 7-class pipeline — retired, not validated." -- including runs
 * stored before the backend marker existed.
 *
 * Run:  node tests/test_legacy_pipeline_ui.mjs
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const { legacyPipelineNotice, LEGACY_PIPELINE_NOTICE } =
  await import(join(here, '..', 'geowatch-ui', 'src', 'legacyPipeline.js'))
const app = readFileSync(join(here, '..', 'geowatch-ui', 'src', 'App.jsx'), 'utf8')

const EXACT = 'Legacy 7-class pipeline — retired, not validated.'

// 1. The wording is exactly the ruled text.
assert.equal(LEGACY_PIPELINE_NOTICE, EXACT)

// 2. No result, no banner.
assert.equal(legacyPipelineNotice(null), null)
assert.equal(legacyPipelineNotice(undefined), null)

// 3. A new run carries the backend's notice.
assert.equal(legacyPipelineNotice({ legacy_pipeline: { notice: EXACT } }), EXACT)

// 4. A stored run from before the marker still gets the banner: a missing
//    field must never mean "no warning".
for (const fixture of ['result_clean.json', 'result_degraded.json', 'result_pre_item40.json']) {
  const r = JSON.parse(readFileSync(join(here, 'fixtures', fixture), 'utf8'))
  assert.equal(r.legacy_pipeline, undefined, `${fixture} predates the marker`)
  assert.equal(legacyPipelineNotice(r), EXACT, fixture)
}

// 5. App.jsx renders it whenever a result is shown.
assert.match(app, /import \{ legacyPipelineNotice \} from '\.\/legacyPipeline'/)
assert.match(app, /\{legacyPipelineNotice\(result\) && \(/)
assert.match(app, /data-testid="legacy-pipeline-banner"/)

// 6. The only thing that sets `result` is POST /api/analyze (run_pipeline), so
//    "whenever a result is shown" == "on every run_pipeline result".
const setters = [...app.matchAll(/setResult\(([^)]*)\)/g)].map(m => m[1].trim())
assert.deepEqual([...new Set(setters)].sort(), ['data', 'null'])
assert.equal((app.match(/apiFetch\('\/api\/analyze'/g) || []).length, 1)

console.log('legacy pipeline banner: all checks passed')
