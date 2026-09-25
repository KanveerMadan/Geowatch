"""
Item 21 Phase A, part 5 — the regressor interface, and PLACEHOLDER regressors.

Phase A trains nothing (validation-first mandate; item 21 regressors need
hand labels that do not exist yet). The pipeline still has to run end to
end, so vegetation, water and the impervious share of the hard-surface
remainder come from placeholders behind the same interface the real
regressors will implement.

  ███ A PLACEHOLDER OUTPUT IS NOT A MEASUREMENT. ███

Placeholders return a constant from configs/fractions.yaml `placeholders`,
with provenance "placeholder". Bookkeeping propagates that mark to every
quantity derived from them, and the run output carries a top-level
`contains_placeholder: true` banner.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PLACEHOLDER = "placeholder"

# What each regressor predicts.
#   vegetation, water       fraction of the pixel
#   impervious_share        share of the HARD-SURFACE REMAINDER that is
#                           impervious (Phase A ruling, 2026-09-25), in [0, 1]
REGRESSOR_TARGETS = ("vegetation", "water", "impervious_share")


@dataclass
class Prediction:
    value: np.ndarray            # NaN where the pixel is not known
    provenance: str              # "placeholder" | "regression"
    prediction_interval: dict    # Decision 14 (b), estimate-quality group


class Regressor:
    """The interface. A real regressor implements `predict` from the
    observable composite and the other per-pixel features."""
    target: str

    def predict(self, features: dict, known: np.ndarray) -> Prediction:
        raise NotImplementedError


class PlaceholderRegressor(Regressor):
    """Returns a constant. NOT A MODEL. Exists so the pipeline runs end to
    end before any regressor is trained."""

    def __init__(self, target: str, value: float):
        if target not in REGRESSOR_TARGETS:
            raise ValueError(f"unknown regressor target {target!r}")
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"placeholder {target}={value} outside [0, 1]")
        self.target = target
        self.value = float(value)

    def predict(self, features: dict, known: np.ndarray) -> Prediction:
        v = np.where(known, self.value, np.nan).astype(np.float32)
        return Prediction(
            value=v, provenance=PLACEHOLDER,
            prediction_interval={"status": "not_computed",
                                 "reason": "placeholder regressor has no interval"})


def placeholder_regressors(cfg: dict) -> dict:
    p = cfg["placeholders"]["regressors"]
    return {t: PlaceholderRegressor(t, p[t]) for t in REGRESSOR_TARGETS}
