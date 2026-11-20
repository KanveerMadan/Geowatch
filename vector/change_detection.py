"""Local, seasonal change screening on an identifiable spatial support.

A series belongs to one source, acquisition track, measurement and fixed support.
Training and threshold selection both precede the monitoring interval. Signal
differences are reported in instrument units. Interpretation and alert validation
are separate stages.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from hashlib import sha256
import json
import math

import numpy as np

MODEL_VERSION = "seasonal-history-v1"
YEAR = 365.2425
SIGNALS = {
    "ndvi": ("greenness", "index"),
    "mndwi": ("open_water_signal", "index"),
    "ndbi": ("built_surface_signal", "index"),
    "vv_db": ("radar_vv_backscatter", "dB"),
    "vh_db": ("radar_vh_backscatter", "dB"),
    "building_presence": ("historical_building_presence", "confidence_score"),
}


@dataclass(frozen=True)
class DetectionConfig:
    """Experimental operating choices; none imply a calibrated alert probability.

    Use no more than five local years to limit long-term drift. Reserve the last
    annual cycle to measure forecast error out of time. Two harmonics represent
    annual and twice-yearly responses. The envelope covers the chosen empirical
    fraction of pre-monitoring residuals. Screen many opportunities together
    using held-out maxima across tracks and query-length time blocks. A two-date confirmation rejects single
    acquisitions, a 90-day span describes persistence over roughly one season.
    Twice the local upper-quartile revisit gap tolerates one missed acquisition.
    """

    history_years: int = 5
    harmonics: int = 2
    envelope_quantile: float = 0.9
    confirmations: int = 2
    persistent_days: int = 90
    gap_multiple: float = 2.0

    def __post_init__(self):
        if self.history_years < 2 or self.harmonics not in (1, 2):
            raise ValueError("seasonal detection requires at least two years and one or two harmonics")
        if not 0.5 < self.envelope_quantile < 1 or self.confirmations < 2:
            raise ValueError("invalid empirical quantile or confirmation count")
        if self.persistent_days <= 0 or self.gap_multiple < 1:
            raise ValueError("invalid persistence or observation gap")


@lru_cache(maxsize=8192)
def _day(value):
    return value if type(value) is date else date.fromisoformat(str(value)[:10])


def _ago(day, years):
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def _design(days, origin, harmonics):
    t = (np.asarray(days, dtype=float) - origin) / YEAR
    cols = [np.ones_like(t), t]
    for h in range(1, harmonics + 1):
        angle = 2 * np.pi * h * t
        cols.extend([np.cos(angle), np.sin(angle)])
    return np.column_stack(cols)


def _quarters(days):
    return {(date.fromordinal(int(d)).month - 1) // 3 for d in days}


def _baseline(days, values, start, cfg):
    """Fit on early history; measure out-of-time errors on its final year."""
    cal = days >= _ago(date.fromordinal(start), 1).toordinal()
    train = ~cal
    parameters = 2 + 2 * cfg.harmonics
    if np.sum(train) < 2 * parameters or np.sum(cal) < math.ceil(cfg.envelope_quantile / (1 - cfg.envelope_quantile) - 1e-9):
        return None, "insufficient_training_or_calibration_dates"
    if len(_quarters(days[train])) != 4 or len(_quarters(days[cal])) != 4:
        return None, "incomplete_seasonal_history"
    # Dense acquisitions over a single annual cycle cannot separate trend and season.
    if np.ptp(days[train]) + np.median(np.diff(days[train])) < 365:
        return None, "short_training_span"
    precision = np.finfo(np.float32).eps * max(1.0, float(np.median(np.abs(values[train]))))
    if np.ptp(values[train]) <= precision:
        return None, "uninformative_flat_training_signal"
    origin = int(days[train][0])
    X = _design(days, origin, cfg.harmonics)
    A, y = X[train], values[train]
    weights = np.ones(len(y))
    for _ in range(4):  # robust least squares, Huber's conventional tuning value
        W = np.sqrt(weights)
        beta, _, rank, _ = np.linalg.lstsq(A * W[:, None], y * W, rcond=None)
        if rank < parameters:
            return None, "unidentifiable_season_or_trend"
        residual = y - A @ beta
        mad = np.median(np.abs(residual - np.median(residual)))
        if mad < 1e-12:
            break
        weights = np.minimum(1.0, 1.345 * 1.4826 * mad / np.maximum(np.abs(residual), 1e-12))
    inv = np.linalg.pinv((A * W[:, None]).T @ (A * W[:, None]))
    predicted = X[cal] @ beta
    leverage = np.sqrt(1.0 + np.einsum("ij,jk,ik->i", X[cal], inv, X[cal]))
    cal_errors = np.abs(values[cal] - predicted) / leverage
    # Upper empirical order statistic; no nominal coverage claim for correlated dates.
    rank = min(len(cal_errors), math.ceil((len(cal_errors) + 1) * cfg.envelope_quantile))
    # Bounds below the float32 measurement precision are numerically meaningless.
    envelope = max(float(np.partition(cal_errors, rank - 1)[rank - 1]), float(precision))
    gap = max(1, math.ceil(cfg.gap_multiple * np.quantile(np.diff(days), 0.75)))
    return (origin, beta, inv, envelope, gap, days[cal], cal_errors / envelope), None


def _groups(observations, earliest, until):
    groups = defaultdict(lambda: defaultdict(list))
    for row in observations:
        day = _day(row["date"])
        if not earliest <= day <= until:
            continue
        source = str(row["source"])
        track = str(row.get("track") or "")
        if source == "sentinel1" and not track:
            continue
        coverage = row.get("coverage", 1)
        if coverage is None or not math.isfinite(float(coverage)) or float(coverage) <= 0:
            continue
        lineage = row.get("lineage") or ("sentinel2" if source == "open_buildings" else source)
        if isinstance(lineage, str):
            lineage = (lineage,)
        else:
            lineage = tuple(sorted(map(str, lineage)))
        key = (source, track, str(row.get("support_id") or ""), lineage)
        for signal, value in row["values"].items():
            if signal in SIGNALS and value is not None and math.isfinite(value):
                groups[(*key, signal)][day.toordinal()].append(float(value))
    return groups


def _iso(day):
    return date.fromordinal(int(day)).isoformat()


def _signal_run(cell_id, d, prev, key, sign):
    source, track, support, lineage, signal = key
    eid = sha256(json.dumps([cell_id, source, track, support, signal, d, sign],
                            separators=(",", ":")).encode()).hexdigest()[:24]
    direction = "gain" if sign > 0 else "loss"
    return {
        "event_id": eid, "transition": f"{SIGNALS[signal][0]}_{direction}",
        "direction": direction, "onset": {"after": _iso(prev) if prev is not None else None,
                                          "by": _iso(d)},
        "detected_on": _iso(d), "last_evidence_on": _iso(d), "confirmed_on": None,
        "recovered_on": None, "lifecycle": "candidate", "trajectory": "unresolved",
        "sources": [source], "lineages": list(lineage),
        "signals": [{"signal": signal, "source": source, "track": track, "unit": SIGNALS[signal][1],
                     "support_id": support}],
        "_dates": [], "_residuals": [],
    }


def _finish_run(event, recovered, cfg):
    event["_returned"] = _iso(recovered) if recovered is not None else None
    dates, residuals = event["_dates"], np.asarray(event.pop("_residuals"))
    if len(dates) < cfg.confirmations:
        return
    event["confirmed_on"] = _iso(dates[cfg.confirmations - 1])
    event["lifecycle"] = "corroborated"
    if dates[-1] - dates[0] >= cfg.persistent_days:
        event["lifecycle"], event["trajectory"] = "persistent", "sustained"
        # Persistent ramp versus abrupt step: a sloping line must explain the
        # measurements better than the best two-level step by a full envelope.
        if len(dates) >= 4:
            t = np.asarray(dates) - dates[0]
            line = np.polyval(np.polyfit(t, residuals, 1), t)
            prefix = np.cumsum(residuals)[:-1]
            n = len(dates)
            left = np.arange(1, n)
            explained = prefix**2 / left + (residuals.sum() - prefix)**2 / (n - left)
            step_sse = max(0.0, float(residuals @ residuals - explained.max()))
            margin = event["signals"][0]["threshold"]
            if (np.sign(line[-1] - line[0]) == np.sign(residuals[-1])
                    and abs(line[-1] - line[0]) > margin
                    and (step_sse - np.sum((residuals - line) ** 2)) / len(dates) > margin ** 2):
                event["trajectory"] = "gradual"
    if recovered is not None:
        event["recovered_on"] = _iso(recovered)
        event["lifecycle"], event["trajectory"] = "recovered", "temporary"


def _prepare(key, vals, start, end, cfg):
    source, track, support, lineage, signal = key
    days = np.asarray(sorted(vals))
    daily = [vals[d] for d in days]
    values = np.asarray([v[0] if len(v) == 1 else np.median(v) for v in daily])
    historical = days < start
    in_window = (days >= start) & (days < end)
    history, in_dates = days[historical], days[in_window]
    info = {"signal": signal, "source": source, "track": track, "lineages": list(lineage),
            "support_id": support, "unit": SIGNALS[signal][1], "history_count": len(history),
            "observed_count": len(in_dates), "status": "insufficient_observation",
            "first_observed_on": _iso(in_dates[0]) if len(in_dates) else None,
            "last_observed_on": _iso(in_dates[-1]) if len(in_dates) else None}
    if signal == "building_presence":
        info.update(status="context_only", reason="annual_uncalibrated_building_confidence")
        return info, None
    model, reason = _baseline(history, values[historical], start, cfg)
    if reason:
        info["reason"] = reason
        return info, None
    return info, (days, values, model)


def _family_envelope(prepared, start, end, cfg):
    """Learn a common scale multiplier from historical query-length maxima.

    One whole calibration year is available per locally supported series. Short
    samples use their observed maximum and explicitly report the block count.
    The same retrospective operating rule applies to each new acquisition.
    """
    history_span = start - _ago(date.fromordinal(start), 1).toordinal()
    window = min(end - start, history_span)
    nblocks = history_span // window
    peaks = np.full(nblocks, np.nan)
    for _, _, inputs in prepared:
        if inputs is None:
            continue
        days, scores = inputs[2][-2:]
        block = (start - 1 - days) // window
        for b in np.unique(block):
            if b < nblocks:
                peaks[b] = np.fmax(peaks[b], np.max(scores[block == b]))
    peaks = peaks[np.isfinite(peaks)]
    if not len(peaks):
        return None, 0, window
    index = min(len(peaks), math.ceil((len(peaks) + 1) * cfg.envelope_quantile)) - 1
    return max(1., float(np.partition(peaks, index)[index])), len(peaks), window


def _score(cell_id, key, info, inputs, start, end, until, family_scale, cfg):
    days, values, model = inputs
    historical = days < start
    in_dates = days[(days >= start) & (days < end)]
    if not len(in_dates):
        info["reason"] = "no_measurement_during_query"
        return []
    if family_scale is None:
        info["reason"] = "no_calibration_block_as_long_as_query"
        return []
    origin, beta, inv, channel_scale, gap, cal_days, _ = model
    scale = family_scale * channel_scale
    target = days[~historical]
    X = _design(target, origin, cfg.harmonics)
    pred = X @ beta
    bounds = scale * np.sqrt(1.0 + np.einsum("ij,jk,ik->i", X, inv, X))
    complete_end = min(end - 1, until)
    gaps = np.diff(np.concatenate(([start], in_dates, [complete_end])))
    complete = (until >= end - 1 and len(in_dates) >= cfg.confirmations and np.max(gaps) <= gap)
    info.update(status="observed" if complete else "partial_observation",
                baseline_trend_per_year=float(beta[1]), calibration_count=len(cal_days),
                forecast_error_envelope=scale, continuity_gap_days=gap)
    # Only genuinely in-envelope historical observations can bound the onset.
    # Replay the latest calibration observations at the frozen threshold so an
    # episode already visible at the boundary cannot be dated as a fresh onset.
    hist_x = _design(cal_days, origin, cfg.harmonics)
    hist_bounds = scale * np.sqrt(1.0 + np.einsum("ij,jk,ik->i", hist_x, inv, hist_x))
    hist_delta = values[historical][-len(cal_days):] - hist_x @ beta
    normal = np.abs(hist_delta) <= hist_bounds * (1 + 1e-12)
    prev = int(cal_days[normal][-1]) if normal.any() else None
    # Two same-direction departures already present before the query can be
    # recognised from the channel's ordinary forecast variability even when that
    # departure itself widened the family-wise envelope.
    n = cfg.confirmations
    signs = np.sign(hist_delta[-n:])
    preexisting = 0
    if (len(signs) == n and np.all(signs == signs[-1]) and np.all(np.diff(cal_days[-n:]) <= gap)
            and np.all(np.abs(hist_delta[-n:]) > (hist_bounds[-n:] / family_scale) * (1 + 1e-12))):
        preexisting = int(signs[-1])
        prev = int(cal_days[normal & (cal_days < cal_days[-n])][-1]) if np.any(normal[:-n]) else None
    runs, active, normal_dates = [], None, []
    last_date = int(cal_days[-1])
    for raw_day, actual, estimate, bound in zip(target, values[~historical], pred, bounds):
        d = int(raw_day)
        if d - last_date > gap:
            preexisting = 0
            if active is not None:
                _finish_run(active, None, cfg)
                active, normal_dates = None, []
        last_date = d
        delta = float(actual - estimate)
        sign = int(np.sign(delta)) if abs(delta) > bound * (1 + 1e-12) else 0
        if preexisting and sign == preexisting:
            info["ongoing_at_start"] = True
            continue
        preexisting = 0
        if not sign:
            prev = d
            if active is not None:
                normal_dates.append(d)
                if len(normal_dates) >= cfg.confirmations:
                    _finish_run(active, d, cfg)
                    active, normal_dates = None, []
            continue
        if active is not None and (((active["direction"] == "gain") != (sign > 0))
                                   or (normal_dates and len(active["_dates"]) < cfg.confirmations)):
            _finish_run(active, None, cfg)
            active = None
        if active is None:
            if d >= end:
                continue  # later acquisitions may only update an episode in the query
            active = _signal_run(cell_id, d, prev, key, sign)
            active["onset_may_predate_window"] = prev is None or prev < start - 1
            runs.append(active)
        normal_dates = []
        active["_dates"].append(d)
        active["_residuals"].append(delta)
        active["last_evidence_on"] = _iso(d)
        measure = active["signals"][0]
        if abs(delta) > abs(measure.get("delta", 0)):
            measure.update(baseline=float(estimate), value=float(actual), delta=delta,
                           observed_on=_iso(d), threshold=float(bound))
    if active is not None:
        _finish_run(active, None, cfg)
    return runs


def _fuse(runs):
    """Corroborate matching signals observed over overlapping dates.

    Optical indices and building confidence derived from the same images cannot
    provide independent evidence. Different radar passes remain identifiable.
    """
    out = []
    for event in sorted(runs, key=lambda e: (e["detected_on"], e["event_id"])):
        partner = next((x for x in reversed(out)
                        if x["transition"] == event["transition"]
                        and x["signals"][0]["support_id"] == event["signals"][0]["support_id"]
                        and x["last_evidence_on"] >= event["detected_on"]
                        and set(x["lineages"]).isdisjoint(event["lineages"])), None)
        if partner is None:
            out.append(event)
            continue
        # Pairing staggered observations becomes knowable when the first stream
        # next overlaps the second stream, never before this date.
        overlap_day = _day(event["detected_on"]).toordinal()
        evidence_day = _iso(next(d for d in partner["_dates"] if d >= overlap_day))
        partner["signals"].extend(event["signals"])
        partner["sources"] = sorted(set(partner["sources"] + event["sources"]))
        partner["lineages"] = sorted(set(partner["lineages"] + event["lineages"]))
        partner["_dates"] = sorted(set(partner["_dates"] + event["_dates"]))
        partner["confirmed_on"] = min(d for d in (partner["confirmed_on"], event["confirmed_on"],
                                                   evidence_day) if d)
        partner["last_evidence_on"] = max(partner["last_evidence_on"], event["last_evidence_on"])
        # Cross-source recovery requires a return in both comparable histories.
        if partner["_returned"] and event["_returned"]:
            partner["_returned"] = max(partner["_returned"], event["_returned"])
            partner["recovered_on"] = partner["_returned"]
            partner["lifecycle"], partner["trajectory"] = "recovered", "temporary"
        else:
            partner["_returned"] = None
            partner["recovered_on"] = None
            lcs = (partner["lifecycle"], event["lifecycle"])
            partner["lifecycle"] = "persistent" if "persistent" in lcs else "corroborated"
            partner["trajectory"] = "sustained" if "persistent" in lcs else "unresolved"
    for e in out:
        e["detections"] = len(e.pop("_dates"))
        e.pop("_returned")
    return out


def detect_cell(cell_id, observations, *, start, end, mode="prospective", as_of=None, config=None):
    """Detect changes first seen in [start, end) on one fixed spatial unit.

    as_of is an inclusive data cutoff. Only an explicit retrospective as_of
    permits later evidence to establish persistence or recovery. Input records
    contain ISO date, source, track, optional support_id/lineage and a values
    mapping of native signal units. Quality-masked values should be None.
    """
    cfg = config or DetectionConfig()
    start, end = _day(start), _day(end)
    if start >= end or mode not in ("prospective", "retrospective"):
        raise ValueError("invalid monitoring interval or evidence mode")
    until = _day(as_of) if as_of is not None else end - timedelta(days=1)
    if mode == "prospective":
        until = min(until, end - timedelta(days=1))
    grouped = _groups(observations, _ago(start, cfg.history_years), until)
    first, last = start.toordinal(), end.toordinal()
    prepared = [(key, *_prepare(key, vals, first, last, cfg)) for key, vals in sorted(grouped.items())]
    scale, blocks, block_days = _family_envelope(prepared, first, last, cfg)
    series, runs = [], []
    for key, info, inputs in prepared:
        if inputs is not None:
            runs.extend(_score(cell_id, key, info, inputs, first, last, until.toordinal(), scale, cfg))
        series.append(info)
    events = _fuse(runs)
    state = "insufficient_observation"
    if any(s["status"] == "observed" for s in series):
        state = "no_change_detected"
    if events:
        state = ("change_detected" if any(e["lifecycle"] != "candidate" for e in events)
                 else "candidate_change")
    return {"cell_id": cell_id, "state": state, "events": events, "series": series,
            "mode": mode, "as_of": until.isoformat(), "model_version": MODEL_VERSION,
            "diagnostics": {"calibration_window_days": block_days, "calibration_blocks": blocks,
                            "query_days": last - first,
                            "multichannel_envelope_multiplier": scale},
            "validation_status": "experimental"}
