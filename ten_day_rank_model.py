"""Point-in-time ten-session excess-return ranking primitives.

This module is deliberately independent from :mod:`server`.  Version 2 is a
parallel Shadow research contract: it consumes immutable point-in-time
observations, predicts a continuous net excess return, and can never authorize
itself for production.  Collection, settlement, and production promotion are
separate trust boundaries.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


MODEL_ID = "ten-day-excess-rank-shadow-v2"
LABEL_VERSION = "r10-net-excess-return-v2"
FEATURE_SCHEMA_VERSION = "point-in-time-technical-d1-v2"
TRAINING_PROVENANCE = "point_in_time_universe_ledger"
ARTIFACT_CONTRACT_VERSION = "ten-day-rank-artifact-v2"
HORIZON_SESSIONS = 10
MIN_TRAIN_DAYS = 100
TEST_BLOCK_DAYS = 20
FIXED_RIDGE_L2 = 1.0
TRANSACTION_COSTS = {"a_share": 0.0015, "hk": 0.0030, "us": 0.0015}
REGISTERED_BENCHMARKS = {"a_share": "510300", "hk": "2800.HK", "us": "SPY"}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return number


def _iso_date(value: Any, field: str) -> str:
    text = str(value or "")[:10]
    try:
        dt.date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc
    return text


def _validate_rows(rows: Sequence[dict], *, field: str) -> list[dict]:
    if not rows:
        raise ValueError(f"{field} rows are empty")
    result: list[dict] = []
    previous_date: str | None = None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{field} row must be an object")
        date_text = _iso_date(row.get("date"), f"{field}.date")
        if previous_date is not None and date_text <= previous_date:
            raise ValueError(f"{field} rows must be strictly chronological and unique")
        for price_field in ("open", "close"):
            _positive(row.get(price_field), f"{field}.{price_field}")
        previous_date = date_text
        result.append(row)
    return result


@dataclass(frozen=True)
class ExcessReturnLabel:
    market: str
    benchmark_code: str
    entry_date: str
    exit_date: str
    stock_entry_price: float
    stock_exit_price: float
    benchmark_entry_price: float
    benchmark_exit_price: float
    stock_transaction_cost: float
    benchmark_transaction_cost: float
    stock_gross_return: float
    stock_net_return: float
    benchmark_gross_return: float
    benchmark_net_return: float
    net_excess_return: float

    def __post_init__(self) -> None:
        if self.market not in REGISTERED_BENCHMARKS:
            raise ValueError("label market is invalid")
        if self.benchmark_code != REGISTERED_BENCHMARKS[self.market]:
            raise ValueError("label benchmark is not registered for its market")
        entry = dt.date.fromisoformat(self.entry_date)
        exit_ = dt.date.fromisoformat(self.exit_date)
        if entry >= exit_:
            raise ValueError("label exit date must be after entry date")
        numeric_fields = (
            self.stock_entry_price,
            self.stock_exit_price,
            self.benchmark_entry_price,
            self.benchmark_exit_price,
            self.stock_transaction_cost,
            self.benchmark_transaction_cost,
            self.stock_gross_return,
            self.stock_net_return,
            self.benchmark_gross_return,
            self.benchmark_net_return,
            self.net_excess_return,
        )
        if not all(math.isfinite(float(value)) for value in numeric_fields):
            raise ValueError("label values must be finite")
        if min(
            self.stock_entry_price,
            self.stock_exit_price,
            self.benchmark_entry_price,
            self.benchmark_exit_price,
        ) <= 0:
            raise ValueError("label prices must be positive")
        if self.stock_transaction_cost < 0 or self.benchmark_transaction_cost < 0:
            raise ValueError("label costs must be non-negative")
        if not math.isclose(
            self.stock_net_return,
            self.stock_gross_return - self.stock_transaction_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("stock net return is inconsistent")
        if not math.isclose(
            self.benchmark_net_return,
            self.benchmark_gross_return - self.benchmark_transaction_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("benchmark net return is inconsistent")
        if not math.isclose(
            self.net_excess_return,
            self.stock_net_return - self.benchmark_net_return,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("net excess return is inconsistent")


def ten_session_excess_label(
    stock_rows: Sequence[dict],
    benchmark_rows: Sequence[dict],
    signal_index: int,
    *,
    market: str,
    benchmark_code: str | None = None,
    stock_transaction_cost: float | None = None,
    benchmark_transaction_cost: float | None = None,
) -> ExcessReturnLabel:
    """Return next-session-open to tenth-session-close net excess return.

    The benchmark must be the market's registered investable benchmark and
    must have observations on the exact stock entry and exit dates.  Missing
    benchmark evidence fails closed rather than substituting a later cohort.
    """

    if market not in REGISTERED_BENCHMARKS:
        raise ValueError("market is invalid")
    registered_benchmark = REGISTERED_BENCHMARKS[market]
    if benchmark_code is not None and benchmark_code != registered_benchmark:
        raise ValueError("benchmark is not registered for this market")
    benchmark_code = registered_benchmark
    stock_cost = TRANSACTION_COSTS[market] if stock_transaction_cost is None else stock_transaction_cost
    benchmark_cost = TRANSACTION_COSTS[market] if benchmark_transaction_cost is None else benchmark_transaction_cost
    if not _finite(stock_cost) or float(stock_cost) < 0:
        raise ValueError("stock transaction cost must be non-negative and finite")
    if not _finite(benchmark_cost) or float(benchmark_cost) < 0:
        raise ValueError("benchmark transaction cost must be non-negative and finite")

    stocks = _validate_rows(stock_rows, field="stock")
    benchmarks = _validate_rows(benchmark_rows, field="benchmark")
    if signal_index < 0 or signal_index + HORIZON_SESSIONS >= len(stocks):
        raise ValueError("label requires ten future stock sessions")
    signal_date = _iso_date(stocks[signal_index].get("date"), "stock.signal_date")
    entry_date = _iso_date(stocks[signal_index + 1].get("date"), "stock.entry_date")
    exit_date = _iso_date(stocks[signal_index + HORIZON_SESSIONS].get("date"), "stock.exit_date")
    if not signal_date < entry_date < exit_date:
        raise ValueError("label dates must be strictly chronological")

    benchmark_by_date = {_iso_date(row.get("date"), "benchmark.date"): row for row in benchmarks}
    if entry_date not in benchmark_by_date or exit_date not in benchmark_by_date:
        raise ValueError("registered benchmark is missing the exact entry or exit session")
    stock_entry = _positive(stocks[signal_index + 1].get("open"), "stock entry")
    stock_exit = _positive(stocks[signal_index + HORIZON_SESSIONS].get("close"), "stock exit")
    benchmark_entry = _positive(benchmark_by_date[entry_date].get("open"), "benchmark entry")
    benchmark_exit = _positive(benchmark_by_date[exit_date].get("close"), "benchmark exit")
    stock_gross = stock_exit / stock_entry - 1.0
    benchmark_gross = benchmark_exit / benchmark_entry - 1.0
    stock_net = stock_gross - float(stock_cost)
    benchmark_net = benchmark_gross - float(benchmark_cost)
    return ExcessReturnLabel(
        market=market,
        benchmark_code=benchmark_code,
        entry_date=entry_date,
        exit_date=exit_date,
        stock_entry_price=stock_entry,
        stock_exit_price=stock_exit,
        benchmark_entry_price=benchmark_entry,
        benchmark_exit_price=benchmark_exit,
        stock_transaction_cost=float(stock_cost),
        benchmark_transaction_cost=float(benchmark_cost),
        stock_gross_return=stock_gross,
        stock_net_return=stock_net,
        benchmark_gross_return=benchmark_gross,
        benchmark_net_return=benchmark_net,
        net_excess_return=stock_net - benchmark_net,
    )


@dataclass(frozen=True)
class RankSample:
    market: str
    code: str
    signal_date: str
    entry_date: str
    exit_date: str
    features: tuple[float, ...]
    label: ExcessReturnLabel
    # Optional audit metadata added by the immutable ledger join.  Defaults
    # preserve the original public constructor used by research tests/tools.
    feature_records: tuple[dict[str, Any], ...] = ()
    provenance_sha256: str = ""
    market_regime: str = "unknown"
    source_observation_id: str = ""
    currency: str = ""
    transaction_cost_version: str = ""

    def __post_init__(self) -> None:
        if self.market not in REGISTERED_BENCHMARKS or self.label.market != self.market:
            raise ValueError("sample market is invalid or inconsistent")
        signal = dt.date.fromisoformat(self.signal_date)
        entry = dt.date.fromisoformat(self.entry_date)
        exit_ = dt.date.fromisoformat(self.exit_date)
        if not signal < entry < exit_:
            raise ValueError("sample dates must be strictly chronological")
        if self.entry_date != self.label.entry_date or self.exit_date != self.label.exit_date:
            raise ValueError("sample dates must match its label")
        if not self.code:
            raise ValueError("sample code is required")
        if not self.features or not all(_finite(value) for value in self.features):
            raise ValueError("sample features must be finite and non-empty")
        if self.feature_records and len(self.features) != len(self.feature_records) * 2:
            raise ValueError("audited sample features must contain value/missingness pairs")
        if self.provenance_sha256 and (
            len(self.provenance_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.provenance_sha256)
        ):
            raise ValueError("sample provenance hash is invalid")


def _sample_date(sample: Any) -> str:
    return str(sample.signal_date if hasattr(sample, "signal_date") else sample.get("signal_date"))


def date_equal_weights(samples: Sequence[Any]) -> tuple[float, ...]:
    """Give every signal-date/market cell equal mass without dropping rows."""

    def cell(sample: Any) -> tuple[str, str]:
        market = str(sample.market if hasattr(sample, "market") else sample.get("market"))
        return _sample_date(sample), market

    counts = Counter(cell(sample) for sample in samples)
    if not samples or not counts:
        return ()
    sample_count = len(samples)
    cell_count = len(counts)
    return tuple(sample_count / (cell_count * counts[cell(sample)]) for sample in samples)


@dataclass(frozen=True)
class RidgeModel:
    feature_count: int
    sample_count: int
    signal_date_count: int
    l2: float
    means: tuple[float, ...]
    deviations: tuple[float, ...]
    coefficients: tuple[float, ...]

    def predict(self, features: Sequence[float]) -> float:
        if len(features) != self.feature_count or not all(_finite(value) for value in features):
            raise ValueError("prediction features are invalid")
        scaled = [
            (float(value) - self.means[index]) / self.deviations[index]
            for index, value in enumerate(features)
        ]
        prediction = self.coefficients[0] + sum(
            self.coefficients[index + 1] * value for index, value in enumerate(scaled)
        )
        if not math.isfinite(prediction):
            raise ValueError("ridge prediction is not finite")
        return prediction


def _solve_linear_system(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    width = len(vector)
    if width == 0 or len(matrix) != width or any(len(row) != width for row in matrix):
        raise ValueError("linear system dimensions are invalid")
    augmented = [[float(value) for value in row] + [float(vector[index])] for index, row in enumerate(matrix)]
    for column in range(width):
        pivot = max(range(column, width), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-14:
            raise ValueError("ridge normal equation is singular")
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]
        for row in range(width):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            augmented[row] = [
                value - factor * pivot_cell
                for value, pivot_cell in zip(augmented[row], augmented[column])
            ]
    result = [augmented[index][-1] for index in range(width)]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("ridge coefficients are not finite")
    return result


def fit_weighted_ridge(
    matrix: Sequence[Sequence[float]],
    targets: Sequence[float],
    weights: Sequence[float],
    *,
    l2: float = FIXED_RIDGE_L2,
    signal_date_count: int = 0,
) -> RidgeModel:
    """Fit deterministic weighted Ridge with an unregularized intercept."""

    if not matrix or len(matrix) != len(targets) or len(matrix) != len(weights):
        raise ValueError("ridge inputs are empty or inconsistent")
    if not _finite(l2) or float(l2) <= 0:
        raise ValueError("ridge l2 must be a positive finite number")
    width = len(matrix[0])
    if width == 0 or any(len(row) != width for row in matrix):
        raise ValueError("ridge feature widths are inconsistent")
    if not all(all(_finite(value) for value in row) for row in matrix):
        raise ValueError("ridge features must be finite")
    if not all(_finite(value) for value in targets):
        raise ValueError("ridge targets must be finite")
    if not all(_finite(value) and float(value) > 0 for value in weights):
        raise ValueError("ridge weights must be positive and finite")

    total_weight = sum(float(value) for value in weights)
    means = [
        sum(float(weight) * float(row[index]) for row, weight in zip(matrix, weights)) / total_weight
        for index in range(width)
    ]
    deviations: list[float] = []
    for index, mean in enumerate(means):
        variance = sum(
            float(weight) * (float(row[index]) - mean) ** 2
            for row, weight in zip(matrix, weights)
        ) / total_weight
        deviation = math.sqrt(max(0.0, variance))
        deviations.append(deviation if deviation > 1e-12 else 1.0)

    design = [
        [1.0, *[(float(value) - means[index]) / deviations[index] for index, value in enumerate(row)]]
        for row in matrix
    ]
    normal = [[0.0] * (width + 1) for _ in range(width + 1)]
    rhs = [0.0] * (width + 1)
    for row, target, weight in zip(design, targets, weights):
        weight_value = float(weight)
        target_value = float(target)
        for left in range(width + 1):
            rhs[left] += weight_value * row[left] * target_value
            for right in range(left, width + 1):
                normal[left][right] += weight_value * row[left] * row[right]
    for left in range(width + 1):
        for right in range(left):
            normal[left][right] = normal[right][left]
    for index in range(1, width + 1):
        normal[index][index] += float(l2)
    coefficients = _solve_linear_system(normal, rhs)
    return RidgeModel(
        feature_count=width,
        sample_count=len(matrix),
        signal_date_count=int(signal_date_count),
        l2=float(l2),
        means=tuple(means),
        deviations=tuple(deviations),
        coefficients=tuple(coefficients),
    )


def fit_date_equal_ridge(samples: Sequence[RankSample]) -> RidgeModel:
    """Fit the registered fixed Ridge on every supplied point-in-time row."""

    ordered = sorted(samples, key=lambda sample: (sample.signal_date, sample.market, sample.code))
    if not ordered:
        raise ValueError("ridge samples are empty")
    if len({sample.market for sample in ordered}) != 1:
        raise ValueError("one Ridge artifact must contain exactly one market")
    feature_count = len(ordered[0].features)
    if any(len(sample.features) != feature_count for sample in ordered):
        raise ValueError("sample feature widths are inconsistent")
    weights = date_equal_weights(ordered)
    return fit_weighted_ridge(
        [sample.features for sample in ordered],
        [sample.label.net_excess_return for sample in ordered],
        weights,
        l2=FIXED_RIDGE_L2,
        signal_date_count=len({sample.signal_date for sample in ordered}),
    )


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train: tuple[RankSample, ...]
    test: tuple[RankSample, ...]
    train_dates: tuple[str, ...]
    test_dates: tuple[str, ...]
    embargoed_dates: tuple[str, ...]
    train_label_cutoff: str


def expanding_walk_forward_splits(
    samples: Iterable[RankSample],
    *,
    min_train_days: int = MIN_TRAIN_DAYS,
    test_block_days: int = TEST_BLOCK_DAYS,
    max_folds: int | None = None,
) -> tuple[WalkForwardFold, ...]:
    """Build non-overlapping expanding folds purged by actual label exit date."""

    if min_train_days <= 0 or test_block_days <= 0:
        raise ValueError("walk-forward day counts must be positive")
    if max_folds is not None and max_folds <= 0:
        raise ValueError("max_folds must be positive")
    ordered = tuple(sorted(samples, key=lambda sample: (sample.signal_date, sample.market, sample.code)))
    if not ordered:
        return ()
    if len({sample.market for sample in ordered}) != 1:
        raise ValueError("walk-forward splits must be built one market at a time")
    groups: dict[str, list[RankSample]] = defaultdict(list)
    for sample in ordered:
        groups[sample.signal_date].append(sample)
    dates = sorted(groups)

    first_test_index: int | None = None
    for candidate_index in range(min_train_days, len(dates)):
        boundary = dates[candidate_index]
        safe_dates = [
            date_text
            for date_text in dates[:candidate_index]
            if max(sample.exit_date for sample in groups[date_text]) < boundary
        ]
        if len(safe_dates) >= min_train_days:
            first_test_index = candidate_index
            break
    if first_test_index is None:
        return ()

    folds: list[WalkForwardFold] = []
    test_index = first_test_index
    while test_index + test_block_days <= len(dates):
        test_dates = tuple(dates[test_index : test_index + test_block_days])
        boundary = test_dates[0]
        prior_dates = dates[:test_index]
        safe_train_dates = tuple(
            date_text
            for date_text in prior_dates
            if max(sample.exit_date for sample in groups[date_text]) < boundary
        )
        if len(safe_train_dates) < min_train_days:
            test_index += test_block_days
            continue
        safe_set = set(safe_train_dates)
        test_set = set(test_dates)
        train_rows = tuple(sample for sample in ordered if sample.signal_date in safe_set)
        test_rows = tuple(sample for sample in ordered if sample.signal_date in test_set)
        if not train_rows or not test_rows:
            test_index += test_block_days
            continue
        embargoed = tuple(date_text for date_text in prior_dates if date_text not in safe_set)
        folds.append(
            WalkForwardFold(
                fold_id=len(folds) + 1,
                train=train_rows,
                test=test_rows,
                train_dates=safe_train_dates,
                test_dates=test_dates,
                embargoed_dates=embargoed,
                train_label_cutoff=max(sample.exit_date for sample in train_rows),
            )
        )
        if max_folds is not None and len(folds) >= max_folds:
            break
        test_index += test_block_days
    return tuple(folds)


def walk_forward_predictions(
    samples: Iterable[RankSample],
    *,
    min_train_days: int = MIN_TRAIN_DAYS,
    test_block_days: int = TEST_BLOCK_DAYS,
    max_folds: int | None = None,
) -> tuple[list[dict], tuple[WalkForwardFold, ...]]:
    """Fit only on each fold's past and emit untouched out-of-sample rows."""

    folds = expanding_walk_forward_splits(
        samples,
        min_train_days=min_train_days,
        test_block_days=test_block_days,
        max_folds=max_folds,
    )
    records: list[dict] = []
    for fold in folds:
        model = fit_date_equal_ridge(fold.train)
        for sample in fold.test:
            records.append(
                {
                    "fold_id": fold.fold_id,
                    "market": sample.market,
                    "code": sample.code,
                    "signal_date": sample.signal_date,
                    "predicted_net_excess_return": model.predict(sample.features),
                    "net_excess_return": sample.label.net_excess_return,
                    "stock_net_return": sample.label.stock_net_return,
                    "benchmark_net_return": sample.label.benchmark_net_return,
                }
            )
    return records, folds


