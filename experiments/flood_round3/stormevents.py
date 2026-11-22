"""
Round 3, flash floods: NOAA NCEI Storm Events (public domain) as a metadata event list for the Sentinel-1
route (RESERVE_CRITERIA_R3 §8, FLASH_SE_DESIGN.md). Nothing here reads a label.

    python -m experiments.flood_round3.stormevents episodes        # details CSVs -> results/se_flash_episodes.json
    python -m experiments.flood_round3.stormevents screen [dev|reserve]   # driver, timing, baselines -> results/se_flash_candidates.json

Episode = one NWS episode (EPISODE_ID) with Flash Flood events whose summed direct property damage is
>= $1 M (the analogue of EMS's reported affected area). Its point and date are those of the episode's
highest-damage Flash Flood event (ties: earliest begin time). Split: DEV before 2022-01-01, reserve after.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/stormevents")
MIN_DAMAGE = 1e6
RESERVE_FROM = "2022-01-01"
PROX_KM = 20.0
SEARCH_KM = 20.0
MAX_LAG_FLASH = 2


def _dmg(s) -> float:
    s = str(s).strip().upper()
    if s in ("", "NAN"):
        return 0.0
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}
    try:
        return float(s[:-1] or 0) * mult[s[-1]] if s[-1] in mult else float(s)
    except ValueError:
        return 0.0


def episodes():
    import pandas as pd
    cols = ["EPISODE_ID", "EVENT_ID", "EVENT_TYPE", "BEGIN_DATE_TIME", "BEGIN_LAT", "BEGIN_LON", "DAMAGE_PROPERTY",
            "DEATHS_DIRECT", "FLOOD_CAUSE", "STATE", "CZ_TIMEZONE"]
    fr = []
    for f in sorted(glob.glob(os.path.join(CACHE, "StormEvents_details-ftp_v1.0_d20*.csv.gz"))):
        if int(os.path.basename(f).split("_v1.0_d")[1][:4]) < 2015:
            continue
        d = pd.read_csv(f, usecols=cols, low_memory=False)
        fr.append(d[(d.EVENT_TYPE == "Flash Flood") & d.BEGIN_LAT.notna() & d.BEGIN_LON.notna()])
    d = pd.concat(fr)
    d["dmg"] = d.DAMAGE_PROPERTY.map(_dmg)
    d["t"] = pd.to_datetime(d.BEGIN_DATE_TIME, format="%d-%b-%y %H:%M:%S")
    out = []
    for ep, g in d.groupby("EPISODE_ID"):
        if g.dmg.sum() < MIN_DAMAGE:
            continue
        top = g.sort_values(["dmg", "t"], ascending=[False, True]).iloc[0]
        day = top.t.date().isoformat()          # local standard time, as NWS records it
        out.append({"episode": int(ep), "event_id": int(top.EVENT_ID), "date": day, "lat": float(top.BEGIN_LAT),
                    "lon": float(top.BEGIN_LON), "state": str(top.STATE), "damage_usd": float(g.dmg.sum()),
                    "deaths": int(g.DEATHS_DIRECT.sum()), "cause": str(top.FLOOD_CAUSE), "n_events": int(len(g)),
                    "split": "reserve" if day >= RESERVE_FROM else "dev"})
    out.sort(key=lambda r: (r["date"], r["episode"]))
    json.dump(out, open(os.path.join(OUT, "se_flash_episodes.json"), "w"), indent=1)
    print(len(out), "episodes;", sum(r["split"] == "dev" for r in out), "dev", flush=True)
    return 0


def _r311_boxes():
    from experiments.flood_round3 import rain311 as R3
    return [c["bbox"] for c in R3.CITIES.values()]


def screen(split="dev"):
    import numpy as np
    from experiments.flood_round3 import diagnose_ee as D
    from experiments.flood_round3 import select_r3 as S
    ee = D._init()
    eps = [e for e in json.load(open(os.path.join(OUT, "se_flash_episodes.json"))) if e["split"] == split]
    pts = S._used_points()
    cities = _r311_boxes()
    p = os.path.join(OUT, "se_flash_candidates.json")
    res = json.load(open(p)) if os.path.exists(p) else {"candidates": [], "refused": []}
    done = {r["episode"] for r in res["candidates"] + res["refused"]}
    taken = [(r["lon"], r["lat"], r["date"]) for r in res["candidates"]]
    for e in eps:
        if e["episode"] in done:
            continue

        def refuse(why, **kw):
            res["refused"].append({"episode": e["episode"], "date": e["date"], "split": split, "why": why, **kw})
        pt = (e["lon"], e["lat"])
        d0 = dt.date.fromisoformat(e["date"])
        if any(S._hav(pt, q[:2]) <= PROX_KM for q in pts):
            refuse("within 20 km of a burned unit")
        elif any(b[0] - 0.25 <= pt[0] <= b[2] + 0.25 and b[1] - 0.2 <= pt[1] <= b[3] + 0.2 for b in cities):
            refuse("inside a 311 city (+ ~20 km)")
        elif any(S._hav(pt, q[:2]) <= PROX_KM and abs((d0 - dt.date.fromisoformat(q[2])).days) <= 30 for q in taken):
            refuse("same place and month as an earlier candidate")
        else:
            box = S._box(e["lon"], e["lat"], SEARCH_KM)
            cp = os.path.join(CACHE, f"imerg_{e['episode']}.json")
            if not os.path.exists(cp):
                mean, _ = D.rain_series(ee, box, e["date"])
                json.dump(mean, open(cp, "w"))
            s = json.load(open(cp))
            days = sorted(s)
            v = np.array([s[k] or 0.0 for k in days])
            k3 = np.convolve(v, np.ones(3), mode="same")
            near = [j for j, k in enumerate(days) if -2 <= (dt.date.fromisoformat(k) - d0).days <= 1]
            i = near[int(np.argmax(k3[near]))]
            rain3, peak = float(k3[i]), dt.date.fromisoformat(days[i])
            if rain3 < 20:
                refuse("driver check failed (IMERG 3-day < 20 mm)", rain_3day_mm=round(rain3, 1))
            else:
                win = S.s1_passes(ee, e["lon"], e["lat"], (peak - dt.timedelta(days=1)).isoformat(),
                                  (peak + dt.timedelta(days=MAX_LAG_FLASH + 1)).isoformat())
                if not win:
                    refuse("no Sentinel-1 pass in [peak - 1 d, peak + 2 d]", peak=peak.isoformat())
                else:
                    t0, orbit = win[0]
                    t0d = dt.date.fromisoformat(t0)
                    nb, yr = 0, 0
                    for yr in (0, 1):
                        b0 = (t0d - dt.timedelta(days=60 + 365 * yr)).isoformat()
                        b1 = (t0d - dt.timedelta(days=5 + 365 * yr)).isoformat()
                        nb = sum(1 for _, o in S.s1_passes(ee, e["lon"], e["lat"], b0, b1) if o == orbit)
                        if nb >= 2:
                            break
                    if nb < 2:
                        refuse("fewer than 2 same-orbit baseline passes", t0=t0)
                    else:
                        unit = f"r3se_{e['episode']}"
                        res["candidates"].append({
                            "unit": unit, "episode": e["episode"], "tags": ["flash_flood"], "event": e["date"],
                            "date": e["date"], "lat": e["lat"], "lon": e["lon"], "peak_day": peak.isoformat(),
                            "rain_3day_mm": round(rain3, 1), "image": t0, "orbit": orbit, "lag_days": (t0d - peak).days,
                            "baseline_passes": nb, "baseline_year_before": yr == 1, "search_point": [e["lat"], e["lon"]],
                            "bbox_at_search_point": [round(x, 6) for x in box], "damage_usd": e["damage_usd"],
                            "split": split, "cluster": f"se_{e['episode']}",
                            "source": "NOAA Storm Events episode; v3 Sentinel-1 label"})
                        taken.append((e["lon"], e["lat"], e["date"]))
                        print(unit, e["date"], round(rain3, 1), t0, flush=True)
        json.dump(res, open(p, "w"), indent=1)
    c = [r for r in res["candidates"] if r["split"] == split]
    print(split, len(c), "candidates;", sum(r["split"] == split for r in res["refused"]), "refused", flush=True)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "episodes":
        return episodes()
    return screen(a[1] if len(a) > 1 else "dev")


if __name__ == "__main__":
    raise SystemExit(main())
