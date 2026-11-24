"""Read and verify the shipped 30 m development labels one tile at a time."""
import csv
import hashlib
import io
import json
import zipfile
from contextlib import ExitStack
from pathlib import Path

import numpy as np

ROOT = Path(__file__).with_name('floodspeed_results')
OPTICAL_GROUPS = {'paired_development', 'paired_research_diagnostic', 'acquisition_only'}


def iter_labels(kind, *, event=None, root=ROOT):
    """Yield (metadata, four-state array). An explicit kind keeps observation targets distinct."""
    if kind != 'peak' and kind not in OPTICAL_GROUPS:
        raise ValueError('Unknown label collection')
    folder = Path(root) / ('peak' if kind == 'peak' else 'optical')
    with ExitStack() as stack:
        manifest = stack.enter_context((folder / 'tiles.csv').open())
        archives = {}
        for row in csv.DictReader(manifest):
            if event is not None and event != row['event']:
                continue
            if kind == 'peak':
                archive = row['archive']
                if archive not in archives:
                    archives[archive] = stack.enter_context(zipfile.ZipFile(folder / archive))
                data = archives[archive].read(row['file'])
            else:
                if row['use'] != kind:
                    continue
                data = (folder / row['file']).read_bytes()
            if hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError(f"Checksum mismatch for {row['file']}")
            with np.load(io.BytesIO(data), allow_pickle=False) as tile:
                meta = json.loads(tile['meta'].item())
                state = tile['state']
                if (meta['role'] != 'dev' or int(meta['event'][:4]) >= 2022
                    or state.shape != tuple(meta['grid']['shape']) or state.dtype != np.uint8
                    or np.any(state > 3) or not np.array_equal(tile['flooded'], state == 2)
                    or not np.array_equal(tile['valid'], (state == 1) | (state == 2))):
                    raise ValueError(f"Invalid development reference {row['file']}")
                yield meta, state
