"""Deterministic ten-session Shadow probability model.

This module deliberately has no dependency on ``server.py``.  It consumes
completed daily OHLCV rows, builds chronological purged folds, fits one model
per market, calibrates probabilities on a separate fold and publishes held-out
evidence.  The current-universe historical backfill can never authorize a
production decision; callers must preserve that boundary as well.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo


MODEL_ID = "ten-day-technical-shadow-v1"
LABEL_VERSION = "r10-net-total-return-v1"
FEATURE_SCHEMA_VERSION = "technical-d1-v1"
TRAINING_PROVENANCE = "current_universe_historical_backfill"
HORIZON_SESSIONS = 10
PURGE_DAYS = 10
CALIBRATION_DAYS = 30
TEST_DAYS = 40
MIN_TRAIN_DAYS = 100
MAX_SAMPLES_PER_DATE = 24
TRANSACTION_COSTS = {"a_share": 0.0015, "hk": 0.0030, "us": 0.0015}
QUALITY_GATE = {
    "minimum_independent_test_dates": TEST_DAYS,
    "minimum_brier_skill": 0.01,
    "minimum_auc": 0.55,
    "maximum_ece_10bin": 0.10,
    "minimum_top_decile_excess_vs_mean": 0.005,
    "minimum_top_decile_mean_net_return": 0.0,
}
MARKET_TIMEZONES = {
    "a_share": ZoneInfo("Asia/Shanghai"),
    "hk": ZoneInfo("Asia/Hong_Kong"),
    "us": ZoneInfo("America/New_York"),
}
MARKET_CLOSES = {
    "a_share": dt.time(15, 10),
    "hk": dt.time(16, 10),
    "us": dt.time(16, 10),
}
FEATURE_NAMES = (
    "return_1",
    "return_5",
    "return_10",
    "return_20",
    "ma_5_gap",
    "ma_10_gap",
    "ma_20_gap",
    "volatility_10",
    "volatility_20",
    "drawdown_20",
    "range_position_20",
    "volume_ratio_5_20",
    "atr_14",
)


@dataclass(frozen=True)
class Label:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    gross_return: float
    transaction_cost: float
    net_return: float
    positive: bool

    def __post_init__(self) -> None:
        try:
            entry_date = dt.date.fromisoformat(self.entry_date)
            exit_date = dt.date.fromisoformat(self.exit_date)
        except ValueError as exc:
            raise ValueError("label dates must be ISO dates") from exc
        if entry_date >= exit_date:
            raise ValueError("label exit date must be after entry date")
        if not all(
            math.isfinite(float(value))
            for value in (
                self.entry_price,
                self.exit_price,
                self.gross_return,
                self.transaction_cost,
                self.net_return,
            )
        ):
            raise ValueError("label values must be finite")
        if self.entry_price <= 0 or self.exit_price <= 0 or self.transaction_cost < 0:
            raise ValueError("label prices and transaction cost are invalid")
        if self.positive is not (self.net_return > 0.0):
            raise ValueError("label class must match net return")


@dataclass(frozen=True)
class Sample:
    market: str
    code: str
    signal_date: str
    signal_index: int
    entry_date: str
    exit_date: str
    features: tuple[float, ...]
    label: Label

    def __post_init__(self) -> None:
        if self.entry_date != self.label.entry_date or self.exit_date != self.label.exit_date:
            raise ValueError("sample dates must match its label")
        try:
            signal_date = dt.date.fromisoformat(self.signal_date)
            entry_date = dt.date.fromisoformat(self.entry_date)
            exit_date = dt.date.fromisoformat(self.exit_date)
        except ValueError as exc:
            raise ValueError("sample dates must be ISO dates") from exc
        if not signal_date < entry_date < exit_date:
            raise ValueError("sample signal, entry and exit dates must be strictly chronological")


@dataclass(frozen=True)
class ChronologicalSplit:
    train: tuple[Sample, ...]
    calibration: tuple[Sample, ...]
    test: tuple[Sample, ...]
    train_dates: tuple[str, ...]
    calibration_dates: tuple[str, ...]
    test_dates: tuple[str, ...]
    purged_dates: tuple[str, ...]

    @property
    def train_signal_index(self) -> tuple[int, ...]:
        return tuple(item.signal_index for item in self.train)

    @property
    def calibration_signal_index(self) -> tuple[int, ...]:
        return tuple(item.signal_index for item in self.calibration)

    @property
    def test_signal_index(self) -> tuple[int, ...]:
        return tuple(item.signal_index for item in self.test)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _positive(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("OHLC values must be positive finite numbers")
    return number


def _volume(value: Any) -> float:
    number = float(value or 0.0)
    if not math.isfinite(number) or number < 0:
        raise ValueError("volume must be a non-negative finite number")
    return number


def _row_values(row: dict) -> tuple[float, float, float, float, float]:
    opening = _positive(row.get("open"))
    high = _positive(row.get("high"))
    low = _positive(row.get("low"))
    close = _positive(row.get("close"))
    volume = _volume(row.get("volume"))
    if high < low:
        raise ValueError("daily high cannot be below daily low")
    return opening, high, low, close, volume


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values) / len(values)


def _population_std(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = _mean(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def feature_vector(rows: Sequence[dict], signal_index: int) -> tuple[float, ...]:
    """Return features using only rows at or before ``signal_index``."""

    if signal_index < 20 or signal_index >= len(rows):
        raise ValueError("feature vector requires 21 completed bars")
    window = rows[signal_index - 20 : signal_index + 1]
    parsed = [_row_values(row) for row in window]
    closes = [row[3] for row in parsed]
    highs = [row[1] for row in parsed]
    lows = [row[2] for row in parsed]
    volumes = [row[4] for row in parsed]
    current = closes[-1]

    def trailing_return(days: int) -> float:
        return current / closes[-(days + 1)] - 1.0

    returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))]
    high_20 = max(highs[-20:])
    low_20 = min(lows[-20:])
    range_width = high_20 - low_20
    volume_20 = _mean(volumes[-20:])
    previous_closes = closes[:-1]
    true_ranges = []
    for offset in range(7, 21):
        high = highs[offset]
        low = lows[offset]
        previous_close = previous_closes[offset - 1]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))

    values = (
        trailing_return(1),
        trailing_return(5),
        trailing_return(10),
        trailing_return(20),
        current / _mean(closes[-5:]) - 1.0,
        current / _mean(closes[-10:]) - 1.0,
        current / _mean(closes[-20:]) - 1.0,
        _population_std(returns[-10:]),
        _population_std(returns[-20:]),
        current / max(closes[-20:]) - 1.0,
        (current - low_20) / range_width if range_width > 0 else 0.5,
        _mean(volumes[-5:]) / volume_20 - 1.0 if volume_20 > 0 else 0.0,
        _mean(true_ranges) / current,
    )
    if len(values) != len(FEATURE_NAMES) or not all(math.isfinite(value) for value in values):
        raise ValueError("feature vector contains a non-finite value")
    return tuple(float(value) for value in values)


def ten_session_label(rows: Sequence[dict], signal_index: int, transaction_cost: float) -> Label:
    """Next-session open to tenth-session close, net of round-trip cost."""

    if signal_index < 0 or signal_index + HORIZON_SESSIONS >= len(rows):
        raise ValueError("label requires ten future sessions")
    if not _finite(transaction_cost) or transaction_cost < 0:
        raise ValueError("transaction cost must be non-negative")
    entry_date = str(rows[signal_index + 1].get("date") or "")[:10]
    exit_date = str(rows[signal_index + HORIZON_SESSIONS].get("date") or "")[:10]
    try:
        dt.date.fromisoformat(entry_date)
        dt.date.fromisoformat(exit_date)
    except ValueError as exc:
        raise ValueError("label entry and exit dates must be ISO dates") from exc
    if entry_date <= str(rows[signal_index].get("date") or "")[:10] or exit_date < entry_date:
        raise ValueError("label dates must be strictly chronological")
    entry = round(_positive(rows[signal_index + 1].get("open")), 8)
    exit_ = round(_positive(rows[signal_index + HORIZON_SESSIONS].get("close")), 8)
    gross = exit_ / entry - 1.0
    net = gross - float(transaction_cost)
    if not all(math.isfinite(value) for value in (gross, net)):
        raise ValueError("label contains a non-finite value")
    return Label(
        entry_date=entry_date,
        exit_date=exit_date,
        entry_price=entry,
        exit_price=exit_,
        gross_return=gross,
        transaction_cost=float(transaction_cost),
        net_return=net,
        positive=net > 0.0,
    )


def _sample_date(sample: Any) -> str:
    value = sample.signal_date if hasattr(sample, "signal_date") else sample.get("signal_date")
    return str(value)


def _sample_exit_date(sample: Any) -> str:
    value = sample.exit_date if hasattr(sample, "exit_date") else sample.get("exit_date")
    label = sample.label if hasattr(sample, "label") else sample.get("label")
    label_value = label.exit_date if hasattr(label, "exit_date") else None
    value = str(value or "")
    if label_value is not None and value != str(label_value):
        raise ValueError("sample exit date must match its label")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("sample exit date must be an ISO date") from exc
    return value


def chronological_split(
    samples: Iterable[Sample],
    *,
    calibration_days: int = CALIBRATION_DAYS,
    test_days: int = TEST_DAYS,
    purge_days: int = PURGE_DAYS,
) -> ChronologicalSplit:
    ordered = tuple(sorted(samples, key=lambda item: (_sample_date(item), item.market, item.code)))
    dates = sorted({_sample_date(sample) for sample in ordered})
    train_end = len(dates) - test_days - purge_days - calibration_days - purge_days
    if train_end <= 0:
        raise ValueError("insufficient independent dates for purged split")
    first_purge = dates[train_end : train_end + purge_days]
    calibration_start = train_end + purge_days
    calibration_end = calibration_start + calibration_days
    second_purge = dates[calibration_end : calibration_end + purge_days]
    test_start = calibration_end + purge_days
    train_dates = tuple(dates[:train_end])
    calibration_dates = tuple(dates[calibration_start:calibration_end])
    test_dates_tuple = tuple(dates[test_start : test_start + test_days])
    if len(calibration_dates) != calibration_days or len(test_dates_tuple) != test_days:
        raise ValueError("insufficient calibration or test dates")
    train_set = set(train_dates)
    calibration_set = set(calibration_dates)
    test_set = set(test_dates_tuple)
    calibration_boundary = calibration_dates[0]
    test_boundary = test_dates_tuple[0]
    train_samples = tuple(
        sample
        for sample in ordered
        if _sample_date(sample) in train_set and _sample_exit_date(sample) < calibration_boundary
    )
    calibration_samples = tuple(
        sample
        for sample in ordered
        if _sample_date(sample) in calibration_set and _sample_exit_date(sample) < test_boundary
    )
    test_samples = tuple(sample for sample in ordered if _sample_date(sample) in test_set)
    effective_train_dates = tuple(sorted({_sample_date(sample) for sample in train_samples}))
    effective_calibration_dates = tuple(sorted({_sample_date(sample) for sample in calibration_samples}))
    effective_test_dates = tuple(sorted({_sample_date(sample) for sample in test_samples}))
    return ChronologicalSplit(
        train=train_samples,
        calibration=calibration_samples,
        test=test_samples,
        train_dates=effective_train_dates,
        calibration_dates=effective_calibration_dates,
        test_dates=effective_test_dates,
        purged_dates=tuple([*first_purge, *second_purge]),
    )


def sigmoid(value: float) -> float:
    clipped = max(-35.0, min(35.0, float(value)))
    return 1.0 / (1.0 + math.exp(-clipped))


def _date_equal_weights(samples: Sequence[Any]) -> list[float]:
    counts = Counter(_sample_date(sample) for sample in samples)
    date_count = len(counts)
    sample_count = len(samples)
    if not counts or not sample_count:
        return []
    return [sample_count / (date_count * counts[_sample_date(sample)]) for sample in samples]


def _standardizer(matrix: Sequence[Sequence[float]], weights: Sequence[float]) -> tuple[list[float], list[float]]:
    if not matrix or not weights or len(matrix) != len(weights):
        raise ValueError("standardizer input is empty or inconsistent")
    total_weight = sum(weights)
    width = len(matrix[0])
    means = [sum(row[index] * weight for row, weight in zip(matrix, weights)) / total_weight for index in range(width)]
    deviations = []
    for index, mean in enumerate(means):
        variance = sum(weight * (row[index] - mean) ** 2 for row, weight in zip(matrix, weights)) / total_weight
        deviation = math.sqrt(max(0.0, variance))
        deviations.append(deviation if deviation > 1e-12 else 1.0)
    return means, deviations


def _scale(row: Sequence[float], means: Sequence[float], deviations: Sequence[float]) -> list[float]:
    return [(float(value) - means[index]) / deviations[index] for index, value in enumerate(row)]


def fit_logistic(
    matrix: Sequence[Sequence[float]],
    labels: Sequence[int],
    weights: Sequence[float],
    *,
    l2: float = 0.02,
    steps: int = 140,
    rate: float = 0.08,
) -> list[float]:
    if not matrix or len(matrix) != len(labels) or len(matrix) != len(weights):
        raise ValueError("logistic input is empty or inconsistent")
    if len(set(labels)) < 2:
        raise ValueError("logistic fit requires both classes")
    width = len(matrix[0])
    coefficients = [0.0] * (width + 1)
    total_weight = sum(weights)
    for step in range(steps):
        gradients = [0.0] * (width + 1)
        for row, label, weight in zip(matrix, labels, weights):
            score = coefficients[0] + sum(coefficients[index + 1] * row[index] for index in range(width))
            error = (sigmoid(score) - int(label)) * weight
            gradients[0] += error
            for index, value in enumerate(row):
                gradients[index + 1] += error * value
        step_rate = rate / math.sqrt(1.0 + step / 35.0)
        coefficients[0] -= step_rate * gradients[0] / total_weight
        for index in range(1, width + 1):
            gradient = gradients[index] / total_weight + l2 * coefficients[index]
            coefficients[index] = max(-12.0, min(12.0, coefficients[index] - step_rate * gradient))
    if not all(math.isfinite(value) for value in coefficients):
        raise ValueError("logistic coefficients are not finite")
    return coefficients


def _linear_score(coefficients: Sequence[float], row: Sequence[float]) -> float:
    return coefficients[0] + sum(coefficients[index + 1] * value for index, value in enumerate(row))


def _fit_platt(scores: Sequence[float], labels: Sequence[int], weights: Sequence[float]) -> tuple[float, float]:
    if not scores or len(scores) != len(labels) or len(scores) != len(weights) or len(set(labels)) < 2:
        raise ValueError("Platt calibration requires both classes")
    slope = 1.0
    intercept = 0.0
    total_weight = sum(weights)
    for step in range(180):
        slope_gradient = 0.0
        intercept_gradient = 0.0
        for score, label, weight in zip(scores, labels, weights):
            error = (sigmoid(slope * score + intercept) - int(label)) * weight
            slope_gradient += error * score
            intercept_gradient += error
        step_rate = 0.04 / math.sqrt(1.0 + step / 40.0)
        slope -= step_rate * (slope_gradient / total_weight + 0.002 * (slope - 1.0))
        intercept -= step_rate * intercept_gradient / total_weight
        slope = max(0.05, min(6.0, slope))
        intercept = max(-8.0, min(8.0, intercept))
    return slope, intercept


def _auc(
    probabilities: Sequence[float],
    labels: Sequence[int],
    weights: Sequence[float] | None = None,
) -> float | None:
    if len(probabilities) != len(labels):
        raise ValueError("AUC inputs are inconsistent")
    weights = list(weights) if weights is not None else [1.0] * len(labels)
    if len(weights) != len(labels):
        raise ValueError("AUC weights are inconsistent")
    positive_indices = [index for index, label in enumerate(labels) if int(label) == 1]
    negative_indices = [index for index, label in enumerate(labels) if int(label) == 0]
    positive_weight = sum(weights[index] for index in positive_indices)
    negative_weight = sum(weights[index] for index in negative_indices)
    if positive_weight <= 0 or negative_weight <= 0:
        return None
    concordance = 0.0
    for positive_index in positive_indices:
        for negative_index in negative_indices:
            comparison = 1.0 if probabilities[positive_index] > probabilities[negative_index] else (
                0.5 if probabilities[positive_index] == probabilities[negative_index] else 0.0
            )
            concordance += weights[positive_index] * weights[negative_index] * comparison
    return concordance / (positive_weight * negative_weight)


def _validation_metrics(records: Sequence[dict], *, baseline_probability: float) -> dict:
    if not records:
        return {}
    probabilities = [float(record["probability"]) for record in records]
    labels = [int(record["positive"]) for record in records]
    count = len(records)
    weights = _date_equal_weights(records)
    total_weight = sum(weights)
    brier = sum(
        weight * (probability - label) ** 2
        for probability, label, weight in zip(probabilities, labels, weights)
    ) / total_weight
    baseline_brier = sum(
        weight * (float(record.get("baseline_probability", baseline_probability)) - label) ** 2
        for record, label, weight in zip(records, labels, weights)
    ) / total_weight
    ece = 0.0
    for bucket in range(10):
        indices = [
            index
            for index, probability in enumerate(probabilities)
            if min(9, int(probability * 10)) == bucket
        ]
        if not indices:
            continue
        bucket_weight = sum(weights[index] for index in indices)
        confidence = sum(probabilities[index] * weights[index] for index in indices) / bucket_weight
        frequency = sum(float(labels[index]) * weights[index] for index in indices) / bucket_weight
        ece += bucket_weight / total_weight * abs(confidence - frequency)

    records_by_date: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        records_by_date[_sample_date(record)].append(record)
    daily_mean_returns = []
    daily_top_returns = []
    daily_tail_returns = []
    for date_text in sorted(records_by_date):
        daily_records = records_by_date[date_text]
        daily_returns = [float(record["net_return"]) for record in daily_records]
        ranked = sorted(
            daily_records,
            key=lambda record: (float(record["probability"]), str(record.get("market") or ""), str(record.get("code") or "")),
            reverse=True,
        )
        top_count = max(1, math.ceil(len(ranked) * 0.1))
        tail_count = max(1, math.ceil(len(daily_returns) * 0.1))
        daily_mean_returns.append(_mean(daily_returns))
        daily_top_returns.append(_mean([float(record["net_return"]) for record in ranked[:top_count]]))
        daily_tail_returns.append(_mean(sorted(daily_returns)[:tail_count]))
    mean_return = _mean(daily_mean_returns)
    top_return = _mean(daily_top_returns)
    top_excess = _mean(
        [top_value - mean_value for top_value, mean_value in zip(daily_top_returns, daily_mean_returns)]
    )
    expected_shortfall = _mean(daily_tail_returns)
    auc_value = _auc(probabilities, labels, weights)
    result = {
        "test_row_count": count,
        "independent_test_date_count": len(records_by_date),
        "validation_weighting": "signal_date_equal_weight_v1",
        "top_decile_policy": "per_signal_date_top_ceil_10pct_then_date_mean_v1",
        "brier_score": round(brier, 8),
        "baseline_brier_score": round(baseline_brier, 8),
        "brier_skill": round(1.0 - brier / baseline_brier, 8) if baseline_brier > 0 else None,
        "ece_10bin": round(ece, 8),
        "auc": round(auc_value, 8) if auc_value is not None else None,
        "positive_rate": round(sum(label * weight for label, weight in zip(labels, weights)) / total_weight, 8),
        "mean_net_return": round(mean_return, 8),
        "top_decile_mean_net_return": round(top_return, 8),
        "top_decile_excess_vs_mean": round(top_excess, 8),
        "expected_shortfall_10pct": round(expected_shortfall, 8),
    }
    json.dumps(result, allow_nan=False)
    return result


def _completed_cutoff(market: str, generated_at: dt.datetime | str | None) -> dt.date | None:
    if generated_at is None:
        return None
    if isinstance(generated_at, str):
        parsed = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    elif isinstance(generated_at, dt.datetime):
        parsed = generated_at
    else:
        raise TypeError("generated_at must be an aware datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    local = parsed.astimezone(MARKET_TIMEZONES[market])
    cutoff = local.date()
    if local.timetz().replace(tzinfo=None) < MARKET_CLOSES[market]:
        cutoff -= dt.timedelta(days=1)
    return cutoff


def completed_rows(rows: Sequence[dict], market: str, generated_at: dt.datetime | str | None) -> list[dict]:
    """Normalize rows and remove a provider's possibly-partial current bar."""

    cutoff = _completed_cutoff(market, generated_at)
    by_date: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_text = str(row.get("date") or "")[:10]
        try:
            row_date = dt.date.fromisoformat(date_text)
            _row_values(row)
        except (TypeError, ValueError, OverflowError):
            continue
        if cutoff is not None and row_date > cutoff:
            continue
        by_date[date_text] = dict(row)
    return [by_date[key] for key in sorted(by_date)]


