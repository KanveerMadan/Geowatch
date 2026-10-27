"""
The error convention for ingestion sources (build items 54 and 55).

  * Programmer errors and integration failures RAISE: GEE errors, network
    failures, typos, a source whose schema has changed, a required local
    file that is not installed. Nothing catches these just to turn them
    into a status.
  * `status: "unavailable"` means ONLY that the source genuinely has no
    data for this place. It is produced by raising NoDataError inside a
    source function and catching that, and only that, class. The resulting
    dict carries `exception_class: "NoDataError"`, so downstream code can
    tell "no data here" from anything else. Before this, every source
    returned one identical "unavailable" for a GEE quota error, a timeout,
    a wrong band name, a Python typo and a real data gap alike.
  * A broad `except Exception` is right only at a fan-out boundary, where
    one unit must not stop the others, and there it records
    `type(e).__name__`. Those boundaries are the scheduler and batch-runner
    loops (one AOI) and, since the item 54 amendment, run_pipeline's
    context-layer calls (one layer). A layer caught there becomes
    `status: "failed"` via layer_failed() -- deliberately NOT "unavailable",
    so "the integration broke" and "there is no data here" stay distinct
    all the way into result.json.
"""


class NoDataError(LookupError):
    """The source was reached and works, but has no data for this place."""


def no_data(exc: NoDataError, **fields) -> dict:
    """The status dict for a genuine data gap.

    `fields` carries the source's own schema (its None-valued numeric
    fields, `source`, and so on), so each caller's output shape is unchanged
    apart from the two tagging keys.
    """
    return {
        **fields,
        "status": "unavailable",
        "error": str(exc),
        "exception_class": type(exc).__name__,
    }


def layer_failed(layer: str, exc: BaseException, **fields) -> dict:
    """The block for a context layer whose source raised (item 54 amendment).

    Built by run_pipeline's layer boundary, never by a source. Every consumer
    gates on `status == "available"`, so a failed layer is excluded exactly
    as an unavailable one is; only the label and the class differ.
    """
    return {
        **fields,
        "status": "failed",
        "layer": layer,
        "error": str(exc),
        "exception_class": type(exc).__name__,
    }
