"""Pytest launcher for an isolated QGIS editing session on a private practice copy."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tools.labelling.geowatch_item21.storage import Log, timer


def test_timer_preserves_existing_keys_and_accumulates_explicit_sessions(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"labeller": None, "unknown": 23, "timing": {"minutes": 5, "note": "prior measurement"}}))
    start = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        timer(tmp_path, at=start)
    timer(tmp_path, "Labeller", start)
    timer(tmp_path, at=start+timedelta(minutes=4))
    timer(tmp_path, at=start+timedelta(minutes=10))
    timer(tmp_path, at=start+timedelta(minutes=11))
    meta = json.loads(path.read_text())
    assert meta["unknown"] == 23 and meta["labeller"] == "Labeller"
    assert meta["timing"]["note"] == "prior measurement"
    assert meta["timing"]["minutes"] == 10
    assert len(meta["timing"]["item21_sessions"]) == 2


def test_rejections_are_tile_specific_and_reversible(tmp_path):
    log = Log(tmp_path / "profile" / "review.sqlite")
    assert not log.rejected("tileA") and not log.path.exists()
    log.write("tileA", "a", "reject")
    assert log.rejected("tileA") == {"a"} and not log.rejected("tileB")
    log.write("tileA", "a", "reopen")
    assert not log.rejected("tileA")


def test_qgis_plugin_on_private_fixture(tmp_path):
    python = os.environ.get("GEOWATCH_QGIS_PYTHON")
    if not python:
        app_python = Path("/Applications/QGIS.app/Contents/MacOS/python")
        if not app_python.exists():
            pytest.skip("Set GEOWATCH_QGIS_PYTHON to run the desktop integration test.")
        python = str(app_python)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QGIS_CUSTOM_CONFIG_PATH=str(tmp_path/"profile"),
               XDG_CACHE_HOME=str(tmp_path/"cache"), PYTHONDONTWRITEBYTECODE="1", GDAL_PAM_ENABLED="NO")
    script = Path(__file__).with_name("qgis_review_session.py")
    subprocess.run([python, str(script), str(tmp_path)], env=env, check=True, timeout=120)