def _cap_date_samples(samples: Sequence[Sample]) -> list[Sample]:
    groups: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        groups[sample.signal_date].append(sample)
    result = []
    for date_text in sorted(groups):
        ranked = sorted(
            groups[date_text],
            key=lambda sample: hashlib.sha256(
                f"{sample.market}|{date_text}|{sample.code}".encode("utf-8")
            ).hexdigest(),
        )
        result.extend(ranked[:MAX_SAMPLES_PER_DATE])
    return result


def _market_samples(
    market: str,
    rows_by_code: dict[str, list[dict]],
    generated_at: dt.datetime | str | None,
) -> tuple[list[Sample], dict[str, list[dict]]]:
    cost = TRANSACTION_COSTS[market]
    cleaned: dict[str, list[dict]] = {}
    samples: list[Sample] = []
    for code in sorted(rows_by_code):
        rows = completed_rows(rows_by_code.get(code) or [], market, generated_at)
        if len(rows) < 32:
            continue
        cleaned[str(code)] = rows
        for signal_index in range(20, len(rows) - HORIZON_SESSIONS):
            try:
                features = feature_vector(rows, signal_index)
                label = ten_session_label(rows, signal_index, cost)
            except (TypeError, ValueError, OverflowError):
                continue
            samples.append(
                Sample(
                    market=market,
                    code=str(code),
                    signal_date=str(rows[signal_index]["date"])[:10],
                    signal_index=signal_index,
                    entry_date=label.entry_date,
                    exit_date=label.exit_date,
                    features=features,
                    label=label,
                )
            )
    return _cap_date_samples(samples), cleaned


