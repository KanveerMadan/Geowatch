"""
Shared Overpass client — the single place endpoints and retry policy live.

Written to close **C44**, which had two halves:

  1. Two of the three configured endpoints were unreachable, and three separate
     copies of the same round-robin loop marched through them anyway.
  2. Every caller did `raise_for_status()` inside `except Exception`, which
     collapses 429 / 400 / 502 / 503 / 504 and every transport error into one
     indistinguishable failure. The remedies for those diverge completely — a
     429 needs a long backoff, a malformed query needs to fail immediately, a
     dead host needs rotation, and a dispatcher 504 needs only a short retry —
     so a caller that cannot tell them apart cannot do the right thing for any
     of them.

WHY THE ENDPOINT LIST LOOKS LIKE THIS (measured 2026-09-23, not assumed)

Every candidate was probed twice: once with a query whose answer is known to be
non-empty, once with the paved-polygon query shape the endmember extraction
actually issues.

    overpass-api.de      200, 50 elements, 0.8-7.2 s     PRIMARY
    maps.mail.ru         200, 50 elements, 12-22 s       SECONDARY
    overpass.kumi.systems 200, 50 elements, 66 s; ReadTimeout on the second
                          query                          LAST RESORT
    overpass.osm.ch      200 with ZERO elements on a query that has 50
    openstreetmap.ru     ConnectTimeout, both attempts
    overpass.private.coffee ReadTimeout, both attempts
    overpass.osm.jp      SSLError, both attempts

**`overpass.osm.ch` is the important one and it is deliberately excluded.** It
answers 200 fast, so a liveness check that only looks at the status code marks
it healthy — but it is a regional mirror holding only Swiss data, so every
query outside Switzerland returns an empty element list. That is a *silently
wrong answer*, which is strictly worse than a dead host: a dead host fails
loudly, whereas this one would have produced an endmember library built on zero
paved polygons and nothing would have raised. Any future endpoint added here
must be validated with `check_endpoints()`, which tests for a NON-EMPTY result
on a known-non-empty query, never for HTTP 200 alone.

The list is ordered by measured latency and is not a round robin: a request
starts at the primary every time and only walks down on failure, so a healthy
primary is never skipped.
"""
from __future__ import annotations

import random
import time
from typing import Callable, Iterable

import requests

__all__ = [
    "OVERPASS_URLS", "OverpassError", "OverpassUnreachable", "OverpassRateLimited",
    "OverpassQueryError", "OverpassQueryTooHeavy", "OverpassServerError",
    "run_query", "check_endpoints",
]

# Ordered by measured reliability; NOT a round robin. See module docstring.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

USER_AGENT = "GeoWatch/1.0 (research; https://github.com/KanveerMadan/Geowatch)"
DEFAULT_TIMEOUT = 90
MAX_ROUNDS = 3              # full passes over the endpoint list
RATE_LIMIT_BASE_WAIT = 20   # seconds; doubles per rate-limited round


class OverpassError(RuntimeError):
    """Base. Carries the endpoint and, when there was one, the HTTP status."""

    def __init__(self, message, *, url=None, status=None, body=None):
        self.url, self.status, self.body = url, status, (body or "")[:400]
        detail = f" [endpoint={url}]" if url else ""
        if status is not None:
            detail += f" [HTTP {status}]"
        if self.body:
            detail += f" [body={self.body!r}]"
        super().__init__(message + detail)


class OverpassUnreachable(OverpassError):
    """Transport failed: DNS, TLS, connect timeout, read timeout. Rotate."""


class OverpassRateLimited(OverpassError):
    """429, or a 'too many requests' slot-limit body. Back off, then retry."""


class OverpassQueryError(OverpassError):
    """400 — the QUERY is malformed. Never retried: rotating cannot fix syntax."""


class OverpassQueryTooHeavy(OverpassError):
    """504 whose body is a genuine query timeout. Split the query; do not spin."""


class OverpassServerError(OverpassError):
    """5xx that is the server's problem, incl. the transient dispatcher fault."""


def _classify(resp: requests.Response, url: str) -> OverpassError | None:
    """Map one response onto the specific error, or None when it is usable."""
    body = (resp.text or "")[:400]
    low = body.lower()
    if resp.status_code == 200:
        return None
    if resp.status_code == 400:
        return OverpassQueryError(
            "Overpass rejected the query as malformed (not retried)",
            url=url, status=400, body=body)
    if resp.status_code == 429 or "too many requests" in low or "rate_limited" in low:
        return OverpassRateLimited("rate limited", url=url, status=resp.status_code, body=body)
    if resp.status_code in (503, 504):
        # The 504 that bit this project before was NOT a heavy query: the body
        # read `runtime error: open64: 0 Success /osm3s_osm_base
        # Dispatcher_Client::req` -- a transient dispatcher fault that an
        # unchanged retry cleared every time. Splitting the query would have
        # been the wrong fix, which is exactly why the body has to be read.
        if "dispatcher" in low or "open64" in low:
            return OverpassServerError("transient dispatcher fault (short retry)",
                                       url=url, status=resp.status_code, body=body)
        # Overpass words this several ways: "Query timed out in queryTime",
        # "runtime error: Query run out of memory", "please reduce your query".
        # Matching only the literal "timeout" misses "timed out" -- a real bug
        # this module shipped with until tests/test_overpass_client.py caught it.
        if any(k in low for k in ("timed out", "timeout", "time limit",
                                  "run out of memory", "reduce your query")):
            return OverpassQueryTooHeavy(
                "Overpass hit its own query time limit -- split the bbox or raise [timeout:]",
                url=url, status=resp.status_code, body=body)
        return OverpassServerError("server busy/unavailable", url=url,
                                   status=resp.status_code, body=body)
    return OverpassServerError("unexpected status", url=url,
                               status=resp.status_code, body=body)


