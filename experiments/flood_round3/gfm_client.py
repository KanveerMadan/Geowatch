"""
Round 3: Global Flood Monitoring (GFM, Copernicus EMS / EODC) API client.

Credentials: ~/.config/geowatch/gfm.json = {"email": "...", "password": "..."} (chmod 600). The owner types them;
they are never printed, logged or committed. tools/secrets_scan.py blocks the file name and its values. The bearer
token lives only in memory.

    python -m experiments.flood_round3.gfm_client check     # login test; prints OK / FAILED and the token lifetime
"""
from __future__ import annotations

import json
import os
import stat
import sys

API = "https://api.gfm.eodc.eu/v2"
CREDS = os.path.expanduser("~/.config/geowatch/gfm.json")


def _creds():
    if not os.path.exists(CREDS):
        raise FileNotFoundError("GFM credentials file missing (~/.config/geowatch/gfm.json)")
    if stat.S_IMODE(os.stat(CREDS).st_mode) & 0o077:
        raise PermissionError("GFM credentials file must be chmod 600")
    c = json.load(open(CREDS))
    if not c.get("email") or not c.get("password"):
        raise ValueError("GFM credentials file needs 'email' and 'password'")
    return c


class GFM:
    def __init__(self, timeout=120):
        import requests
        self.s = requests.Session()
        self.timeout = timeout
        c = _creds()
        r = self.s.post(f"{API}/auth/login", json={"email": c["email"], "password": c["password"]}, timeout=timeout)
        del c
        if r.status_code != 200:
            raise RuntimeError(f"GFM login failed: HTTP {r.status_code}")
        j = r.json()
        self.user_id = j.get("client_id") or j.get("user_id")
        self.expires_in = j.get("expires_in")
        self.s.headers["Authorization"] = f"Bearer {j['access_token']}"

    def get(self, path, **kw):
        r = self.s.get(f"{API}{path}", timeout=self.timeout, **kw)
        r.raise_for_status()
        return r.json()

    def post(self, path, body):
        r = self.s.post(f"{API}{path}", json=body, timeout=self.timeout)
        r.raise_for_status()
        return r.json()


def check():
    try:
        g = GFM()
        print("GFM OK: token received, lifetime", g.expires_in, "s; user id present:", bool(g.user_id))
        return 0
    except Exception as e:          # noqa: BLE001  (message never includes the credentials)
        print("GFM FAILED:", type(e).__name__, str(e)[:200])
        return 1


if __name__ == "__main__":
    raise SystemExit({"check": check}[(sys.argv[1:] or ["check"])[0]]())