def _round_list(values: Sequence[float], digits: int = 10) -> list[float]:
    return [round(float(value), digits) for value in values]


def _artifact_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _latest_label_exit(samples: Sequence[Sample]) -> str:
    if not samples:
        raise ValueError("label cutoff requires at least one sample")
    return max(_sample_exit_date(sample) for sample in samples)


def _quality_gate_ready(validation: dict) -> bool:
    required = (
        "independent_test_date_count",
        "brier_skill",
        "auc",
        "ece_10bin",
        "top_decile_excess_vs_mean",
        "top_decile_mean_net_return",
    )
    if not all(_finite(validation.get(field)) for field in required):
        return False
    return bool(
        int(validation["independent_test_date_count"]) >= QUALITY_GATE["minimum_independent_test_dates"]
        and validation["brier_skill"] >= QUALITY_GATE["minimum_brier_skill"]
        and validation["auc"] >= QUALITY_GATE["minimum_auc"]
        and validation["ece_10bin"] <= QUALITY_GATE["maximum_ece_10bin"]
        and validation["top_decile_excess_vs_mean"]
        >= QUALITY_GATE["minimum_top_decile_excess_vs_mean"]
        and validation["top_decile_mean_net_return"]
        > QUALITY_GATE["minimum_top_decile_mean_net_return"]
    )


