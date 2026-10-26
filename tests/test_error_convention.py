"""
C18 + the broad-except finding / build items 54 and 55 — one error convention.

THE CONVENTION:
  * Programmer errors and integration failures RAISE. That covers a GEE
    error, a network failure, a typo, and a source whose schema changed.
  * A status dict with status "unavailable" means ONLY that the source
    genuinely has no data for this place. Every such dict carries
    `exception_class: "NoDataError"`, so downstream code can tell it apart.
  * A broad catch exists only at a fan-out loop (the scheduler, the batch
    runner), where one city must not stop the rest. Those catches record
    the exception class.

04_FINDINGS_LEDGER.md: every function in hydrology.py, coastal.py,
rainfall.py and vulnerability_sources.py wrapped its body in
`except Exception` and returned an identical "unavailable" for a GEE quota
error, a timeout, a wrong band name, a typo or a real data gap. C18: the
scheduler detected failure via `except`, while run_pipeline signalled it
in-band, so a failed refresh printed "refreshed OK".

Earth Engine is mocked throughout. Nothing here touches the network.

Run from the repo root:  pytest tests/test_error_convention.py
"""

from unittest.mock import MagicMock, patch

import ee
import openpyxl
import pytest

from configs import vulnerability_constants as K
from ingestion import coastal, hydrology, rainfall, vulnerability_sources as vs

BBOX = dict(west=72.836, south=19.037, east=72.862, north=19.06)

INTEGRATION_ERRORS = [
    pytest.param(ee.EEException("User memory limit exceeded."), id="ee-quota"),
    pytest.param(ConnectionError("network unreachable"), id="network"),
    pytest.param(TimeoutError("read timed out"), id="timeout"),
]
PROGRAMMER_ERRORS = [
    pytest.param(NameError("name 'hnd_stast' is not defined"), id="typo"),
    pytest.param(TypeError("unsupported operand"), id="type"),
]


# ── Integration and programmer errors raise, from every module ──────────

def _gee_entry_points():
    return [
        ("ingestion.hydrology.initialize_gee",
         lambda: hydrology.get_merit_hand_context(**BBOX)),
        ("ingestion.hydrology.initialize_gee",
         lambda: hydrology.get_fabdem_elevation_stats(**BBOX)),
        ("ingestion.hydrology.initialize_gee",
         lambda: hydrology.get_slope_stats(**BBOX)),
        ("ingestion.coastal.initialize_gee",
         lambda: coastal.get_coastline_context(**BBOX)),
        ("ingestion.vulnerability_sources.initialize_gee",
         lambda: vs.get_country_iso3_for_aoi(**BBOX)),
    ]


@pytest.mark.parametrize("exc", INTEGRATION_ERRORS + PROGRAMMER_ERRORS)
@pytest.mark.parametrize("target,call", _gee_entry_points(),
                         ids=["merit_hand", "fabdem", "slope", "coastline", "country"])
def test_gee_module_raises_instead_of_reporting_unavailable(target, call, exc):
    with patch(target, side_effect=exc):
        with pytest.raises(type(exc)):
            call()


@pytest.mark.parametrize("exc", INTEGRATION_ERRORS + PROGRAMMER_ERRORS)
def test_rainfall_raises_instead_of_reporting_unavailable(exc):
    with patch("ingestion.rainfall.ee.ImageCollection", side_effect=exc):
        with pytest.raises(type(exc)):
            rainfall.get_rainfall_climatology(MagicMock())


# ── Genuine no-data returns unavailable, tagged NoDataError ─────────────

def _reducing_image(stats):
    img = MagicMock()
    for m in ("select", "filterBounds", "mosaic", "clip", "reproject"):
        getattr(img, m).return_value = img
    img.reduceRegion.return_value.getInfo.return_value = stats
    return img


def _assert_no_data(result):
    assert result["status"] == "unavailable"
    assert result["exception_class"] == "NoDataError"
    assert result["error"]


