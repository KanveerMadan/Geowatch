"""
The legacy 7-class pipeline marker (finding C46, 2026-09-25).

One definition, used by pipeline.py (stamped on every run_pipeline result)
and api.py (added to stored results served by /api/demo that predate the
stamp), so the wording cannot drift. The UI renders `notice` as a banner.
"""

LEGACY_PIPELINE_NOTICE = "Legacy 7-class pipeline — retired, not validated."


def legacy_pipeline_marker() -> dict:
    return {"retired": True, "validated": False, "notice": LEGACY_PIPELINE_NOTICE}
