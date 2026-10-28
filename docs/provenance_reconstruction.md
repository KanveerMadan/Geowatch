# Provenance Reconstruction (item 62)

> **Historical record. This concerns only the RETIRED checkpoint**
> `models/production/geowatch_production_model.pth` (`08_STATE.md`
> §RETIRED). It is kept short for that reason. Nothing here supports a
> capability claim. The checkpoint's stored LOCO value is not a capability
> number (C43).

**What this recovers.** Auditability, not history. The checkpoint was
trained in Colab, outside version control. This section records how its
training notebook was identified, so a reader can rerun the identification
instead of trusting it.

**Inputs.** The checkpoint (sha256 `f70000c4…6120d`, `ARTIFACT_HASHES.txt:2`,
verified 2026-10-28). The 28 GeoWatch notebooks among the 37 `.ipynb` files
archived at commit `ecfe370` (`git ls-tree -r ecfe370`). `notebooks/archive/`
was deleted from the working tree later (`08_STATE.md`, C42). Everything
below was re-run on 2026-10-28 from those inputs.

## Elimination, step by step

| step | test against the checkpoint | candidates left |
|---|---|---:|
| 0 | all GeoWatch notebooks at `ecfe370` | 28 |
| 1 | **the four config values:** (V1) `CITY_MAP` keys = `training_cities`; (V2) a separation loss between the same two classes the `architecture` string names; (V3) `PROD_VAL_FRACTION = 0.10`, consistent with 141 / 1,413; (V4) 7 categories and `IGNORE_INDEX = 255` = `num_classes`, `ignore_index` | **12** |
| 2 | no `np.load` / `.npy` input. The checkpoint stem is 3-channel, `encoder.conv1.weight` (64, 3, 7, 7) | 10 |
| 3 | all five patch builders present. Only the 5-builder pipeline reproduces the stored class weights (rebuild matches to max \|Δ\| 0.0083, `experiments/band_reflectance/results/patch_rebuild_v2.md`) | 8 |
| 4 | latest notebook saved before the checkpoint was written (file mtimes in `~/Downloads`, the Colab download location) | **1** |

**Result:** `geowatch_water_loco_with_diagnostics (2).ipynb`, saved
2026-07-15 00:40. The checkpoint was written 01:38:13 the same night. The
`~/Downloads` copy and the `ecfe370` copy are byte-identical (sha256
`1438bdcf…0964` both). The production training cell is cell 39 (of 48), and
its final call is `files.download(local_path)`.

**What this is and is not.** The four config values are **necessary, not
sufficient**. They are shared by 12 notebooks. `archive/AUDIT_FINDINGS.md`
§"Training Notebook Search" presents them as a four-way independent match,
which is true but does not single out one file. Step 4 is what singles it
out, and step 4 rests on file timestamps alone. The nearest rival,
`…diagnostics (1).ipynb` (2026-07-14 17:01), has the same save-cell
configuration. Treat the identification as **strongly supported, not proven**.

## What the reconstruction cannot account for

The checkpoint stores `loco_mean_miou = 0.313`, `loco_std_miou = 0.0564`.
**No archived artifact writes those values:**

| source | `loco_mean_miou` / `loco_std_miou` |
|---|---|
| checkpoint (read with `torch.load`) | 0.313 / 0.0564 |
| identified notebook, cell 39 (hard-coded, with comment "fill in with the FRESH LOCO mean") | 0.2994 / 0.0535 |
| `…diagnostics (1).ipynb` | 0.2994 / 0.0535 |
| `…diagnostics.ipynb`, the four `…UPDATED__6_*` copies that carry the field | 0.3055 / 0.0540 |
| `patch_checkpoint_provenance.py` (mutates the checkpoint in place) | 0.3037 / `None` |

So the stored LOCO fields were set by a step that was **not** archived. They
are hand-entered metadata of unknown origin, not a recorded output. This is a
further reason, on top of C43, never to quote 0.313.

**Records this corrects.** `04_FINDINGS_LEDGER.md` C42 says "54 archived
notebooks at `ecfe370`". `git ls-tree` counts 37 `.ipynb` files there, 28 of
them GeoWatch notebooks.

## Reproduce

```python
# read-only; run with the project env from the repo root
import json, re, subprocess, torch
ck = torch.load("models/production/geowatch_production_model.pth", map_location="cpu", weights_only=False)
names = subprocess.run(["git", "ls-tree", "-r", "--name-only", "ecfe370"], capture_output=True, text=True).stdout.split("\n")
for n in sorted(x for x in names if x.endswith(".ipynb") and "geowatch" in x):
    raw = subprocess.run(["git", "show", f"ecfe370:{n}"], capture_output=True).stdout
    try: nb = json.loads(raw)
    except json.JSONDecodeError: nb, _ = json.JSONDecoder().raw_decode(raw.decode())  # one archived file is malformed
    src = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    m = re.search(r"CITY_MAP\s*=\s*\{(.*?)\}", src, re.S)
    v1 = bool(m) and sorted(re.findall(r"'([a-z]+)'\s*:", m.group(1))) == sorted(ck["training_cities"])
    v2 = bool(re.search(r"class_a_idx\s*=\s*CATEGORIES\.index", src))  # pair checked by eye against ck["architecture"]
    v3 = bool(re.search(r"PROD_VAL_FRACTION\s*=\s*0\.10\b", src))
    print(n.split("/")[-1], v1, v2, v3, "np.load" in src, len(set(re.findall(r"def (build_\w+_patches)", src))),
          re.findall(r"'loco_mean_miou':\s*([0-9.]+)", src), sep=" | ")
```

(V4 holds for every candidate that passes V1–V3, so it is left out of the
snippet. Mtimes: `ls -lT ~/Downloads/geowatch_*.ipynb models/production/`.)