def _average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(indexed):
        end = start + 1
        while end < len(indexed) and indexed[end][1] == indexed[start][1]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[indexed[position][0]] = average_rank
        start = end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    if left_scale <= 1e-15 or right_scale <= 1e-15:
        return None
    return numerator / (left_scale * right_scale)


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean requires values")
    return sum(values) / len(values)


def _expected_shortfall(values: Sequence[float], fraction: float = 0.10) -> float:
    if not values:
        raise ValueError("expected shortfall requires values")
    count = max(1, math.ceil(len(values) * fraction))
    return _mean(sorted(values)[:count])


def daily_ranking_metrics(records: Sequence[dict]) -> dict:
    """Rank inside each date-market cell, then weight cells equally."""

    if not records:
        return {}
    required = (
        "predicted_net_excess_return",
        "net_excess_return",
        "stock_net_return",
    )
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        if not isinstance(record, dict) or not all(_finite(record.get(field)) for field in required):
            raise ValueError("ranking record is incomplete or non-finite")
        date_text = _iso_date(record.get("signal_date"), "ranking.signal_date")
        market = str(record.get("market") or "")
        if market not in REGISTERED_BENCHMARKS:
            raise ValueError("ranking record market is invalid")
        groups[(date_text, market)].append(record)

    daily_ic: list[float] = []
    daily_top_excess: list[float] = []
    daily_top_stock: list[float] = []
    daily_top1_excess: list[float] = []
    daily_top1_stock: list[float] = []
    daily_spreads: list[float] = []
    for cell in sorted(groups):
        rows = groups[cell]
        predicted = [float(row["predicted_net_excess_return"]) for row in rows]
        realized = [float(row["net_excess_return"]) for row in rows]
        ic = _pearson(_average_ranks(predicted), _average_ranks(realized))
        if ic is not None:
            daily_ic.append(ic)
        ranked = sorted(
            rows,
            key=lambda row: (
                float(row["predicted_net_excess_return"]),
                str(row.get("market") or ""),
                str(row.get("code") or ""),
            ),
            reverse=True,
        )
        top_count = max(1, math.ceil(len(ranked) * 0.10))
        top = ranked[:top_count]
        bottom = ranked[-top_count:]
        top_excess = _mean([float(row["net_excess_return"]) for row in top])
        daily_top_excess.append(top_excess)
        daily_top_stock.append(_mean([float(row["stock_net_return"]) for row in top]))
        daily_top1_excess.append(float(ranked[0]["net_excess_return"]))
        daily_top1_stock.append(float(ranked[0]["stock_net_return"]))
        daily_spreads.append(
            top_excess - _mean([float(row["net_excess_return"]) for row in bottom])
        )

    result = {
        "test_row_count": len(records),
        "independent_test_date_count": len(groups),
        "independent_test_date_market_cell_count": len(groups),
        "distinct_test_date_count": len({date_text for date_text, _market in groups}),
        "ic_date_count": len(daily_ic),
        "validation_weighting": "signal_date_market_equal_weight_v3",
        "ranking_policy": "per_signal_date_market_expected_net_excess_desc_v3",
        "top_decile_policy": "per_signal_date_market_top_ceil_10pct_then_cell_mean_v3",
        "mean_daily_spearman_ic": round(_mean(daily_ic), 8) if daily_ic else None,
        "mean_top_decile_net_excess_return": round(_mean(daily_top_excess), 8),
        "mean_top_decile_stock_net_return": round(_mean(daily_top_stock), 8),
        "mean_top1_net_excess_return": round(_mean(daily_top1_excess), 8),
        "mean_top1_stock_net_return": round(_mean(daily_top1_stock), 8),
        "mean_top_bottom_net_excess_spread": round(_mean(daily_spreads), 8),
        "top_decile_excess_hit_rate": round(
            sum(value > 0 for value in daily_top_excess) / len(daily_top_excess), 8
        ),
        "top1_absolute_hit_rate": round(
            sum(value > 0 for value in daily_top1_stock) / len(daily_top1_stock), 8
        ),
        "top_decile_stock_expected_shortfall_10pct": round(_expected_shortfall(daily_top_stock), 8),
        "top_decile_excess_expected_shortfall_10pct": round(_expected_shortfall(daily_top_excess), 8),
    }
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


