/*
 * Legacy-pipeline notice — finding C46, 2026-09-25.
 *
 * Every result this UI shows comes from POST /api/analyze, i.e. run_pipeline(),
 * the retired 7-class pipeline. Each such result carries a banner saying so.
 * New runs carry `legacy_pipeline.notice`; runs stored before the marker
 * existed do not, so the same wording is the fallback — a missing field must
 * never mean "no warning".
 */

export const LEGACY_PIPELINE_NOTICE = 'Legacy 7-class pipeline — retired, not validated.'

export function legacyPipelineNotice(result) {
  if (!result) return null
  return result.legacy_pipeline?.notice || LEGACY_PIPELINE_NOTICE
}
