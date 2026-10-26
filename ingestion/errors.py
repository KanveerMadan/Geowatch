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
  * A broad `except Exception` is right only at a fan-out loop (the
    scheduler, the batch runner) where one AOI must not stop the others,
    and there it records `type(e).__name__`.
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
