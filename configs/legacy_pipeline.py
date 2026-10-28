"""
The legacy 7-class pipeline marker (finding C46, 2026-09-25).

One definition, used by pipeline.py (stamped on every run_pipeline result)
and api.py (added to stored results served by /api/demo that predate the
stamp), so the wording cannot drift. The UI renders `notice` as a banner.
"""

LEGACY_PIPELINE_NOTICE = "Legacy 7-class pipeline — retired, not validated."


def legacy_pipeline_marker() -> dict:
    return {"retired": True, "validated": False, "notice": LEGACY_PIPELINE_NOTICE}


# Every block of a legacy result is labelled "retired" (2026-10-28). It is the
# worst label in analysis/contract.py's precedence: a retired output is not a
# measurement anyone should act on, whatever it was labelled before.
RETIRED = "retired"


def _is_container(d: dict) -> bool:
    """A map of blocks (susceptibility, applicability, terrain_context, ...).
    Not itself a block: stamping a key into it would add a phantom member,
    which a consumer iterating its keys (the UI's hazardKeys) would render."""
    return bool(d) and all(isinstance(v, dict) for v in d.values())


def _stamp(block: dict) -> None:
    prior = block.get("validation_status")
    if prior is not None and prior != RETIRED:
        block["validation_status_superseded"] = prior
    block["validation_status"] = RETIRED


def _visit(d: dict, is_block: bool) -> None:
    if _is_container(d):
        for v in d.values():
            _visit(v, True)
        return
    if is_block:
        _stamp(d)
    for v in list(d.values()):
        if isinstance(v, dict):
            # Nested blocks are the status-bearing ones; plain maps such as
            # category_area_pct or palette are data, not blocks.
            _visit(v, "status" in v or "validation_status" in v)


def mark_retired(result: dict) -> dict:
    """Label every block of a legacy 7-class result `retired`, in place.

    A block is every dict-valued top-level field, and every nested dict that
    carries `status` or `validation_status`. Maps of blocks are recursed into,
    not stamped. Lists (segments) are rows, not blocks. A block's earlier
    label is kept as `validation_status_superseded`."""
    for v in result.values():
        if isinstance(v, dict):
            _visit(v, True)
    return result


def legacy_blocks(result: dict):
    """(path, block) for every block mark_retired() labels. Used by tests."""
    def walk(d, path, is_block):
        if _is_container(d):
            for k, v in d.items():
                yield from walk(v, f"{path}.{k}", True)
            return
        if is_block:
            yield path, d
        for k, v in d.items():
            if isinstance(v, dict) and k != "validation_status":
                yield from walk(v, f"{path}.{k}", "status" in v or "validation_status" in v)
    for k, v in result.items():
        if isinstance(v, dict):
            yield from walk(v, k, True)