def _fit_market(
    market: str,
    rows_by_code: dict[str, list[dict]],
    generated_at: dt.datetime | str | None,
) -> tuple[dict, list[dict], list[dict]]:
    samples, cleaned = _market_samples(market, rows_by_code, generated_at)
    base = {
        "market": market,
        "model_id": MODEL_ID,
        "label_version": LABEL_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "transaction_cost": TRANSACTION_COSTS[market],
        "training_provenance": TRAINING_PROVENANCE,
        "input_symbol_count": len(rows_by_code),
        "usable_symbol_count": len(cleaned),
        "sample_row_count": len(samples),
        "quality_gate": dict(QUALITY_GATE),
        "reason_codes": [],
    }
    try:
        split = chronological_split(samples)
    except ValueError:
        base.update(
            {
                "status": "INSUFFICIENT_DATA",
                "training_cutoff": None,
                "fit_data_cutoff": None,
                "last_training_signal_date": None,
                "last_calibration_signal_date": None,
                "validation_cutoff": None,
                "validation": {},
                "reason_codes": ["INSUFFICIENT_PURGED_DATE_HISTORY"],
                "artifact_sha256": _artifact_hash({**base, "status": "INSUFFICIENT_DATA"}),
            }
        )
        return base, [], []
    if (
        len(split.train_dates) < MIN_TRAIN_DAYS
        or len(split.calibration_dates) < CALIBRATION_DAYS
        or len(split.test_dates) < TEST_DAYS
        or not split.train
        or not split.calibration
        or not split.test
    ):
        base.update(
            {
                "status": "INSUFFICIENT_DATA",
                "training_cutoff": None,
                "fit_data_cutoff": None,
                "last_training_signal_date": None,
                "last_calibration_signal_date": None,
                "validation_cutoff": None,
                "validation": {},
                "reason_codes": ["INSUFFICIENT_INDEPENDENT_TRAINING_DATES"],
                "artifact_sha256": _artifact_hash({**base, "status": "INSUFFICIENT_DATA"}),
            }
        )
        return base, [], []

    train_labels = [int(sample.label.positive) for sample in split.train]
    calibration_labels = [int(sample.label.positive) for sample in split.calibration]
    test_labels = [int(sample.label.positive) for sample in split.test]
    if any(len(set(labels)) < 2 for labels in (train_labels, calibration_labels, test_labels)):
        base.update(
            {
                "status": "INSUFFICIENT_DATA",
                "training_cutoff": None,
                "fit_data_cutoff": None,
                "last_training_signal_date": None,
                "last_calibration_signal_date": None,
                "validation_cutoff": None,
                "validation": {},
                "reason_codes": ["SINGLE_CLASS_PURGED_FOLD"],
                "artifact_sha256": _artifact_hash({**base, "status": "INSUFFICIENT_DATA"}),
            }
        )
        return base, [], []

    train_matrix_raw = [sample.features for sample in split.train]
    train_weights = _date_equal_weights(split.train)
    means, deviations = _standardizer(train_matrix_raw, train_weights)
    train_matrix = [_scale(row, means, deviations) for row in train_matrix_raw]
    coefficients = fit_logistic(train_matrix, train_labels, train_weights)
    calibration_matrix = [_scale(sample.features, means, deviations) for sample in split.calibration]
    calibration_scores = [_linear_score(coefficients, row) for row in calibration_matrix]
    calibration_weights = _date_equal_weights(split.calibration)
    platt_slope, platt_intercept = _fit_platt(calibration_scores, calibration_labels, calibration_weights)

    baseline_probability = sum(label * weight for label, weight in zip(train_labels, train_weights)) / sum(train_weights)
    test_records = []
    for sample in split.test:
        score = _linear_score(coefficients, _scale(sample.features, means, deviations))
        probability_value = sigmoid(platt_slope * score + platt_intercept)
        test_records.append(
            {
                "market": market,
                "code": sample.code,
                "signal_date": sample.signal_date,
                "probability": probability_value,
                "positive": sample.label.positive,
                "net_return": sample.label.net_return,
                "baseline_probability": baseline_probability,
            }
        )
    validation = _validation_metrics(test_records, baseline_probability=baseline_probability)
    validation.update(
        {
            "train_row_count": len(split.train),
            "calibration_row_count": len(split.calibration),
            "independent_train_date_count": len(split.train_dates),
            "independent_calibration_date_count": len(split.calibration_dates),
            "purged_date_count": len(split.purged_dates),
        }
    )
    quality_ready = _quality_gate_ready(validation)
    status = "SHADOW_READY" if quality_ready else "SHADOW_REJECTED"
    reason_codes = [] if quality_ready else ["HELD_OUT_QUALITY_GATE_NOT_MET"]

    train_returns = [sample.label.net_return for sample in split.train]
    positive_returns = [value for value in train_returns if value > 0]
    nonpositive_returns = [value for value in train_returns if value <= 0]
    tail_count = max(1, math.ceil(len(train_returns) * 0.1))
    tail_risk = abs(_mean(sorted(train_returns)[:tail_count]))
    return_profile = {
        "positive_mean": _mean(positive_returns),
        "nonpositive_mean": _mean(nonpositive_returns),
        "tail_risk": tail_risk,
    }
    last_training_signal_date = split.train_dates[-1]
    last_calibration_signal_date = split.calibration_dates[-1]
    training_cutoff = _latest_label_exit([*split.train, *split.calibration])
    validation_cutoff = _latest_label_exit(split.test)
    artifact_payload = {
        "model_id": MODEL_ID,
        "label_version": LABEL_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "market": market,
        "feature_names": FEATURE_NAMES,
        "last_training_signal_date": last_training_signal_date,
        "last_calibration_signal_date": last_calibration_signal_date,
        "training_cutoff": training_cutoff,
        "fit_data_cutoff": training_cutoff,
        "validation_cutoff": validation_cutoff,
        "means": _round_list(means),
        "deviations": _round_list(deviations),
        "coefficients": _round_list(coefficients),
        "platt_slope": round(platt_slope, 10),
        "platt_intercept": round(platt_intercept, 10),
        "return_profile": {key: round(value, 10) for key, value in return_profile.items()},
        "transaction_cost": TRANSACTION_COSTS[market],
        "quality_gate": QUALITY_GATE,
    }
    artifact_sha256 = _artifact_hash(artifact_payload)
    base.update(
        {
            "status": status,
            "last_training_signal_date": last_training_signal_date,
            "last_calibration_signal_date": last_calibration_signal_date,
            "training_cutoff": training_cutoff,
            "fit_data_cutoff": training_cutoff,
            "validation_cutoff": validation_cutoff,
            "feature_names": list(FEATURE_NAMES),
            "scaler_mean": _round_list(means),
            "scaler_deviation": _round_list(deviations),
            "coefficients": _round_list(coefficients),
            "platt_slope": round(platt_slope, 10),
            "platt_intercept": round(platt_intercept, 10),
            "return_profile": {key: round(value, 10) for key, value in return_profile.items()},
            "validation": validation,
            "reason_codes": reason_codes,
            "artifact_sha256": artifact_sha256,
        }
    )

    predictions = []
    for code in sorted(cleaned):
        rows = cleaned[code]
        if len(rows) < 21:
            continue
        try:
            features = feature_vector(rows, len(rows) - 1)
        except (TypeError, ValueError, OverflowError):
            continue
        score = _linear_score(coefficients, _scale(features, means, deviations))
        probability_value = sigmoid(platt_slope * score + platt_intercept)
        expected_return = (
            probability_value * return_profile["positive_mean"]
            + (1.0 - probability_value) * return_profile["nonpositive_mean"]
        )
        rounded_return = round(expected_return, 8)
        rounded_tail = round(tail_risk, 8)
        predictions.append(
            {
                "market": market,
                "code": code,
                "model_id": MODEL_ID,
                "label_version": LABEL_VERSION,
                "probability": round(probability_value, 8),
                "expected_net_return": rounded_return,
                "expected_net_utility": round(rounded_return - 0.25 * rounded_tail, 8),
                "transaction_cost": TRANSACTION_COSTS[market],
                "tail_risk": rounded_tail,
                "market_validation_status": status,
                "prediction_as_of": str(rows[-1].get("date"))[:10],
                "artifact_sha256": artifact_sha256,
                "training_cutoff": training_cutoff,
                "fit_data_cutoff": training_cutoff,
                "participates_in_decision": False,
                "production_eligible": False,
            }
        )
    json.dumps({"market_model": base, "predictions": predictions}, allow_nan=False)
    return base, predictions, test_records


