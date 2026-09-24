"""
C44 regression tests: failure causes must stay distinguishable.

The defect these lock down is not "queries fail" -- it is that every failure
looked identical, so no caller could choose the right remedy. Each test below
asserts a DIFFERENT cause produces a DIFFERENT outcome.
"""
import sys, types, pathlib
import pytest
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ingestion import overpass as ov


class FakeResp:
    def __init__(self, status=200, body="", json_payload=None, headers=None):
        self.status_code, self.text = status, body
        self._json, self.headers = json_payload, headers or {}

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _patch(monkeypatch, responses):
    """Feed `responses` in order; each may be a FakeResp or an exception."""
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        r = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(ov.requests, "post", fake_post)
    monkeypatch.setattr(ov.time, "sleep", lambda *_: None)
    return calls


OK = FakeResp(200, json_payload={"elements": [{"id": 1}]})


# ---- the four causes must map to four different exception types -------------

def test_malformed_query_raises_query_error_and_does_not_rotate(monkeypatch):
    calls = _patch(monkeypatch, [FakeResp(400, "line 1: parse error")])
    with pytest.raises(ov.OverpassQueryError):
        ov.run_query("garbage", log=lambda *_: None)
    assert len(calls) == 1, "a malformed query must not be reissued to other hosts"


def test_query_too_heavy_is_distinct_from_server_error(monkeypatch):
    _patch(monkeypatch, [FakeResp(504, "runtime error: Query timed out in queryTime")])
    with pytest.raises(ov.OverpassQueryTooHeavy):
        ov.run_query("q", log=lambda *_: None)


def test_dispatcher_504_is_a_server_error_not_a_heavy_query(monkeypatch):
    """The exact body this project saw: a transient fault a plain retry clears.
    Classifying it as 'too heavy' would send someone to split their bbox."""
    body = "runtime error: open64: 0 Success /osm3s_osm_base Dispatcher_Client::req"
    _patch(monkeypatch, [FakeResp(504, body)])
    with pytest.raises(ov.OverpassServerError) as ei:
        ov.run_query("q", max_rounds=1, log=lambda *_: None)
    assert not isinstance(ei.value, ov.OverpassQueryTooHeavy)


def test_rate_limit_is_distinct_and_retried(monkeypatch):
    calls = _patch(monkeypatch, [FakeResp(429, "too many requests"), OK])
    assert ov.run_query("q", log=lambda *_: None) == [{"id": 1}]
    assert len(calls) >= 2, "a 429 must be retried, not surfaced immediately"


def test_transport_failure_rotates_without_sleeping(monkeypatch):
    slept = []
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        if len(calls) == 1:
            raise requests.exceptions.ConnectTimeout("dead host")
        return OK

    monkeypatch.setattr(ov.requests, "post", fake_post)
    monkeypatch.setattr(ov.time, "sleep", lambda s: slept.append(s))
    assert ov.run_query("q", log=lambda *_: None) == [{"id": 1}]
    assert calls[0] != calls[1], "must move to the next endpoint"
    assert not slept, "a dead host is not busy -- backing off on it is the C44 waste"


# ---- endpoint-list behaviour ------------------------------------------------

def test_primary_is_tried_first_every_time_not_round_robin(monkeypatch):
    calls = _patch(monkeypatch, [OK])
    for _ in range(3):
        ov.run_query("q", log=lambda *_: None)
    assert calls == [ov.OVERPASS_URLS[0]] * 3, (
        "the old code advanced the index per attempt, so a healthy primary got skipped")


def test_dead_endpoints_are_not_in_the_configured_list():
    for dead in ("openstreetmap.ru", "private.coffee", "osm.jp"):
        assert not any(dead in u for u in ov.OVERPASS_URLS), f"{dead} measured dead"


def test_regional_mirror_excluded():
    """overpass.osm.ch answers 200 fast but returns nothing outside Switzerland.
    A silently-empty endpoint is worse than a dead one."""
    assert not any("osm.ch" in u for u in ov.OVERPASS_URLS)


def test_at_least_two_endpoints_configured():
    assert len(ov.OVERPASS_URLS) >= 2


# ---- the correctness probe --------------------------------------------------

def test_check_endpoints_fails_a_200_that_returns_nothing(monkeypatch):
    """The osm.ch trap: liveness alone would call this healthy."""
    monkeypatch.setattr(ov.requests, "post",
                        lambda url, **kw: FakeResp(200, json_payload={"elements": []}))
    res = ov.check_endpoints(["https://example.invalid/api"], log=lambda *_: None)
    ok, note = res["https://example.invalid/api"]
    assert ok is False and "EMPTY" in note


def test_check_endpoints_passes_a_200_with_elements(monkeypatch):
    monkeypatch.setattr(ov.requests, "post",
                        lambda url, **kw: FakeResp(200, json_payload={"elements": [1, 2]}))
    res = ov.check_endpoints(["https://example.invalid/api"], log=lambda *_: None)
    assert res["https://example.invalid/api"][0] is True


# ---- both consumers share the fix -------------------------------------------

def test_both_generators_use_the_shared_list():
    import generate_osm_road_masks as roads
    import generate_osm_water_masks as water
    assert roads.OVERPASS_URLS is ov.OVERPASS_URLS
    assert water.OVERPASS_URLS is ov.OVERPASS_URLS, (
        "water masks used to keep its own copy of the list")


def test_error_carries_status_and_endpoint(monkeypatch):
    """C44's second half: the status code must survive into the message."""
    _patch(monkeypatch, [FakeResp(503, "busy")])
    with pytest.raises(ov.OverpassError) as ei:
        ov.run_query("q", max_rounds=1, log=lambda *_: None)
    msg = str(ei.value)
    assert "503" in msg and "endpoint=" in msg