def test_merit_hand_no_value_is_no_data():
    img = _reducing_image({"hnd_mean": None, "hnd_min": None, "hnd_max": None, "upa": None})
    with patch("ingestion.hydrology.initialize_gee"), \
         patch("ingestion.hydrology.ee.Image", return_value=img), \
         patch("ingestion.hydrology.ee.Geometry"), \
         patch("ingestion.hydrology.ee.Reducer"):
        _assert_no_data(hydrology.get_merit_hand_context(**BBOX))


def test_fabdem_no_value_is_no_data():
    img = _reducing_image({"b1_mean": None})
    with patch("ingestion.hydrology.initialize_gee"), \
         patch("ingestion.hydrology.ee.ImageCollection", return_value=img), \
         patch("ingestion.hydrology.ee.Geometry"), \
         patch("ingestion.hydrology.ee.Reducer"):
        _assert_no_data(hydrology.get_fabdem_elevation_stats(**BBOX))


def test_slope_no_value_is_no_data():
    img = _reducing_image({"slope": None})
    with patch("ingestion.hydrology.initialize_gee"), \
         patch("ingestion.hydrology.ee.ImageCollection", return_value=img), \
         patch("ingestion.hydrology.ee.Terrain.slope", return_value=img), \
         patch("ingestion.hydrology.ee.Geometry"), \
         patch("ingestion.hydrology.ee.Reducer"):
        _assert_no_data(hydrology.get_slope_stats(**BBOX))


def test_rainfall_empty_collection_is_no_data():
    col = MagicMock()
    col.filterBounds.return_value = col
    col.filterDate.return_value = col
    col.size.return_value.getInfo.return_value = 0
    with patch("ingestion.rainfall.ee.ImageCollection", return_value=col):
        _assert_no_data(rainfall.get_rainfall_climatology(MagicMock()))


def _countries(count, props=None):
    fc = MagicMock()
    fc.filterBounds.return_value = fc
    fc.size.return_value.getInfo.return_value = count
    feat = MagicMock()
    feat.toDictionary.return_value.getInfo.return_value = props or {}
    return fc, feat


def test_country_over_ocean_is_no_data():
    fc, feat = _countries(0)
    with patch("ingestion.vulnerability_sources.initialize_gee"), \
         patch("ingestion.vulnerability_sources.ee.FeatureCollection", return_value=fc), \
         patch("ingestion.vulnerability_sources.ee.Geometry"):
        r = vs.get_country_iso3_for_aoi(**BBOX)
    _assert_no_data(r)
    assert r["iso3"] is None


def test_country_schema_change_raises():
    """A matched boundary without `country_co` is the asset's schema
    changing. That is a broken integration, not a place with no country."""
    fc, feat = _countries(1, {"country_na": "India"})
    with patch("ingestion.vulnerability_sources.initialize_gee"), \
         patch("ingestion.vulnerability_sources.ee.FeatureCollection", return_value=fc), \
         patch("ingestion.vulnerability_sources.ee.Feature", return_value=feat), \
         patch("ingestion.vulnerability_sources.ee.Geometry"):
        with pytest.raises(KeyError):
            vs.get_country_iso3_for_aoi(**BBOX)


# ── INFORM: the local file ───────────────────────────────────────────────

HEADERS = [K.INFORM_COL_ISO3, K.INFORM_COL_VULNERABILITY,
           K.INFORM_COL_COPING_CAPACITY, K.INFORM_COL_RELIABILITY,
           K.INFORM_COL_PCT_MISSING]


@pytest.fixture
def inform_file(tmp_path, monkeypatch):
    path = tmp_path / "inform.xlsx"

    def write(rows, headers=HEADERS):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = K.INFORM_RISK_SHEET_NAME
        ws.append([None] * len(headers))
        ws.append(headers)
        ws.append(["units"] * len(headers))
        for r in rows:
            ws.append(r)
        wb.save(path)
        monkeypatch.setattr(vs, "INFORM_RISK_FILE_PATH", str(path))

    return write


