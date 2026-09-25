"""The Overpass / Nominatim contact comes from GEOWATCH_CONTACT_EMAIL, never
from source, and a missing value fails loudly -- including through the
retry loops whose `except Exception` would otherwise swallow it."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ingestion import contact

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def no_dotenv(monkeypatch):
    monkeypatch.setattr(contact, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv(contact.ENV_VAR, raising=False)


def test_user_agent_uses_env(no_dotenv, monkeypatch):
    monkeypatch.setenv(contact.ENV_VAR, "someone@example.org")
    assert contact.contact_user_agent() == "GeoWatchCopilot/1.0 (someone@example.org)"


@pytest.mark.parametrize("value", [None, "", "   ", "not-an-email"])
def test_missing_or_bad_value_fails_loudly(no_dotenv, monkeypatch, value):
    if value is not None:
        monkeypatch.setenv(contact.ENV_VAR, value)
    with pytest.raises(contact.ContactEmailUnset, match="GEOWATCH_CONTACT_EMAIL"):
        contact.contact_user_agent()


def test_get_osm_features_raises_instead_of_degrading(no_dotenv, tmp_path, monkeypatch):
    import requests
    from ingestion import osm_dem
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("no request without a contact"))
    with pytest.raises(contact.ContactEmailUnset):
        osm_dem.get_osm_features(72.83, 19.03, 72.84, 19.04, output_dir=str(tmp_path))


def test_get_osm_facilities_raises_instead_of_degrading(no_dotenv, tmp_path, monkeypatch):
    import requests
    from ingestion import exposure_sources
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("no request without a contact"))
    with pytest.raises(contact.ContactEmailUnset):
        exposure_sources.get_osm_facilities(72.83, 19.03, 72.84, 19.04, output_dir=str(tmp_path))


def test_no_hardcoded_address_left_in_python_sources():
    needle = "kanveermadan" + "@"          # split so this file does not match itself
    hits = [str(p) for p in REPO.rglob("*.py")
            if not {"geowatch-env", "venv", "node_modules"} & set(p.parts)
            and needle in p.read_text(errors="ignore")]
    assert hits == []


def test_env_example_documents_the_variable():
    assert "GEOWATCH_CONTACT_EMAIL=" in (REPO / ".env.example").read_text()
