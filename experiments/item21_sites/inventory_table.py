"""
Render experiments/item21_sites/results/imagery_inventory.json as the
measurement A table (Markdown). Inventory only -- no source is chosen.

    python experiments/item21_sites/inventory_table.py
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "results", "imagery_inventory.json")
DST = os.path.join(HERE, "results", "imagery_inventory.md")

HIGH_RES_MAX_M = 2.0   # the "sub-2 m" criterion of the 2026-09-24 site-list check

# What each licence string permits for DIGITISING A DERIVED DATASET (labels).
LICENCE_TERMS = {
    "CC-BY 4.0": "derivatives allowed, incl. commercial; attribution required",
    "CC BY-SA 4.0": "derivatives allowed; attribution; derived labels must be released CC BY-SA",
    "CC BY-NC 4.0": "derivatives allowed, NON-COMMERCIAL only; attribution",
    "CC-BY-NC-4.0": "derivatives allowed, NON-COMMERCIAL only; attribution",
}


def time_cell(sc: dict, lon: float) -> str:
    t0, t1 = sc.get("acquisition_start_utc"), sc.get("acquisition_end_utc")
    if not t0:
        return f"{sc.get('acquisition', '?')}; **time not published**"
    t0c = t0.replace("T", " ").replace(".000Z", "Z")
    t1c = (t1 or "").replace("T", " ").replace(".000Z", "Z")
    hhmmss = t0c[11:19]
    window = t0c[:19] + ("" if not t1c or t1c[:19] == t0c[:19] else f" → {t1c[11:19]}") + " UTC"
    if hhmmss.endswith(":00:00"):
        return window + " — *on the hour: date-only or approximate*"
    h, m, s = (int(x) for x in hhmmss.split(":"))
    solar = (h + m / 60 + s / 3600 + lon / 15) % 24
    return window + f" (≈ {int(solar):02d}:{int(solar % 1 * 60):02d} local solar)"


def licence_cell(sc: dict) -> str:
    lic = sc.get("licence") or "?"
    note = LICENCE_TERMS.get(lic, "")
    extra = ""
    if sc.get("licence_acquisition_collection") and sc["licence_acquisition_collection"] != lic:
        extra = f"; **acquisition collection says `{sc['licence_acquisition_collection']}`**"
    return f"`{lic}`" + (f" — {note}" if note else "") + extra


def s2_cell(s2: dict) -> str:
    if "clear_scenes_pm30" not in s2:
        return s2.get("status", "?")
    g = s2["nearest_clear_gap_days"]
    return (f"{s2['clear_scenes_pm30']} / {s2['clear_scenes_pm60']} / "
            f"{s2['clear_scenes_pm90']}; nearest {g} d" if g is not None
            else "0 / 0 / 0; none within 90 d")


def main():
    d = json.load(open(SRC))
    lines = [
        "# Item 21 measurement A — high-resolution imagery inventory",
        "",
        f"Generated from `imagery_inventory.json` ({d['generated_utc']}). "
        "**Inventory only: no source is chosen here.**",
        "",
        "- **Catalogues:** OpenAerialMap (bbox query), Maxar Open Data STAC "
        f"({d['maxar_events_scanned']} events scanned), and the source recorded in "
        "`05_BUILD_MANUAL.md` item 21 where it is in neither (Cape Town city "
        "imagery, Rio IPP mosaic).",
        f"- **High resolution** = ≤ {HIGH_RES_MAX_M:g} m (the sub-2 m criterion of "
        "the 2026-09-24 site-list check). Coarser catalogue entries are dropped "
        "and counted.",
        "- **Time:** the catalogue's own acquisition start (→ end) in UTC. "
        "OpenAerialMap times that fall exactly on the hour are usually a date "
        "entered at local midnight (Lima 05:00Z = 00:00 local) and are flagged. "
        "Local solar time = UTC + longitude/15, for shadow geometry.",
        "- **Sentinel-2 L2A:** `COPERNICUS/S2_SR_HARMONIZED` scenes with scene "
        "`CLOUDY_PIXEL_PERCENTAGE` < 20 at the centroid of the scene/site "
        "overlap, within ±30 / 60 / 90 days of the acquisition date, and the "
        "nearest such scene. Scene-level, not per-pixel.",
        "- **Licence:** as the catalogue states it; the right-hand note is what "
        "that licence permits for digitising a derived label dataset.",
        "",
    ]
    for site, v in d["sites"].items():
        bbox = d["search_bboxes"][site]
        lon = (bbox[0] + bbox[2]) / 2
        scenes = [s for s in v["scenes"]
                  if s.get("resolution_m") is None or s["resolution_m"] <= HIGH_RES_MAX_M]
        dropped = len(v["scenes"]) - len(scenes)
        scenes.sort(key=lambda s: (s.get("acquisition_start_utc") or s.get("acquisition") or ""))
        lines += [f"## {site.replace('_', ' ').title()} — {v['role']}", "",
                  f"Search window {bbox}. {len(scenes)} candidate(s)"
                  + (f"; {dropped} coarser than {HIGH_RES_MAX_M:g} m dropped." if dropped else "."),
                  "",
                  "| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |",
                  "|---|---|---|---:|---|---|"]
        for s in scenes:
            src = s["catalogue"] + (f" · {s['event']}" if s.get("event") else "")
            name = (s.get("title") or "") + (f" `{s['id']}`" if s.get("id") else "")
            if s["catalogue"] == "Maxar Open Data" and s.get("sun_elevation_deg") is not None:
                name += f" (sun el. {s['sun_elevation_deg']}°, off-nadir {s['off_nadir_deg']}°)"
            if "cajamarquilla" in name.lower():
                name += " — **site list says exclude: no licence**"
            res = "?" if s.get("resolution_m") is None else f"{s['resolution_m']:.3g}"
            lines.append(f"| {src} | {name} | {time_cell(s, lon)} | {res} | "
                         f"{licence_cell(s)} | {s2_cell(s['s2'])} |")
        lines.append("")
    with open(DST, "w") as fh:
        fh.write("\n".join(lines))
    print(DST)


if __name__ == "__main__":
    main()
