"""
Round 3, Phase 3: MMFlood AOI footprints from metadata only.

MMFlood (Montello et al. 2022, Zenodo 6534637, CC BY 4.0) ships one 11 GB zip. We read
the zip's central directory (zip_index.json) and, per tile, only the GeoTIFF *header*
of the DEM tile: the first compressed bytes are inflated (Deflate64) until the TIFF
tags that give size, pixel scale and tie point are complete. Neither the flood mask nor
the SAR tile is read. Output: one footprint per MMFlood AOI (tile group EMSRxxx-k).

    python -m experiments.flood_round3.mmflood_meta     # -> ~/.cache/.../mmflood_meta/footprints.json
"""
from __future__ import annotations

import json
import os
import struct
import time
import urllib.request

URL = "https://zenodo.org/records/6534637/files/mmflood.zip"
META = os.path.expanduser("~/.cache/geowatch/flood_round3/mmflood_meta")
HEAD_BYTES = 16384          # compressed bytes read per tile; grown if the tags are not complete

# TIFF tags we need
T_W, T_H, T_SCALE, T_TIE, T_EPSG = 256, 257, 33550, 33922, 34735
TYPES = {1: ("B", 1), 2: ("c", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8), 12: ("d", 8), 16: ("Q", 8)}


def _rng(a, b):
    req = urllib.request.Request(URL, headers={"Range": f"bytes={a}-{b}", "User-Agent": "geowatch-research"})
    for k in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:
            time.sleep(5 * (k + 1))
    raise RuntimeError("range request failed")


def parse_tiff_header(buf: bytes) -> dict | None:
    """Width, height, pixel scale, tie point and EPSG (GeoKey 2048/3072) from a little- or
    big-endian classic TIFF prefix. None if the first IFD is not fully inside `buf`."""
    if len(buf) < 8:
        return None
    e = "<" if buf[:2] == b"II" else ">"
    if struct.unpack(e + "H", buf[2:4])[0] != 42:
        return None
    off = struct.unpack(e + "I", buf[4:8])[0]
    if off + 2 > len(buf):
        return None
    n = struct.unpack(e + "H", buf[off:off + 2])[0]
    if off + 2 + 12 * n > len(buf):
        return None
    tags = {}
    for i in range(n):
        p = off + 2 + 12 * i
        tag, typ, cnt = struct.unpack(e + "HHI", buf[p:p + 8])
        if tag not in (T_W, T_H, T_SCALE, T_TIE, T_EPSG) or typ not in TYPES:
            continue
        fmt, size = TYPES[typ]
        total = size * cnt
        if total <= 4:
            raw = buf[p + 8:p + 8 + total]
        else:
            vo = struct.unpack(e + "I", buf[p + 8:p + 12])[0]
            if vo + total > len(buf):
                return None
            raw = buf[vo:vo + total]
        ch = fmt[0] if fmt != "II" else "I"
        k = cnt if fmt != "II" else 2 * cnt
        tags[tag] = struct.unpack(e + ch * k, raw)
    if not all(t in tags for t in (T_W, T_H, T_SCALE, T_TIE)):
        return None
    epsg = None
    g = tags.get(T_EPSG)
    if g:
        for j in range(4, len(g) - 3, 4):
            if g[j] in (2048, 3072) and g[j + 1] == 0:
                epsg = g[j + 3]
    sx, sy = tags[T_SCALE][0], tags[T_SCALE][1]
    tx, ty = tags[T_TIE][3], tags[T_TIE][4]
    w, h = tags[T_W][0], tags[T_H][0]
    return {"w": w, "h": h, "epsg": epsg, "bounds": [tx, ty - h * sy, tx + w * sx, ty], "res": [sx, sy]}


def tile_header(entry: dict) -> dict | None:
    import inflate64
    import zlib
    h = _rng(entry["off"], entry["off"] + 29)
    nlen, elen = struct.unpack("<HH", h[26:30])
    start = entry["off"] + 30 + nlen + elen
    n = HEAD_BYTES
    while True:
        n = min(n, entry["csize"])
        comp = _rng(start, start + n - 1)
        if entry["comp"] == 9:
            out = inflate64.Inflater().inflate(comp)
        elif entry["comp"] == 8:
            out = zlib.decompressobj(-15).decompress(comp)
        else:
            out = comp
        hd = parse_tiff_header(out)
        if hd or n >= entry["csize"]:
            return hd
        n *= 4


def main():
    idx = json.load(open(os.path.join(META, "zip_index.json")))
    out_p = os.path.join(META, "footprints.json")
    done = json.load(open(out_p)) if os.path.exists(out_p) else {}
    dem = [e for e in idx if e["name"].endswith(".tif") and "/DEM/" in e["name"]]
    for k, e in enumerate(dem):
        tile = os.path.basename(e["name"])[:-4]
        if tile in done:
            continue
        try:
            done[tile] = tile_header(e)
        except Exception as ex:            # recorded, not fatal
            done[tile] = {"error": str(ex)[:200]}
        if k % 50 == 0:
            json.dump(done, open(out_p, "w"))
            print(k, len(dem), tile, done[tile], flush=True)
        time.sleep(0.2)
    json.dump(done, open(out_p, "w"))
    print("tiles", len(done), "errors", sum(1 for v in done.values() if not v or "error" in v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