def test_inform_iso3_not_listed_is_no_data(inform_file):
    inform_file([["IND", 5.4, 4.1, 3.2, 0.12]])
    _assert_no_data(vs.get_inform_vulnerability_context("ATA"))


def test_inform_no_iso3_is_no_data():
    _assert_no_data(vs.get_inform_vulnerability_context(None))


def test_inform_invalid_cell_is_no_data(inform_file):
    inform_file([["IND", "x", 4.1, 3.2, 0.12]])
    _assert_no_data(vs.get_inform_vulnerability_context("IND"))


def test_inform_file_not_installed_raises(monkeypatch, tmp_path):
    """The file is a required local install, not a per-place data gap:
    every AOI worldwide would report the same "unavailable"."""
    monkeypatch.setattr(vs, "INFORM_RISK_FILE_PATH", str(tmp_path / "absent.xlsx"))
    with pytest.raises(FileNotFoundError):
        vs.get_inform_vulnerability_context("IND")


def test_inform_header_change_raises(inform_file):
    inform_file([["IND", 5.4, 4.1, 3.2]], headers=HEADERS[:4])
    with pytest.raises(KeyError):
        vs.get_inform_vulnerability_context("IND")


def test_inform_wrong_sheet_name_raises(inform_file, monkeypatch):
    inform_file([["IND", 5.4, 4.1, 3.2, 0.12]])
    monkeypatch.setattr(vs, "INFORM_RISK_SHEET_NAME", "INFORM Risk 2027 (a-z)")
    with pytest.raises(KeyError):
        vs.get_inform_vulnerability_context("IND")


# ── C18: the scheduler checks what run_pipeline actually signals ────────

@pytest.fixture
def api_module():
    import api
    return api


def _run_scheduler(api_module, monkeypatch, outcome):
    import pipeline

    def fake_run_pipeline(**kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(api_module, "WATCHED_AOIS", [
        {"label": "dharavi", "west": 72.836, "south": 19.037,
         "east": 72.862, "north": 19.060},
    ])
    return api_module.refresh_all_watched_aois()


def test_in_band_failure_is_not_reported_as_refreshed(api_module, monkeypatch, capsys):
    """The ledger case: run_pipeline returns {"status": "failed"} and the
    scheduler used to print "refreshed OK"."""
    outcomes = _run_scheduler(api_module, monkeypatch,
                              {"status": "failed", "error": "No tiles generated"})
    assert "refreshed OK" not in capsys.readouterr().out
    assert outcomes == [{"label": "dharavi", "outcome": "failed",
                         "error": "No tiles generated"}]


def test_raised_failure_records_its_exception_class(api_module, monkeypatch):
    outcomes = _run_scheduler(api_module, monkeypatch, ee.EEException("quota"))
    assert outcomes[0]["outcome"] == "exception"
    assert outcomes[0]["exception_class"] == "EEException"


def test_success_is_reported_as_complete(api_module, monkeypatch, capsys):
    outcomes = _run_scheduler(api_module, monkeypatch,
                              {"status": "complete", "run_id": "dharavi_20260101_000000"})
    assert outcomes[0]["outcome"] == "complete"
    assert "refreshed OK" in capsys.readouterr().out


def test_analyze_500_names_the_exception_class(api_module, monkeypatch):
    """The API boundary's broad catch is a right one (it turns any failure
    into a 500), so it records the class rather than only str(e)."""
    from fastapi.testclient import TestClient
    import pipeline

    def boom(**kwargs):
        raise ee.EEException("quota")

    monkeypatch.setattr(pipeline, "run_pipeline", boom)
    client = TestClient(api_module.app,
                        headers={api_module.API_KEY_HEADER_NAME: api_module.API_KEY})
    r = client.post("/api/analyze", json={**BBOX, "aoi_label": "dharavi"})
    assert r.status_code == 500
    assert "EEException" in r.json()["detail"]
