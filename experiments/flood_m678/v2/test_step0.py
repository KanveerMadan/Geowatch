"""Step 0: synthetic checks that DEV code cannot list or read reserved data, and the quarantine holds."""
import importlib
import os

import pytest


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOWATCH_M678V2_ROOT", str(tmp_path))
    import experiments.flood_m678.v2.storage as S
    S = importlib.reload(S)
    S.init()
    yield S
    os.chmod(S.RESERVE, 0o700)           # let pytest clean up


def test_reserve_root_is_sealed_and_unlistable(storage):
    assert storage.reserve_is_sealed()
    if os.geteuid() != 0:
        with pytest.raises(PermissionError):
            os.listdir(storage.RESERVE)


def test_dev_path_refuses_reserve_and_escape(storage):
    assert storage.dev_path("tables", "x.npz").startswith(storage.DEV)
    with pytest.raises(storage.ReserveAccess):
        storage.dev_path("..", "reserve", "x.npz")
    with pytest.raises(storage.ReserveAccess):
        storage.dev_path("..", "..", "elsewhere")


def test_open_reserve_needs_a_verified_run(storage):
    with pytest.raises(storage.ReserveAccess):
        storage.open_reserve(False, "run-1")
    with pytest.raises(storage.ReserveAccess):
        storage.open_reserve(True, "")


def test_quarantine_membership():
    from experiments.flood_m678.v2 import registry as R
    reg = {"v1": {"clusters": ["M7:orsk"], "incidents": ["orsk-2024-04-05", "mendenhall-2014-07-11"]}}
    assert R.is_quarantined("M7:orsk", reg=reg)
    assert R.is_quarantined(incident="mendenhall-2014-07-11", reg=reg)
    assert not R.is_quarantined("M7:midland", "midland-2020-05-19", reg=reg)
