"""
C8 / build item 53 — INFORM values are validated at read time.

04_FINDINGS_LEDGER.md C8 [S]: `vulnerability_score` and
`coping_capacity_score` were returned under `"scale": "0-10"` with
`"status": "available"` without any check that they were numeric, non-null
or in range. The `Lack of Reliability (*)` and `% of Missing Indicators`
columns were read and then used for nothing.

The ranges are the file's own. Read from the real INFORM_Risk_2026_v072.xlsx
units row and cell formats at build time:
  VULNERABILITY, LACK OF COPING CAPACITY, Lack of Reliability (*)
      units "(0-10)", number format "0.0"
  % of Missing Indicators
      units "(0-100%)", number format "0%", so it is stored as a 0-1 fraction

Each test writes a small workbook in the real file's layout (blank row 1,
headers in row 2, units in row 3, data from row 4) and points the module at
it. The real file is not modified and not required.

Run from the repo root:  pytest tests/test_inform_validation.py
"""

import math

import openpyxl
import pytest

from configs import vulnerability_constants as K
from ingestion import vulnerability_sources as vs

HEADERS = [K.INFORM_COL_ISO3, K.INFORM_COL_VULNERABILITY,
           K.INFORM_COL_COPING_CAPACITY, K.INFORM_COL_RELIABILITY,
           K.INFORM_COL_PCT_MISSING]
UNITS = ["(a-z)", "(0-10)", "(0-10)", "(0-10)", "(0-100%)"]
GOOD = ["IND", 5.4, 4.1, 3.2, 0.12]


@pytest.fixture
def inform_file(tmp_path, monkeypatch):
    path = tmp_path / "inform.xlsx"

    def write(row, headers=HEADERS):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = K.INFORM_RISK_SHEET_NAME
        ws.append([None] * len(headers))
        ws.append(headers)
        ws.append(UNITS[:len(headers)])
        ws.append(row)
        wb.save(path)
        monkeypatch.setattr(vs, "INFORM_RISK_FILE_PATH", str(path))

    return write


def test_valid_row_is_available(inform_file):
    inform_file(GOOD)
    r = vs.get_inform_vulnerability_context("IND")
    assert r["status"] == "available"
    assert r["dimensions"]["vulnerability"]["raw_score"] == 5.4
    assert r["data_quality"]["lack_of_reliability_score"] == 3.2
    assert r["data_quality"]["pct_missing_indicators"] == 0.12


BAD_CELLS = [
    pytest.param(1, None, id="vulnerability-empty"),
    pytest.param(1, "x", id="vulnerability-text"),
    pytest.param(1, 10.5, id="vulnerability-above-10"),
    pytest.param(1, -0.1, id="vulnerability-negative"),
    pytest.param(1, True, id="vulnerability-bool"),
    pytest.param(2, None, id="coping-empty"),
    pytest.param(2, "5.0", id="coping-numeric-looking-text"),
    pytest.param(2, 11, id="coping-above-10"),
    pytest.param(3, "n/a", id="reliability-text"),
    pytest.param(3, 10.01, id="reliability-above-10"),
    pytest.param(3, None, id="reliability-empty"),
    pytest.param(4, 1.5, id="pct-missing-above-1"),
    pytest.param(4, -0.01, id="pct-missing-negative"),
    pytest.param(4, None, id="pct-missing-empty"),
]


@pytest.mark.parametrize("col,value", BAD_CELLS)
def test_invalid_cell_is_unavailable_not_available(inform_file, col, value):
    row = list(GOOD)
    row[col] = value
    inform_file(row)
    r = vs.get_inform_vulnerability_context("IND")
    assert r["status"] == "unavailable"
    # The reason names the column, so "bad cell" and "file missing" read
    # differently downstream.
    assert HEADERS[col] in r["reason"]


def test_nan_is_invalid():
    assert vs._invalid_inform_value(math.nan, 0.0, 10.0) is not None


def test_missing_quality_column_is_unavailable(inform_file):
    """Without the reliability column there is nothing to qualify the score
    with, so it cannot be served as available."""
    inform_file(GOOD[:4], headers=HEADERS[:4])
    r = vs.get_inform_vulnerability_context("IND")
    assert r["status"] == "unavailable"
    assert K.INFORM_COL_PCT_MISSING in r["reason"]