def run_query(query: str, *, timeout: int = DEFAULT_TIMEOUT,
              urls: Iterable[str] | None = None, max_rounds: int = MAX_ROUNDS,
              log: Callable[[str], None] = print) -> list:
    """
    Run one Overpass QL query and return its `elements` list.

    Walks the endpoint list in order, starting at the primary each round.
    Failure handling is per-cause, which is the whole point of C44:

      400 malformed        -> raise immediately. No retry, no rotation.
      504 query-too-heavy  -> raise immediately. Retrying cannot help; the
                              caller must split the query.
      429 rate limited     -> rotate; honour `Retry-After`, else back off
                              20 s, 40 s, 80 s across rounds.
      5xx / dispatcher     -> rotate, short pause.
      transport failure    -> rotate IMMEDIATELY with no backoff. A dead host
                              is not busy, and sleeping on it is the waste C44
                              measured.

    Raises the most informative error seen once every endpoint is exhausted.
    """
    urls = list(urls or OVERPASS_URLS)
    if not urls:
        raise OverpassError("no Overpass endpoints configured")
    headers = {"User-Agent": USER_AGENT,
               "Content-Type": "application/x-www-form-urlencoded"}
    last: OverpassError | None = None
    rate_limited_rounds = 0

    for round_no in range(max_rounds):
        for url in urls:
            try:
                resp = requests.post(url, data={"data": query},
                                     headers=headers, timeout=timeout)
            except requests.exceptions.RequestException as e:
                # Dead host. Rotate now -- do not pay backoff for a host that
                # cannot answer. This is the concrete waste C44 described.
                last = OverpassUnreachable(f"transport failure ({type(e).__name__})", url=url)
                log(f"  [overpass] {url} unreachable: {type(e).__name__} -- next endpoint")
                continue

            err = _classify(resp, url)
            if err is None:
                try:
                    payload = resp.json()
                except ValueError as e:
                    last = OverpassServerError(f"200 but unparseable JSON ({e})",
                                               url=url, status=200, body=resp.text)
                    log(f"  [overpass] {url} returned unparseable JSON -- next endpoint")
                    continue
                if round_no or url != urls[0]:
                    log(f"  [overpass] satisfied by fallback {url}")
                return payload.get("elements", [])

            if isinstance(err, (OverpassQueryError, OverpassQueryTooHeavy)):
                # The query is the problem, not the host. Rotating would issue
                # the same bad query N more times and report the same failure
                # N attempts later.
                log(f"  [overpass] {type(err).__name__}: {err}")
                raise err

            last = err
            log(f"  [overpass] {url} -> HTTP {err.status}: {type(err).__name__}")
            if isinstance(err, OverpassRateLimited):
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                else:
                    wait = RATE_LIMIT_BASE_WAIT * (2 ** rate_limited_rounds)
                wait += random.uniform(0, 3)   # jitter: callers often run in parallel
                log(f"  [overpass] rate limited; waiting {wait:.0f}s")
                time.sleep(wait)
                rate_limited_rounds += 1
            else:
                time.sleep(3)
    raise last or OverpassError("all Overpass endpoints failed")


# A query whose answer is known to be non-empty worldwide-ish: highways in a
# dense square of central Mumbai. An endpoint that returns 200 with zero
# elements here is serving a regional extract, not the planet.
_PROBE = ('[out:json][timeout:25];'
          '(way["highway"](19.030,72.840,19.050,72.860););out ids 10;')


def check_endpoints(urls: Iterable[str] | None = None, *,
                    timeout: int = 45, log: Callable[[str], None] = print) -> dict:
    """
    Liveness AND correctness probe. Returns {url: (ok, note)}.

    `ok` requires a NON-EMPTY element list, not HTTP 200. `overpass.osm.ch`
    answers 200 in under a second and returns nothing outside Switzerland; a
    status-only check calls that healthy and the caller silently gets no data.
    """
    urls = list(urls or OVERPASS_URLS)
    out = {}
    for url in urls:
        t0 = time.time()
        try:
            r = requests.post(url, data={"data": _PROBE}, timeout=timeout,
                              headers={"User-Agent": USER_AGENT})
            dt = time.time() - t0
            if r.status_code != 200:
                out[url] = (False, f"HTTP {r.status_code}")
            else:
                n = len(r.json().get("elements", []))
                out[url] = ((n > 0), f"{n} elements in {dt:.1f}s"
                            + ("" if n else "  <-- 200 BUT EMPTY: regional extract?"))
        except requests.exceptions.RequestException as e:
            out[url] = (False, f"{type(e).__name__} after {time.time()-t0:.1f}s")
        except ValueError as e:
            out[url] = (False, f"unparseable JSON: {e}")
        log(f"  {'OK  ' if out[url][0] else 'FAIL'} {url:<56} {out[url][1]}")
    return out


if __name__ == "__main__":
    print("Probing configured Overpass endpoints (liveness + non-empty result):")
    res = check_endpoints()
    good = [u for u, (ok, _) in res.items() if ok]
    print(f"\n{len(good)} of {len(res)} usable.")
    raise SystemExit(0 if len(good) >= 2 else 1)