def _artifact_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_collecting_contract(
    samples: Sequence[RankSample] = (),
    *,
    validation: dict | None = None,
    fold_count: int = 0,
    collection_diagnostics: dict | None = None,
    additional_reason_codes: Sequence[str] = (),
) -> dict:
    """Publish v2 collection progress without any path to self-authorization."""

    dates = sorted({sample.signal_date for sample in samples})
    validation = dict(validation or {})
    json.dumps(validation, sort_keys=True, allow_nan=False)
    additional = [str(code) for code in additional_reason_codes if str(code)]
    collection_reason = (
        None
        if "POINT_IN_TIME_LEDGER_INVALID" in additional
        else "POINT_IN_TIME_LEDGER_EMPTY" if not samples else "POINT_IN_TIME_HISTORY_ACCUMULATING"
    )
    reason_codes = list(dict.fromkeys([
        *([collection_reason] if collection_reason else []),
        "PRODUCTION_PROMOTION_REQUIRES_SEPARATE_AUTHORITY",
        *additional,
    ]))
    identity = {
        "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
        "model_id": MODEL_ID,
        "label_version": LABEL_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "training_provenance": TRAINING_PROVENANCE,
        "benchmark_registry": REGISTERED_BENCHMARKS,
        "fixed_ridge_l2": FIXED_RIDGE_L2,
        "sample_count": len(samples),
        "signal_date_count": len(dates),
        "fold_count": int(fold_count),
        "validation": validation,
        "reason_codes": reason_codes,
    }
    if collection_diagnostics is not None:
        diagnostics = dict(collection_diagnostics)
        json.dumps(diagnostics, sort_keys=True, allow_nan=False)
        identity["collection_diagnostics"] = diagnostics
    result = {
        **identity,
        "status": "COLLECTING",
        "target": "ten_session_net_excess_return",
        "horizon_sessions": HORIZON_SESSIONS,
        "sampling_policy": "all_valid_point_in_time_rows_date_equal_weight_v2",
        "validation_method": "expanding_walk_forward_actual_exit_purge_v2",
        "minimum_train_days": MIN_TRAIN_DAYS,
        "test_block_days": TEST_BLOCK_DAYS,
        "first_signal_date": dates[0] if dates else None,
        "last_signal_date": dates[-1] if dates else None,
        "calibrated": False,
        "costs_ready": False,
        "tail_risk_ready": False,
        "participates_in_decision": False,
        "production_eligible": False,
        "probability": None,
        "expected_net_return": None,
        "expected_net_excess_return": None,
        "shadow_predictions": [],
        "reason_codes": reason_codes,
        "artifact_sha256": _artifact_hash(identity),
    }
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def block_bootstrap_confidence_intervals(
    records: Sequence[dict],
    *,
    repetitions: int = 400,
    block_size: int = 5,
) -> dict[str, Any]:
    """Deterministic moving-block intervals over chronological date-market cells."""

    if not records:
        return {}
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        groups[(str(record["signal_date"]), str(record["market"]))].append(record)
    cells = sorted(groups)
    if not cells:
        return {}
    block_size = max(1, min(int(block_size), len(cells)))
    # Reduce each complete cross-section to the quantities that are averaged
    # across cells by ``daily_ranking_metrics``.  Resampling raw rows would
    # overweight large cross-sections and, after a length-based slice, could
    # include only part of the last sampled cell.  It would also merge a cell
    # selected more than once back into one date/market group.
    cell_metrics = {
        cell: daily_ranking_metrics(groups[cell])
        for cell in cells
    }
    rng = random.Random(20260829)
    metrics: dict[str, list[float]] = defaultdict(list)
    for _ in range(max(1, int(repetitions))):
        sampled_cells: list[tuple[str, str]] = []
        while len(sampled_cells) < len(cells):
            start = rng.randrange(len(cells))
            for offset in range(block_size):
                sampled_cells.append(cells[(start + offset) % len(cells)])
                if len(sampled_cells) >= len(cells):
                    break
        sampled = [cell_metrics[cell] for cell in sampled_cells]
        ic_values = [
            float(value["mean_daily_spearman_ic"])
            for value in sampled
            if _finite(value.get("mean_daily_spearman_ic"))
        ]
        if ic_values:
            metrics["mean_daily_spearman_ic"].append(_mean(ic_values))
        for name in (
            "mean_top1_net_excess_return",
            "mean_top_decile_net_excess_return",
        ):
            metrics[name].append(_mean([float(value[name]) for value in sampled]))
        metrics["top_decile_stock_expected_shortfall_10pct"].append(
            _expected_shortfall(
                [float(value["mean_top_decile_stock_net_return"]) for value in sampled]
            )
        )
    return {
        name: {
            "lower": round(float(_percentile(values, 0.025)), 8),
            "upper": round(float(_percentile(values, 0.975)), 8),
            "confidence": 0.95,
            "method": "deterministic_moving_block_bootstrap_date_market_v1",
            "resampling_unit": "complete_date_market_cell",
            "block_size": block_size,
            "repetitions": max(1, int(repetitions)),
        }
        for name, values in sorted(metrics.items())
        if values
    }


