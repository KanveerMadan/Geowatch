# M2 pluvial (rain / urban): reproduce

Environment: `geowatch-env` Python with LightGBM 4.7.0 on `PYTHONPATH`; Earth Engine credentials for the build steps only.

```bash
# DEV inputs and tables (Earth Engine)
python -m experiments.flood_final.build_units --dev
# DEV cross-validation, method choice, report
python -m experiments.flood_final.model_v2 cv
python -m experiments.flood_final.model_v2 choose
python -m experiments.flood_final.dev_report
# held-out (refuses unless HEAD = flood-final-heldout-freeze and heldout.json is absent)
python -m experiments.flood_final.heldout_pass build
python -m experiments.flood_final.heldout_pass score
# this pack
python paper/evidence/flood_final_build.py && python paper/evidence/flood_final_docs.py
```

The held-out score refuses to run twice (`results/heldout.json` is opened with mode `x`).
