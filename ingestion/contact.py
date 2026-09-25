"""
Contact address for the HTTP User-Agent sent to Nominatim / Overpass.

Their usage policies require a real contact, so it cannot be dropped -- but
it is a personal address and does not belong in a public repository. It is
read from GEOWATCH_CONTACT_EMAIL (environment or .env) at CALL time, and a
missing value fails loudly rather than sending an anonymous request.

History: until 2026-09-25 the address was hardcoded in
ingestion/exposure_sources.py and ingestion/osm_dem.py. It remains in git
history by decision (history is not rewritten; see CONTRIBUTING.md).
"""

import os

from dotenv import load_dotenv

ENV_VAR = "GEOWATCH_CONTACT_EMAIL"


class ContactEmailUnset(RuntimeError):
    pass


def contact_user_agent(product: str = "GeoWatchCopilot/1.0") -> str:
    load_dotenv()
    email = os.environ.get(ENV_VAR, "").strip()
    if not email or "@" not in email:
        raise ContactEmailUnset(
            f"{ENV_VAR} is not set (or not an email address). The Overpass and "
            f"Nominatim usage policies require a contact in the User-Agent. Set "
            f"it in the environment or in .env (see .env.example).")
    return f"{product} ({email})"
