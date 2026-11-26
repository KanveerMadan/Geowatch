import test from 'node:test'
import assert from 'node:assert/strict'
import { compareError, historyMark, historyText, initialComparison, periodText, previousDay, replayError, signalName, summaryOf } from '../src/lib/changeHistory.js'
import { changeRows, changeSummary } from '../src/lib/change.js'

const sample = { training_period: ['2020-08-01', '2025-08-01'], period: ['2025-08-01', '2025-11-01'],
  signals: ['ndvi', 'vv_db'], counts: { insufficient_observation: 10, no_change_detected: 3, candidate_change: 2, change_detected: 1 }, event_count: 4 }

test('summary distinguishes an event from a reporting cell and a missing cell', () => {
  assert.equal(historyText({ value: sample }), '4 signal episodes recorded. 6 of 16 cells had enough observations to assess change.')
  const missing = { summary: { counts: { insufficient_observation: 9 }, event_count: 0 }, value: null }
  assert.equal(summaryOf(missing), missing.summary)
  assert.equal(historyText(missing), 'All 9 reporting cells have insufficient observations.')
  assert.equal(historyText({ reason: 'Source unavailable' }), 'Source unavailable')
})
test('detected and candidate cells have distinct marks; unassessed cells appear unknown', () => {
  const states = ['change_detected', 'candidate_change', 'no_change_detected', 'insufficient_observation',
    'increase', 'decrease', 'unchanged', 'unknown_future_value']
  assert.deepEqual(states.map((state) => historyMark({ state })),
    ['detected', 'candidate', 'none', 'unjudged', 'increase', 'decrease', 'none', 'unjudged'])
})
test('comparison respects dated evidence, archive limits, endpoints and signal availability', () => {
  const q = initialComparison(sample, { start: '2025-08-03', end: '2025-10-31' })
  assert.equal(q.before_start, '2020-08-03')
  assert.equal(q.after_end, '2025-10-31')
  assert.equal(compareError(q, sample), '')
  assert.match(compareError({ ...q, before_end: q.after_end }, sample), /first period/)
  assert.match(compareError({ ...q, after_end: '2027-01-01' }, sample), /stored/)
  assert.match(compareError({ ...q, after_end: q.after_start }, sample), /after it starts/)
  assert.match(compareError({ ...q, signal: 'invented' }, sample), /signal/)
  assert.equal(periodText(sample.period), '2025-08-01 to before 2025-11-01')
})
test('older stored comparisons still render their own counts and years', () => {
  const legacy = { built: { status: 'available', value: { increase: 1, decrease: 2, no_detectable_change: 3 },
    validation_status: 'experimental', epochs: { a: 2019, b: 2023 } } }
  assert.equal(changeRows(legacy)[0].changed, 3)
  assert.match(changeSummary(legacy), /2019 and 2023/)
})

test('replay restricts event and evidence dates to the archive and supports later evidence in hindsight', () => {
  const replay = { start: '2024-01-01', end: '2024-03-01', as_of: previousDay('2024-03-01'), mode: 'prospective' }
  assert.equal(replay.as_of, '2024-02-29')
  assert.equal(replayError(replay, sample), '')
  const later = { ...replay, as_of: '2024-05-01' }
  assert.match(replayError(later, sample), /Prospective/)
  assert.equal(replayError({ ...later, mode: 'retrospective' }, sample), '')
  assert.match(replayError({ ...later, as_of: sample.period[1] }, sample), /stored history/)
})

test('all nine optional class signals are described as class scores', () => {
  for (const k of ['water', 'trees', 'grass', 'flooded_vegetation', 'crops', 'shrub_and_scrub', 'built', 'bare', 'snow_and_ice']) {
    assert.match(signalName('dw_' + k), /class score$/)
  }
})
