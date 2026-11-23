"""Small self-contained, publication-sized SVG maps with lossless raster panels."""
import base64
import html
from pathlib import Path
import struct
import zlib

import numpy as np

# Colours are shared across the scientific states and independent masks.
PALETTE = np.array([[228,231,234],[242,224,188],[8,107,126],[156,137,163],[218,109,34]],dtype=np.uint8)


def _png_rgb(rgb):
    h,w,_ = rgb.shape
    def chunk(tag, data):
        return struct.pack(">I",len(data))+tag+data+struct.pack(">I",zlib.crc32(tag+data)&0xffffffff)
    body = b"".join(b"\0"+row.tobytes() for row in rgb)
    png = (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0))
           +chunk(b"IDAT",zlib.compress(body))+chunk(b"IEND",b""))
    return "data:image/png;base64,"+base64.b64encode(png).decode("ascii")


def write_map(path, title, state, base, urban, truth, grid, ref_name, *, baseline_title='Intensity only'):
    e = lambda s: html.escape(str(s),quote=True)
    origin = grid["transform"]
    h,w = state.shape
    panel = 257
    factor = min(panel/w,panel/h)
    width,height = w*factor,h*factor
    independent = np.zeros(state.shape,dtype=np.uint8)
    if truth is not None:
        independent[truth==1]=2
        independent[truth==0]=1
    new = np.where(urban,3,0).astype(np.uint8)
    new[urban.astype(bool) & (base==2)] = 2
    new[urban.astype(bool) & (state==2) & (base!=2)] = 4
    items = [(baseline_title,base),("Urban detector",state),("Urban additions",new),(ref_name,independent)]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1120 435" width="1120" height="435">',
           '<style>text{font:14px sans-serif;fill:#202d36}.title{font:bold 22px sans-serif}.small{font-size:12px}</style>',
           '<rect width="100%" height="100%" fill="white"/>',
           f'<text x="20" y="30" class="title">{e(title)}</text>']
    for i,(label,data) in enumerate(items):
        x = 20+i*274
        svg.append(f'<text x="{x}" y="57">{e(label)}</text>')
        svg.append(f'<image x="{x}" y="70" width="{width}" height="{height}" image-rendering="pixelated" xlink:href="{_png_rgb(PALETTE[data.astype(int)])}"/>')
    for i,(label,colour) in enumerate((("Unobserved / excluded",0),("Confident dry",1),("Confident flood",2),
                                        ("Ambiguous",3),("Additional urban flood candidate",4))):
        x = [20,215,360,517,655][i]
        rgb = PALETTE[colour]
        svg.append(f'<rect x="{x}" y="342" width="14" height="14" fill="rgb({rgb[0]},{rgb[1]},{rgb[2]})"/>')
        svg.append(f'<text x="{x+20}" y="354">{e(label)}</text>')
    svg.extend([f'<text x="20" y="380" class="small">Urban additions panel: grey outside urban mask, purple urban background, teal baseline wet, orange newly mapped wet. North is up.</text>',
                f'<text x="20" y="404" class="small">{e(grid["crs"])} · upper-left grid edge {origin[2]:.0f} m E, {origin[5]:.0f} m N · {w*30:,} m × {h*30:,} m · 30 m cells</text>',
                '</svg>'])
    Path(path).write_text("\n".join(svg)+"\n")