def fit_walk_forward(
    samples: Sequence[RankSample],
    *,
    min_train_days: int = MIN_TRAIN_DAYS,
    test_block_days: int = TEST_BLOCK_DAYS,
    collection_diagnostics: dict | None = None,
) -> dict[str, Any]:
    """Publish real collection progress or an isolated Shadow validation artifact.

    Each market is fitted independently.  Walk-forward folds purge by the
    actual label exit, and the last complete date block is kept out of all
    model selection as a final holdout.  The artifact remains incapable of
    authorizing production regardless of metric values.
    """

    ordered = sorted(samples, key=lambda row: (row.signal_date, row.market, row.code))
    seen: set[tuple[str, str, str]] = set()
    for sample in ordered:
        identity = (sample.signal_date, sample.market, sample.code)
        if identity in seen:
            raise ValueError("duplicate date-market-symbol rank sample")
        seen.add(identity)
    dates = sorted({sample.signal_date for sample in ordered})
    market_date_counts = {
        market: len({sample.signal_date for sample in ordered if sample.market == market})
        for market in REGISTERED_BENCHMARKS
    }
    collection_validation = {
        "schema_version": "ten-day-rank-validation-v1",
        "metric_version": "rank-metrics-date-market-v3",
        "sample_count": len(ordered),
        "signal_date_count": len(dates),
        "market_signal_date_counts": market_date_counts,
        "actual_exit_purge": True,
        "date_market_equal_weighting": True,
        "final_untouched_holdout": True,
    }
    if not ordered or max(market_date_counts.values(), default=0) < min_train_days + test_block_days:
        return build_collecting_contract(
            ordered,
            validation=collection_validation,
            fold_count=0,
            collection_diagnostics=collection_diagnostics,
        )

    oof_records: list[dict[str, Any]] = []
    holdout_records: list[dict[str, Any]] = []
    fold_count = 0
    holdout_dates_by_market: dict[str, list[str]] = {}
    per_market: dict[str, Any] = {}
    for market in REGISTERED_BENCHMARKS:
        market_rows = [sample for sample in ordered if sample.market == market]
        market_dates = sorted({sample.signal_date for sample in market_rows})
        if len(market_dates) < min_train_days + test_block_days:
            per_market[market] = {
                "status": "COLLECTING",
                "sample_count": len(market_rows),
                "signal_date_count": len(market_dates),
            }
            continue
        holdout_dates = market_dates[-test_block_days:]
        holdout_start = holdout_dates[0]
        development = [sample for sample in market_rows if sample.signal_date < holdout_start]
        predictions, folds = walk_forward_predictions(
            development,
            min_train_days=min_train_days,
            test_block_days=test_block_days,
        )
        if not predictions or not folds:
            per_market[market] = {
                "status": "COLLECTING",
                "sample_count": len(market_rows),
                "signal_date_count": len(market_dates),
                "reason": "OUT_OF_FOLD_BLOCK_NOT_YET_AVAILABLE_AFTER_PURGE",
            }
            continue
        safe_train = [
            sample
            for sample in development
            if sample.exit_date < holdout_start
        ]
        if len({sample.signal_date for sample in safe_train}) < min_train_days:
            per_market[market] = {
                "status": "COLLECTING",
                "sample_count": len(market_rows),
                "signal_date_count": len(market_dates),
                "reason": "FINAL_HOLDOUT_PURGE_LEAVES_TOO_FEW_TRAIN_DAYS",
            }
            continue
        final_model = fit_date_equal_ridge(safe_train)
        market_holdout = [sample for sample in market_rows if sample.signal_date in set(holdout_dates)]
        market_holdout_records = [
            {
                "fold_id": "final_holdout",
                "market": sample.market,
                "code": sample.code,
                "signal_date": sample.signal_date,
                "predicted_net_excess_return": final_model.predict(sample.features),
                "net_excess_return": sample.label.net_excess_return,
                "stock_net_return": sample.label.stock_net_return,
                "benchmark_net_return": sample.label.benchmark_net_return,
            }
            for sample in market_holdout
        ]
        oof_records.extend(predictions)
        holdout_records.extend(market_holdout_records)
        fold_count += len(folds)
        holdout_dates_by_market[market] = holdout_dates
        per_market[market] = {
            "status": "SHADOW_READY",
            "sample_count": len(market_rows),
            "signal_date_count": len(market_dates),
            "fold_count": len(folds),
            "out_of_fold": daily_ranking_metrics(predictions),
            "final_holdout": daily_ranking_metrics(market_holdout_records),
        }
    if not holdout_records:
        return build_collecting_contract(
            ordered,
            validation={**collection_validation, "per_market": per_market},
            fold_count=fold_count,
            collection_diagnostics=collection_diagnostics,
        )

    validation_records = [*oof_records, *holdout_records]
    sample_lookup = {
        (sample.signal_date, sample.market, sample.code): sample for sample in ordered
    }
    regime_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in validation_records:
        sample = sample_lookup[(record["signal_date"], record["market"], record["code"])]
        regime_groups[sample.market_regime or "unknown"].append(record)
    validation = {
        **collection_validation,
        "walk_forward": daily_ranking_metrics(oof_records),
        "final_holdout": daily_ranking_metrics(holdout_records),
        "combined_shadow": daily_ranking_metrics(validation_records),
        "block_bootstrap_95pct": block_bootstrap_confidence_intervals(validation_records),
        "per_market": per_market,
        "per_regime": {
            regime: daily_ranking_metrics(records)
            for regime, records in sorted(regime_groups.items())
        },
        "holdout_dates_by_market": holdout_dates_by_market,
        "coverage": round(len(validation_records) / len(ordered), 8),
        "thresholds": {
            "minimum_independent_training_days": min_train_days,
            "minimum_final_holdout_days": test_block_days,
            "minimum_mean_top1_net_excess_return": 0.0,
            "minimum_mean_daily_spearman_ic": 0.0,
            "minimum_coverage": 0.70,
            "maximum_top_decile_stock_expected_shortfall_10pct": -0.15,
            "promotion_authority": "separate_manual_governance_only",
        },
    }
    final_metrics = validation["final_holdout"]
    diagnostics = dict(collection_diagnostics or {})
    data_completeness_gate_passed = bool(
        collection_diagnostics is not None
        and not diagnostics.get("error_type")
        and int(diagnostics.get("excluded_missing_outcome_batch_count", 0)) == 0
        and int(diagnostics.get("excluded_invalid_revision_count", 0)) == 0
        and int(diagnostics.get("excluded_unbound_snapshot_count", 0)) == 0
        and int(diagnostics.get("excluded_missing_rank_label_count", 0)) == 0
        and int(diagnostics.get("excluded_missing_snapshot_count", 0)) == 0
        and int(diagnostics.get("excluded_invalid_feature_count", 0)) == 0
        and int(diagnostics.get("excluded_pending_data_outcome_count", 0)) == 0
        and int(diagnostics.get("excluded_other_unsettled_outcome_count", 0)) == 0
        and int(diagnostics.get("excluded_data_incomplete_market_cell_count", 0)) == 0
    )
    promotion_gate_passed = bool(
        _finite(final_metrics.get("mean_top1_net_excess_return"))
        and float(final_metrics["mean_top1_net_excess_return"]) > 0
        and _finite(final_metrics.get("mean_daily_spearman_ic"))
        and float(final_metrics["mean_daily_spearman_ic"]) > 0
        and _finite(final_metrics.get("top_decile_stock_expected_shortfall_10pct"))
        and float(final_metrics["top_decile_stock_expected_shortfall_10pct"]) >= -0.15
        and validation["coverage"] >= 0.70
        and data_completeness_gate_passed
    )
    validation["data_completeness_gate_passed"] = data_completeness_gate_passed
    identity = {
        "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
        "model_id": MODEL_ID,
        "label_version": LABEL_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "training_provenance": TRAINING_PROVENANCE,
        "benchmark_registry": REGISTERED_BENCHMARKS,
        "fixed_ridge_l2": FIXED_RIDGE_L2,
        "sample_count": len(ordered),
        "signal_date_count": len(dates),
        "fold_count": fold_count,
        "validation": validation,
        "out_of_fold_predictions": validation_records,
        "reason_codes": [
            "SHADOW_VALIDATION_ONLY",
            "PRODUCTION_PROMOTION_REQUIRES_SEPARATE_AUTHORITY",
        ],
    }
    if collection_diagnostics is not None:
        diagnostics = dict(collection_diagnostics)
        json.dumps(diagnostics, sort_keys=True, allow_nan=False)
        identity["collection_diagnostics"] = diagnostics
    result = {
        **identity,
        "status": "SHADOW_READY",
        "target": "ten_session_net_excess_return",
        "horizon_sessions": HORIZON_SESSIONS,
        "sampling_policy": "all_valid_point_in_time_rows_date_market_equal_weight_v3",
        "validation_method": "expanding_walk_forward_actual_exit_purge_final_holdout_v3",
        "minimum_train_days": min_train_days,
        "test_block_days": test_block_days,
        "first_signal_date": dates[0],
        "last_signal_date": dates[-1],
        "calibrated": False,
        "costs_ready": True,
        "tail_risk_ready": True,
        "participates_in_decision": False,
        "production_eligible": False,
        "promotion_gate_passed": promotion_gate_passed,
        "promotion_authorized": False,
        "probability": None,
        "expected_net_return": None,
        "expected_net_excess_return": None,
        "shadow_predictions": validation_records,
        "reason_codes": identity["reason_codes"],
        "artifact_sha256": _artifact_hash(identity),
    }
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


__all__ = [
    "ARTIFACT_CONTRACT_VERSION",
    "ExcessReturnLabel",
    "FIXED_RIDGE_L2",
    "HORIZON_SESSIONS",
    "LABEL_VERSION",
    "MIN_TRAIN_DAYS",
    "MODEL_ID",
    "REGISTERED_BENCHMARKS",
    "RankSample",
    "RidgeModel",
    "TEST_BLOCK_DAYS",
    "TRAINING_PROVENANCE",
    "WalkForwardFold",
    "build_collecting_contract",
    "block_bootstrap_confidence_intervals",
    "daily_ranking_metrics",
    "date_equal_weights",
    "expanding_walk_forward_splits",
    "fit_date_equal_ridge",
    "fit_weighted_ridge",
    "fit_walk_forward",
    "ten_session_excess_label",
    "walk_forward_predictions",
]
