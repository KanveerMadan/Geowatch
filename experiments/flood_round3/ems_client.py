"""
Round 3 (R39): Copernicus EMS rapid-mapping activation details that need a login (pre-2022 activations).

The public dashboard API answers 2022+ activations without a login but returns HTTP 403 ("Authentication credentials
were not provided") for most earlier ones. It authenticates by browser session cookie (EU Login), which cannot be
scripted safely, so the owner pastes the session's Cookie header into

    ~/.config/geowatch/ems.json = {"cookie": "<the Cookie request header sent to rapidmapping.emergency.copernicus.eu>"}

(chmod 600). It is never printed, logged or committed. tools/secrets_scan.py blocks the file name and its value.
Only metadata is read: activation, AOI and product records (image times, sensors, reported stats), as select_r3 does.

    python -m experiments.flood_round3.ems_client check      # prints OK / FAILED only
"""
from __future__ import annotations

import json
import os
import stat
import sys

API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code={code}"
CREDS = os.path.expanduser("~/.config/geowatch/ems.json")


def session():
    import requests
    if not os.path.exists(CREDS):
        raise FileNotFoundError("EMS cookie file missing (~/.config/geowatch/ems.json)")
    if stat.S_IMODE(os.stat(CREDS).st_mode) & 0o077:
        raise PermissionError("EMS cookie file must be chmod 600")
    c = json.load(open(CREDS)).get("cookie")
    if not c:
        raise ValueError("EMS cookie file needs a 'cookie' value")
    s = requests.Session()
    s.headers["Cookie"] = c
    return s


def get(s, code):
    r = s.get(API.format(code=code), timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"EMS {code}: HTTP {r.status_code}")
    j = r.json()
    return (j.get("results") or [j])[0]


def check():
    try:
        a = get(session(), "EMSR117")            # 2015 activation: 403 without a login
        prods = [p for x in a.get("aois") or [] for p in x.get("products") or []]
        print("EMS OK: pre-2022 activation readable;", len(a.get("aois") or []), "AOIs,", len(prods), "products")
        return 0
    except Exception as e:          # noqa: BLE001  (messages never include the cookie)
        print("EMS FAILED:", type(e).__name__, str(e)[:160])
        return 1


if __name__ == "__main__":
    raise SystemExit({"check": check}[(sys.argv[1:] or ["check"])[0]]())
