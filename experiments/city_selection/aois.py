"""
AOIs for the annotation-expansion selection study.

EVERY CITY GETS THE SAME 5 x 5 km (25 km^2) BOX, including the existing 11.
The existing AOIs are not the same size as each other (6.8 km^2 for Kigali,
123.2 for HCMC), so using them as-is would make the morphological distance
matrix partly a measure of AOI size. Each existing city's box is therefore
centred on the centroid of its real AOI, taken from that run's result.json.

Candidate centres target the dense / informal fabric the project is about,
not the city centroid — Cité Soleil rather than downtown Port-au-Prince,
Orangi rather than central Karachi. A 25 km^2 box at a CBD would measure a
different city than the one the classifier struggles with.

Tiers are the OpenAerialMap validation-imagery tiers from the audit recorded
in 08_STATE.md: A = dedicated <=15 cm survey, B = 30 cm-1 m satellite mosaic
(likely CC BY-NC under an OSM-scoped waiver, so restricted for training until
verified per scene), none = no usable OAM coverage.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

AOI_KM = 5.0                      # 5 x 5 km = 25 km^2
HALF_DEG_LAT = (AOI_KM / 2) / 111.0

# name -> (lon, lat, tier, region, note)
CANDIDATES = {
    # --- OAM Tier A: dedicated <=15 cm imagery ---
    "maputo":         (32.560, -25.940, "A", "Africa-E",  "Chamanculo"),
    "kathmandu":      (85.320,  27.710, "A", "S-Asia",    "hillside/valley"),
    "kinshasa":       (15.300,  -4.350, "A", "Africa-C",  "equatorial"),
    "port_au_prince": (-72.340, 18.580, "A", "Caribbean", "Cité Soleil, hillside nearby"),
    "medellin":       (-75.620,  6.260, "A", "LatAm",     "Comuna 13, hillside"),
    "freetown":       (-13.240,  8.490, "A", "Africa-W",  "Kroo Bay, ~3000mm/yr"),
    "dar_es_salaam":  (39.230,  -6.800, "A", "Africa-E",  "Manzese"),
    "monrovia":       (-10.800,  6.330, "A", "Africa-W",  "West Point, ~4600mm/yr"),
    "manila":         (120.970, 14.620, "A", "SE-Asia",   "Tondo"),
    "lima":           (-76.990, -12.010, "A", "LatAm",    "SJL, coastal stratus"),
    "bangkok":        (100.570, 13.710, "A", "SE-Asia",   "Khlong Toei"),
    "niteroi":        (-43.100, -22.890, "A", "LatAm",    "hillside"),

    # --- OAM Tier B: 30 cm-1 m mosaic, licence-restricted ---
    "caracas":        (-66.810, 10.480, "B", "LatAm",     "Petare, hillside"),
    "antananarivo":   (47.520, -18.910, "B", "Africa-E",  "hillside"),
    "mexico_city":    (-99.060, 19.360, "B", "LatAm",     "Iztapalapa"),
    "bogota":         (-74.160,  4.530, "B", "LatAm",     "Ciudad Bolívar, hillside"),

    # --- No OAM, but fill regional gaps ---
    "karachi":        (67.000,  24.940, "none", "S-Asia", "Orangi"),
    "delhi":          (77.210,  28.630, "none", "S-Asia", ""),
    "kolkata":        (88.370,  22.560, "none", "S-Asia", ""),
    "chittagong":     (91.800,  22.340, "none", "S-Asia", ""),
    "cairo":          (31.280,  30.040, "none", "MENA",   "Manshiyat Naser"),
    "casablanca":     (-7.580,  33.580, "none", "MENA",   ""),
    "amman":          (35.930,  31.950, "none", "MENA",   ""),
    "lusaka":         (28.300, -15.400, "none", "Africa-S", ""),
    "harare":         (31.000, -17.870, "none", "Africa-S", "Mbare"),
    "ouagadougou":    (-1.530,  12.360, "none", "Africa-W", "arid"),
    "addis_ababa":    (38.740,   9.020, "none", "Africa-E", "highland"),
    "luanda":         (13.250,  -8.850, "none", "Africa-C", ""),
}

EXISTING_RUNS = {
    "dharavi":   "dharavi_20260702_163012",
    "nairobi":   "nairobi_20260702_164731",
    "jakarta":   "jakarta_20260702_163609",
    "hcmc":      "hcmc_20260702_163714",
    "kigali":    "kigali_20260702_163814",
    "accra":     "accra_20260702_163854",
    "dhaka":     "dhaka_20260702_163939",
    "lagos":     "lagos_20260702_165430",
    "capetown":  "capetown_20260702_164022",
    "guatemala": "guatemala_20260702_164206",
    "nusantara": "nusantara_20260702_165811",
}


def existing_centres() -> dict:
    """Centroid of each existing city's real AOI, from its result.json."""
    out = {}
    for city, run in EXISTING_RUNS.items():
        p = REPO_ROOT / "data" / "pipeline_runs" / run / "result.json"
        aoi = json.loads(p.read_text())["aoi"]
        out[city] = ((aoi["west"] + aoi["east"]) / 2.0,
                     (aoi["south"] + aoi["north"]) / 2.0)
    return out


def bbox(lon: float, lat: float) -> tuple:
    """(west, south, east, north) for a 5 x 5 km box centred on lon/lat."""
    import math
    half_lon = (AOI_KM / 2) / (111.0 * max(math.cos(math.radians(lat)), 1e-6))
    return (lon - half_lon, lat - HALF_DEG_LAT, lon + half_lon, lat + HALF_DEG_LAT)


def all_sites() -> dict:
    """name -> dict(lon, lat, bbox, tier, region, note, group)."""
    sites = {}
    for name, (lon, lat, tier, region, note) in CANDIDATES.items():
        sites[name] = {"lon": lon, "lat": lat, "bbox": bbox(lon, lat), "tier": tier,
                       "region": region, "note": note, "group": "candidate"}
    for name, (lon, lat) in existing_centres().items():
        sites[name] = {"lon": lon, "lat": lat, "bbox": bbox(lon, lat), "tier": "existing",
                       "region": "existing", "note": "", "group": "existing"}
    return sites


if __name__ == "__main__":
    s = all_sites()
    print(f"{len(s)} sites: {sum(1 for v in s.values() if v['group'] == 'candidate')} "
          f"candidates + {sum(1 for v in s.values() if v['group'] == 'existing')} existing")
    for n, v in s.items():
        w, so, e, no = v["bbox"]
        print(f"  {n:<16} {v['tier']:<8} {v['region']:<10} "
              f"[{w:.3f},{so:.3f},{e:.3f},{no:.3f}]")