def build_shadow_model(rows: Sequence[dict], generated_at: dt.datetime | str | None = None) -> dict:
    """Convenience helper for deterministic single-series tests and audits."""

    if generated_at is None and rows:
        last_date = str(rows[-1].get("date"))[:10]
        generated_at = f"{last_date}T23:00:00+08:00"
    artifact, _, _ = _fit_market("a_share", {"SYNTHETIC": list(rows)}, generated_at)
    return artifact


def build_snapshot_model_contract(
    snapshot: dict,
    kline_maps: dict[str, dict[str, list[dict]]],
    generated_at: dt.datetime | str | None,
) -> dict:
    market_models: dict[str, dict] = {}
    predictions: list[dict] = []
    test_records: list[dict] = []
    for market in ("a_share", "hk", "us"):
        rows_by_code = kline_maps.get(market) if isinstance(kline_maps, dict) else None
        rows_by_code = rows_by_code if isinstance(rows_by_code, dict) else {}
        artifact, market_predictions, market_test = _fit_market(market, rows_by_code, generated_at)
        market_models[market] = artifact
        predictions.extend(market_predictions)
        test_records.extend(market_test)

    statuses = [model.get("status") for model in market_models.values()]
    if "SHADOW_READY" in statuses:
        status = "SHADOW_READY"
    elif "SHADOW_REJECTED" in statuses:
        status = "SHADOW_REJECTED"
    else:
        status = "INSUFFICIENT_DATA"
    fitted_models = [model for model in market_models.values() if model.get("status") in {"SHADOW_READY", "SHADOW_REJECTED"}]
    if test_records and fitted_models:
        weighted_baseline = _mean([float(record["baseline_probability"]) for record in test_records])
        validation = _validation_metrics(test_records, baseline_probability=weighted_baseline)
        validation.update(
            {
                "train_row_count": sum(int(model["validation"].get("train_row_count") or 0) for model in fitted_models),
                "calibration_row_count": sum(int(model["validation"].get("calibration_row_count") or 0) for model in fitted_models),
                "independent_train_date_count": max(
                    int(model["validation"].get("independent_train_date_count") or 0)
                    for model in fitted_models
                ),
                "independent_calibration_date_count": max(
                    int(model["validation"].get("independent_calibration_date_count") or 0)
                    for model in fitted_models
                ),
            }
        )
    else:
        validation = {}
    training_cutoffs = [str(model.get("training_cutoff")) for model in fitted_models if model.get("training_cutoff")]
    fit_data_cutoffs = [str(model.get("fit_data_cutoff")) for model in fitted_models if model.get("fit_data_cutoff")]
    validation_cutoffs = [str(model.get("validation_cutoff")) for model in fitted_models if model.get("validation_cutoff")]
    training_signal_dates = [
        str(model.get("last_training_signal_date"))
        for model in fitted_models
        if model.get("last_training_signal_date")
    ]
    calibration_signal_dates = [
        str(model.get("last_calibration_signal_date"))
        for model in fitted_models
        if model.get("last_calibration_signal_date")
    ]
    limitations = [
        "当前动态候选池成员向前回填历史 K 线，存在选择偏差和存活偏差。",
        "Shadow 概率只用于研究排序与在线验证，不参与正式决策。",
        "公开行情源没有交易所级 SLA；缺失或未完成日 K 会被剔除。",
    ]
    reason_codes = sorted(
        {
            str(code)
            for model in market_models.values()
            for code in (model.get("reason_codes") or [])
            if code
        }
    )
    aggregate_identity = {
        "model_id": MODEL_ID,
        "label_version": LABEL_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "training_provenance": TRAINING_PROVENANCE,
        "quality_gate": QUALITY_GATE,
        "market_artifacts": {
            market: model.get("artifact_sha256") for market, model in sorted(market_models.items())
        },
    }
    result = {
        "model_id": MODEL_ID,
        "label_version": LABEL_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "status": status,
        "calibrated": False,
        "costs_ready": bool(fitted_models),
        "tail_risk_ready": bool(fitted_models),
        "participates_in_decision": False,
        "production_eligible": False,
        "probability": None,
        "last_training_signal_date": max(training_signal_dates) if training_signal_dates else None,
        "last_calibration_signal_date": max(calibration_signal_dates) if calibration_signal_dates else None,
        "training_cutoff": max(training_cutoffs) if training_cutoffs else None,
        "fit_data_cutoff": max(fit_data_cutoffs) if fit_data_cutoffs else None,
        "validation_cutoff": max(validation_cutoffs) if validation_cutoffs else None,
        "training_provenance": TRAINING_PROVENANCE,
        "quality_gate": dict(QUALITY_GATE),
        "market_models": market_models,
        "validation": validation,
        "limitations": limitations,
        "artifact_sha256": _artifact_hash(aggregate_identity),
        "shadow_prediction_count": len(predictions),
        "shadow_predictions": sorted(predictions, key=lambda item: (item["market"], item["code"])),
        "reason_codes": reason_codes,
    }
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


__all__ = [
    "FEATURE_NAMES",
    "QUALITY_GATE",
    "Label",
    "Sample",
    "ChronologicalSplit",
    "build_shadow_model",
    "build_snapshot_model_contract",
    "chronological_split",
    "completed_rows",
    "feature_vector",
    "fit_logistic",
    "sigmoid",
    "ten_session_label",
]
