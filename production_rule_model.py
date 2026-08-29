"""Auditable ten-session production qualification rules.

The calibrated ``global_decision`` remains the only probability-bearing
contract. This module consumes its evaluated candidate ledger and applies two
deterministic qualification tracks: the established event-catalyst rules and
a stricter quality-technical path that does not depend on the bounded official
filing enrichment sample. Shared execution, input-quality and material-risk
gates remain mandatory for both tracks. A qualification score is a rule match
score, never a probability or expected return.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "production-rule-10d-v1"
DECISION_SCOPE = "global_10d_bounded_recall"
ACTION_BASIS = "dual_track_candidate_qualification_v4"
RULE_MODEL_ID = "ten-day-audited-rule-ensemble-v4"
SCORE_KIND = "RULE_QUALIFICATION_SCORE"
HORIZON_TRADE_DAYS = 10
ACTION_PICK = "QUALIFIED_PICK"
ACTION_NONE = "NO_QUALIFIED_PICK"
TRACK_EVENT_CATALYST = "event_catalyst"
TRACK_QUALITY_TECHNICAL = "quality_technical"
RULE_INPUTS_CONTRACT_VERSION = "production-rule-inputs-v3"
LEGACY_RULE_INPUTS_CONTRACT_VERSION = "production-rule-inputs-v2"
SUPPORTED_RULE_INPUTS_CONTRACT_VERSIONS = frozenset(
    {LEGACY_RULE_INPUTS_CONTRACT_VERSION, RULE_INPUTS_CONTRACT_VERSION}
)
HORIZON_RANGE_CONTRACT_VERSION = "horizon-range-v1"
HORIZON_RANGE_METHOD_ID = "realized-vol-drift-shadow-v1"
TEN_DAY_TRADE_PLAN_CONTRACT_VERSION = "ten-day-trade-plan-v2"
LEGACY_TEN_DAY_TRADE_PLAN_CONTRACT_VERSION = "ten-day-trade-plan-v1"

MARKET_POLICY = {
    "a_share": {"minimum_legacy": 64.0, "maximum_downside": 8.0, "minimum_upside": 5.0},
    "hk": {"minimum_legacy": 63.0, "maximum_downside": 8.0, "minimum_upside": 5.0},
    "us": {"minimum_legacy": 64.0, "maximum_downside": 10.0, "minimum_upside": 6.0},
}
MAX_V2_RANK_FRACTION = 0.20
MIN_RISK_REWARD_RATIO = 1.20

QUALITY_POLICY = {
    "a_share": {"minimum_legacy": 64.0, "maximum_downside": 6.0, "minimum_upside": 6.0},
    "hk": {"minimum_legacy": 67.0, "maximum_downside": 6.0, "minimum_upside": 6.0},
    "us": {"minimum_legacy": 67.0, "maximum_downside": 7.5, "minimum_upside": 6.5},
}
QUALITY_MAX_V2_RANK_FRACTION = 0.10
QUALITY_MIN_DATA_QUALITY = 95.0
QUALITY_MIN_RISK_REWARD_RATIO = 1.50
QUALITY_MIN_QUALIFICATION_SCORE = 72.0

# Model availability does not participate in either deterministic track. The
# quality track is intentionally independent from the bounded official filing
# enrichment sample. It may waive only the two event-enrichment availability
# blockers; every shared execution, data and material-risk blocker still
# applies.
QUALITY_EVENT_ENRICHMENT_BLOCKERS = frozenset(
    {"EVENT_CANDIDATE_NOT_SCANNED", "VERIFIED_POSITIVE_EVENT_MISSING"}
)
MODEL_AVAILABILITY_BLOCKERS = frozenset(
    {"TEN_DAY_MODEL_NOT_READY", "TEN_DAY_PREDICTION_MISSING"}
)

CANDIDATE_SNAPSHOT_FIELDS = (
    "code", "symbol", "name", "role", "price", "entry_price", "signal_price",
    "change_pct", "current_change_pct", "signal_change_pct", "realtime",
    "amount_yi", "amount_currency", "turnover_pct", "vol_ratio", "float_mcap_yi",
    "market_liquidity_percentile", "market_cap_percentile", "reason_tags", "theme_tags",
    "candidate_lineage", "score", "pre_score", "screen_score", "screen_rank",
    "score_tier", "technical_screen_eligible", "legacy_complete", "deep_scored",
    "legacy_rank", "confidence", "recommendation_degree", "legacy", "v2",
    "analysis_projects", "data_quality", "risk_items", "risk_flags", "decision_gates",
    "execution_state", "estimated_2d_range", "estimated_10d_range", "estimated_2w_range",
    "stop_loss", "take_profit_reference", "reasons",
)
RULE_INPUT_ROW_FIELDS = (
    "name",
    "blocker_codes",
    "legacy_signal",
    "legacy_recommendation_degree",
    "v2_rank",
    "v2_rank_universe_size",
    "event_candidate_scanned",
    "verified_positive_event_ids",
    "entry_price",
    "calendar_id",
    "calendar_version",
    "entry_trade_date",
    "forecast_end_trade_date",
)

_SOURCE_FROM_SNAPSHOT = object()
_CANDIDATE_SNAPSHOT_FROM_SOURCE = object()


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _round_rule_number(value: float, digits: int = 2) -> float:
    """Match the Worker rebuild's IEEE-754 ``Math.round`` policy exactly."""

    factor = 10 ** digits
    rounded = math.floor((float(value) + 2.220446049250313e-16) * factor + 0.5) / factor
    return 0.0 if rounded == 0 else rounded


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _horizon_range_text(low_pct: float, high_pct: float) -> str:
    return f"{float(low_pct):+.1f}% ~ {float(high_pct):+.1f}%"


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return dt.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _canonical_horizon_range(value: Any) -> dict[str, Any] | None:
    """Validate and normalize the auditable ten-session scenario contract."""

    if not isinstance(value, Mapping):
        return None
    low_pct = value.get("low_pct")
    high_pct = value.get("high_pct")
    observations = value.get("source_observations")
    if (
        value.get("contract_version") != HORIZON_RANGE_CONTRACT_VERSION
        or value.get("horizon_trade_days") != HORIZON_TRADE_DAYS
        or value.get("method_id") != HORIZON_RANGE_METHOD_ID
        or value.get("calibrated") is not False
        or not _finite_number(low_pct)
        or not _finite_number(high_pct)
        or not float(low_pct) < 0 < float(high_pct)
        or type(observations) is not int
        or not 0 <= observations <= 20
        or value.get("text") != _horizon_range_text(float(low_pct), float(high_pct))
    ):
        return None
    start = value.get("source_window_start_date")
    end = value.get("source_window_end_date")
    if (start is None) != (end is None):
        return None
    if start is not None and (
        not _valid_iso_date(start)
        or not _valid_iso_date(end)
        or start > end
    ):
        return None
    result = {
        "contract_version": HORIZON_RANGE_CONTRACT_VERSION,
        "low_pct": _round_rule_number(float(low_pct), 2),
        "high_pct": _round_rule_number(float(high_pct), 2),
        "text": _horizon_range_text(float(low_pct), float(high_pct)),
        "horizon_trade_days": HORIZON_TRADE_DAYS,
        "method_id": HORIZON_RANGE_METHOD_ID,
        "calibrated": False,
        "source_observations": observations,
    }
    if start is not None:
        result["source_window_start_date"] = start
        result["source_window_end_date"] = end
    return result


def _candidate_rows(section: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    decision = section.get("decision") or {}
    rows: list[Any] = [
        *(section.get("_candidate_pool") or []),
        decision.get("primary") if isinstance(decision, Mapping) else None,
        decision.get("blocked_candidate") if isinstance(decision, Mapping) else None,
        *((decision.get("watchlist") or []) if isinstance(decision, Mapping) else []),
    ]
    return [row for row in rows if isinstance(row, Mapping)]


def _source_candidate(snapshot: Mapping[str, Any], market: str | None, code: str | None) -> Mapping[str, Any] | None:
    if not market or not code:
        return None
    section = ((snapshot.get("markets") or {}).get(market) or {})
    if not isinstance(section, Mapping):
        return None
    wanted = code.upper()
    for row in _candidate_rows(section):
        if str(row.get("code") or row.get("symbol") or "").upper() == wanted:
            return row
    return None


def _compact_candidate_snapshot(candidate: Mapping[str, Any] | None, market: str | None) -> dict[str, Any] | None:
    if not isinstance(candidate, Mapping):
        return None
    result = {
        key: copy.deepcopy(candidate.get(key))
        for key in CANDIDATE_SNAPSHOT_FIELDS
        if key in candidate
    }
    result.update({
        "candidate_snapshot_version": "production-qualified-candidate-v1",
        "market_key": market,
        "research_only": False,
        "rule_qualified": True,
    })
    return result


def _stable_qualification_id(snapshot: Mapping[str, Any], market: str | None, code: str | None) -> str:
    automation = snapshot.get("automation") or {}
    scheduled_slot = automation.get("scheduled_slot") if isinstance(automation, Mapping) else None
    identity = "|".join(
        str(value or "")
        for value in (
            CONTRACT_VERSION,
            RULE_MODEL_ID,
            scheduled_slot or snapshot.get("target_date") or snapshot.get("signal_date"),
            snapshot.get("target_date") or snapshot.get("signal_date"),
            market,
            code,
        )
    )
    return f"qual_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def _raw_data_quality(row: Mapping[str, Any], candidate: Mapping[str, Any] | None) -> float | None:
    quality = candidate.get("data_quality") if isinstance(candidate, Mapping) else None
    value = quality.get("score") if isinstance(quality, Mapping) else None
    if _finite_number(value):
        return _clamp(float(value))
    component = (row.get("priority_components") or {}).get("data_quality")
    if _finite_number(component):
        return _clamp(float(component) / 20.0 * 100.0)
    return None


def _source_data_quality(candidate: Mapping[str, Any] | None) -> float | None:
    quality = candidate.get("data_quality") if isinstance(candidate, Mapping) else None
    value = quality.get("score") if isinstance(quality, Mapping) else None
    return _clamp(float(value)) if _finite_number(value) else None


def _ten_day_trade_plan(
    row: Mapping[str, Any],
    candidate: Mapping[str, Any] | None,
    qualification_track: str | None,
    input_contract_version: str,
) -> dict[str, Any] | None:
    """Build a deterministic review plan from already-frozen evidence.

    The entry band and 10% single-name cap are execution guardrails, not a
    personalized allocation or return forecast. No browser-side price or stop
    inference is needed because the exact reference evidence travels with the
    qualified row.
    """

    price = row.get("entry_price")
    if not _finite_number(price) or float(price) <= 0:
        return None
    price_value = float(price)
    candidate = candidate if isinstance(candidate, Mapping) else {}
    realtime = candidate.get("realtime")
    realtime = realtime if isinstance(realtime, Mapping) else {}
    estimated_range = row.get("estimated_10d_range")
    estimated_range = estimated_range if isinstance(estimated_range, Mapping) else {}
    low_pct = estimated_range.get("low_pct")
    high_pct = estimated_range.get("high_pct")
    stop_loss = candidate.get("stop_loss")
    stop_source = "candidate_stop_loss"
    if not _finite_number(stop_loss) or float(stop_loss) <= 0:
        stop_loss = (
            price_value * (1.0 + float(low_pct) / 100.0)
            if _finite_number(low_pct) and float(low_pct) < 0
            else None
        )
        stop_source = "ten_day_scenario_lower_bound"
    target = candidate.get("take_profit_reference")
    target_source = "candidate_take_profit_reference"
    if not _finite_number(target) or float(target) <= 0:
        target = (
            price_value * (1.0 + float(high_pct) / 100.0)
            if _finite_number(high_pct) and float(high_pct) > 0
            else None
        )
        target_source = "ten_day_scenario_upper_bound"
    currency = {"a_share": "CNY", "hk": "HKD", "us": "USD"}.get(_text(row.get("market")))
    review_end = _text(row.get("forecast_end_trade_date"))
    current_provenance = input_contract_version == RULE_INPUTS_CONTRACT_VERSION
    plan = {
        "contract_version": (
            TEN_DAY_TRADE_PLAN_CONTRACT_VERSION
            if current_provenance
            else LEGACY_TEN_DAY_TRADE_PLAN_CONTRACT_VERSION
        ),
        "status": "REVIEW_REQUIRED",
        "horizon_trade_days": HORIZON_TRADE_DAYS,
        "reference_quote": {
            "price": _round_rule_number(price_value, 4),
            "currency": currency,
            "source": realtime.get("source"),
            "source_as_of": realtime.get("source_as_of"),
            "quote_status": realtime.get("quote_status") or realtime.get("session_label"),
            "kind": "published_snapshot_quote",
        },
        "entry_zone": {
            "low": _round_rule_number(price_value * 0.99, 4),
            "high": _round_rule_number(price_value * 1.005, 4),
            "currency": currency,
        },
        "entry_trade_date": _text(row.get("entry_trade_date")),
        "invalidation": {
            "price": _round_rule_number(float(stop_loss), 4) if _finite_number(stop_loss) else None,
            "currency": currency,
            "source": stop_source if _finite_number(stop_loss) else None,
        },
        "target": {
            "price": _round_rule_number(float(target), 4) if _finite_number(target) else None,
            "currency": currency,
            "source": target_source if _finite_number(target) else None,
        },
        "position_limit": {
            "max_single_name_weight_pct": 10.0,
            "policy": "strategy_safety_cap_not_personalized",
        },
        "catalyst_expiry_date": review_end if qualification_track == TRACK_EVENT_CATALYST else None,
        "review_end_trade_date": review_end,
        "exit_rules": [
            "EXIT_IF_INVALIDATION_PRICE_BREACHED",
            "REVIEW_AT_TENTH_SESSION_CLOSE",
            "DO_NOT_CHASE_ABOVE_ENTRY_ZONE",
        ],
        "is_personalized_advice": False,
    }
    if current_provenance:
        scenario_range = _canonical_horizon_range(estimated_range)
        if scenario_range is None:
            return None
        plan["scenario_range"] = scenario_range
    return plan


def freeze_production_rule_input_row(
    row: Mapping[str, Any],
    index: int,
    contract_version: str = RULE_INPUTS_CONTRACT_VERSION,
) -> dict[str, Any]:
    """Project one global row to exactly the fields consumed by current V4."""

    result = {
        "input_index": index,
        "market": _text(row.get("market")),
        "code": _text(row.get("code") or row.get("symbol")),
    }
    for key in RULE_INPUT_ROW_FIELDS:
        if key in row:
            result[key] = copy.deepcopy(row.get(key))
    components = row.get("priority_components")
    if isinstance(components, Mapping) and "data_quality" in components:
        result["priority_components"] = {
            "data_quality": copy.deepcopy(components.get("data_quality")),
        }
    estimated_range = row.get("estimated_10d_range")
    if isinstance(estimated_range, Mapping):
        range_fields = (
            ("low_pct", "high_pct")
            if contract_version == LEGACY_RULE_INPUTS_CONTRACT_VERSION
            else (
                "contract_version", "low_pct", "high_pct", "text",
                "horizon_trade_days", "method_id", "calibrated",
                "source_observations", "source_window_start_date",
                "source_window_end_date",
            )
        )
        result["estimated_10d_range"] = {
            key: copy.deepcopy(estimated_range.get(key))
            for key in range_fields
            if key in estimated_range
        }
    return result


def _evaluate_candidate(
    snapshot: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    source_candidate_override: Any = _SOURCE_FROM_SNAPSHOT,
    qualified_candidate_snapshot: Any = _CANDIDATE_SNAPSHOT_FROM_SOURCE,
    input_contract_version: str = RULE_INPUTS_CONTRACT_VERSION,
) -> dict[str, Any]:
    source_blockers = row.get("blocker_codes")
    shared_source_blockers = (
        _dedupe([str(code) for code in source_blockers if str(code) not in MODEL_AVAILABILITY_BLOCKERS])
        if isinstance(source_blockers, list)
        else ["SOURCE_BLOCKER_CODES_INVALID"]
    )
    catalyst_blockers = list(shared_source_blockers)
    quality_blockers = [
        code for code in shared_source_blockers
        if code not in QUALITY_EVENT_ENRICHMENT_BLOCKERS
    ]

    def block_both(code: str) -> None:
        catalyst_blockers.append(code)
        quality_blockers.append(code)

    market = _text(row.get("market"))
    code = _text(row.get("code") or row.get("symbol"))
    name = _text(row.get("name"))
    policy = MARKET_POLICY.get(market or "")
    quality_policy = QUALITY_POLICY.get(market or "")
    if not market or not code:
        block_both("CANDIDATE_IDENTITY_INVALID")
    if policy is None or quality_policy is None:
        block_both("MARKET_POLICY_MISSING")
        policy = {"minimum_legacy": 100.0, "maximum_downside": 0.0, "minimum_upside": 100.0}
        quality_policy = {
            "minimum_legacy": 100.0,
            "maximum_downside": 0.0,
            "minimum_upside": 100.0,
        }

    source_candidate = (
        _source_candidate(snapshot, market, code)
        if source_candidate_override is _SOURCE_FROM_SNAPSHOT
        else source_candidate_override
    )
    if source_candidate is None:
        block_both("CANDIDATE_SNAPSHOT_MISSING")

    # ``legacy_signal`` is a market-level decision: one failed Legacy primary
    # can set it to NO_TRADE for every candidate in that market. Requiring it
    # here made the independent production track reject otherwise valid
    # candidate-level evidence. Keep it for provenance; the per-stock Legacy
    # recommendation threshold below remains a hard gate.
    legacy_signal = _text(row.get("legacy_signal"))
    recommendation = row.get("legacy_recommendation_degree")
    if not _finite_number(recommendation):
        recommendation_value = 0.0
        block_both("LEGACY_RECOMMENDATION_INVALID")
    else:
        recommendation_value = _clamp(float(recommendation))
        if recommendation_value < float(policy["minimum_legacy"]):
            catalyst_blockers.append("LEGACY_RECOMMENDATION_BELOW_THRESHOLD")
        if recommendation_value < float(quality_policy["minimum_legacy"]):
            quality_blockers.append("QUALITY_LEGACY_BELOW_THRESHOLD")

    rank = row.get("v2_rank")
    universe_size = row.get("v2_rank_universe_size")
    rank_valid = (
        _finite_number(rank)
        and _finite_number(universe_size)
        and float(universe_size) >= 1
        and 1 <= float(rank) <= float(universe_size)
    )
    if not rank_valid:
        rank_value = universe_value = rank_fraction = None
        v2_strength = 0.0
        block_both("V2_RANK_INVALID")
    else:
        rank_value = float(rank)
        universe_value = float(universe_size)
        rank_fraction = rank_value / universe_value
        v2_strength = _clamp((universe_value - rank_value + 1.0) / universe_value * 100.0)
        if rank_fraction > MAX_V2_RANK_FRACTION:
            catalyst_blockers.append("V2_TOP_PERCENTILE_REQUIRED")
        if rank_fraction > QUALITY_MAX_V2_RANK_FRACTION:
            quality_blockers.append("QUALITY_V2_TOP_DECILE_REQUIRED")

    quality_score = _raw_data_quality(row, source_candidate)
    if quality_score is None:
        quality_score = 0.0
        block_both("DATA_QUALITY_SCORE_INVALID")
    elif quality_score < QUALITY_MIN_DATA_QUALITY:
        quality_blockers.append("QUALITY_DATA_QUALITY_BELOW_THRESHOLD")

    event_scanned = row.get("event_candidate_scanned") is True
    event_ids_raw = row.get("verified_positive_event_ids")
    event_ids = _dedupe([str(value) for value in event_ids_raw if _text(value)]) if isinstance(event_ids_raw, list) else []
    if not event_scanned:
        catalyst_blockers.append("EVENT_CANDIDATE_NOT_SCANNED")
    if not event_ids:
        catalyst_blockers.append("VERIFIED_POSITIVE_EVENT_MISSING")
    event_strength = min(100.0, 80.0 + 5.0 * len(event_ids)) if event_scanned and event_ids else 0.0

    estimated_range = row.get("estimated_10d_range")
    low_pct = estimated_range.get("low_pct") if isinstance(estimated_range, Mapping) else None
    high_pct = estimated_range.get("high_pct") if isinstance(estimated_range, Mapping) else None
    range_valid = _finite_number(low_pct) and _finite_number(high_pct) and float(low_pct) < 0 < float(high_pct)
    canonical_range = (
        _canonical_horizon_range(estimated_range)
        if input_contract_version == RULE_INPUTS_CONTRACT_VERSION
        else None
    )
    if not range_valid:
        low_value = high_value = downside = ratio = None
        risk_reward_strength = 0.0
        block_both("TEN_DAY_RANGE_INVALID")
    else:
        low_value = float(low_pct)
        high_value = float(high_pct)
        downside = abs(low_value)
        ratio = high_value / downside
        if high_value < float(policy["minimum_upside"]):
            catalyst_blockers.append("TEN_DAY_UPSIDE_BELOW_THRESHOLD")
        if downside > float(policy["maximum_downside"]):
            catalyst_blockers.append("TEN_DAY_DOWNSIDE_ABOVE_LIMIT")
        if ratio < MIN_RISK_REWARD_RATIO:
            catalyst_blockers.append("RISK_REWARD_BELOW_THRESHOLD")
        if high_value < float(quality_policy["minimum_upside"]):
            quality_blockers.append("QUALITY_TEN_DAY_UPSIDE_BELOW_THRESHOLD")
        if downside > float(quality_policy["maximum_downside"]):
            quality_blockers.append("QUALITY_TEN_DAY_DOWNSIDE_ABOVE_LIMIT")
        if ratio < QUALITY_MIN_RISK_REWARD_RATIO:
            quality_blockers.append("QUALITY_RISK_REWARD_BELOW_THRESHOLD")
        risk_reward_strength = _clamp(ratio / 2.0 * 100.0)
        if input_contract_version == RULE_INPUTS_CONTRACT_VERSION and canonical_range is None:
            block_both("TEN_DAY_RANGE_PROVENANCE_INVALID")

    components = {
        "legacy_recommendation": _round_rule_number(recommendation_value * 0.30, 2),
        "v2_rank_strength": _round_rule_number(v2_strength * 0.30, 2),
        "data_quality": _round_rule_number(quality_score * 0.15, 2),
        "verified_event_evidence": _round_rule_number(event_strength * 0.15, 2),
        "risk_reward_scenario": _round_rule_number(risk_reward_strength * 0.10, 2),
    }
    qualification_score = _round_rule_number(_clamp(sum(components.values())), 2)
    if qualification_score < QUALITY_MIN_QUALIFICATION_SCORE:
        quality_blockers.append("QUALITY_QUALIFICATION_SCORE_BELOW_THRESHOLD")

    catalyst_blockers = _dedupe(catalyst_blockers)
    quality_blockers = _dedupe(quality_blockers)
    track_evaluations = [
        {
            "track": TRACK_EVENT_CATALYST,
            "status": "PASS" if not catalyst_blockers else "FAIL",
            "blocker_codes": catalyst_blockers,
        },
        {
            "track": TRACK_QUALITY_TECHNICAL,
            "status": "PASS" if not quality_blockers else "FAIL",
            "blocker_codes": quality_blockers,
        },
    ]
    qualification_track = next(
        (item["track"] for item in track_evaluations if item["status"] == "PASS"),
        None,
    )
    qualified = qualification_track is not None
    blockers = [] if qualified else _dedupe(catalyst_blockers + quality_blockers)
    result = {
        "market": market,
        "code": code,
        "name": name,
        "status": "QUALIFIED" if qualified else "REJECTED",
        "qualification_track": qualification_track,
        "track_evaluations": track_evaluations,
        "rule_model_id": RULE_MODEL_ID,
        "score_kind": SCORE_KIND,
        "qualification_score": qualification_score,
        "score_components": components,
        "probability": None,
        "probability_status": "NOT_APPLICABLE",
        "calibrated": False,
        "expected_net_utility": None,
        "legacy_signal": legacy_signal,
        "legacy_recommendation_degree": _round_rule_number(recommendation_value, 2) if _finite_number(recommendation) else None,
        "v2_rank": int(rank_value) if rank_valid else None,
        "v2_rank_universe_size": int(universe_value) if rank_valid else None,
        "v2_rank_fraction": _round_rule_number(rank_fraction, 4) if rank_fraction is not None else None,
        "data_quality_score": _round_rule_number(quality_score, 2),
        "event_candidate_scanned": event_scanned,
        "verified_positive_event_ids": event_ids,
        "entry_price": float(row["entry_price"]) if _finite_number(row.get("entry_price")) and float(row["entry_price"]) > 0 else None,
        "calendar_id": _text(row.get("calendar_id")),
        "calendar_version": _text(row.get("calendar_version")),
        "entry_trade_date": _text(row.get("entry_trade_date")),
        "forecast_end_trade_date": _text(row.get("forecast_end_trade_date")),
        "estimated_10d_range": copy.deepcopy(canonical_range) if canonical_range is not None else {
            "low_pct": _round_rule_number(low_value, 2) if low_value is not None else None,
            "high_pct": _round_rule_number(high_value, 2) if high_value is not None else None,
            "horizon_trade_days": HORIZON_TRADE_DAYS,
        },
        "risk_reward": {
            "upside_pct": _round_rule_number(high_value, 2) if high_value is not None else None,
            "downside_pct": _round_rule_number(downside, 2) if downside is not None else None,
            "ratio": _round_rule_number(ratio, 2) if ratio is not None else None,
        },
        "blocker_codes": blockers,
    }
    if qualified:
        result["qualification_id"] = _stable_qualification_id(snapshot, market, code)
        result["candidate_snapshot"] = (
            _compact_candidate_snapshot(source_candidate, market)
            if qualified_candidate_snapshot is _CANDIDATE_SNAPSHOT_FROM_SOURCE
            else copy.deepcopy(qualified_candidate_snapshot)
            if isinstance(qualified_candidate_snapshot, Mapping)
            else None
        )
        result["ten_day_trade_plan"] = _ten_day_trade_plan(
            result,
            result.get("candidate_snapshot") or source_candidate,
            qualification_track,
            input_contract_version,
        )
    return result


def production_rule_inputs_sha256(inputs: Mapping[str, Any]) -> str | None:
    """Hash every frozen input field except the hash itself using canonical JSON."""

    if not isinstance(inputs, Mapping):
        return None
    payload = {
        str(key): copy.deepcopy(value)
        for key, value in inputs.items()
        if key != "ledger_sha256"
    }
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(encoded).hexdigest()


def build_production_rule_inputs(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze the smallest self-contained ledger needed to reproduce V4.

    Each global evaluated row is reduced to fields the rules consume, plus
    source-candidate presence and raw data quality.  The substantially larger
    public candidate snapshot is retained solely for rows that qualify.
    """

    global_decision = snapshot.get("global_decision")
    global_decision = global_decision if isinstance(global_decision, Mapping) else {}
    raw_rows = global_decision.get("evaluated_candidates")
    source_rows = raw_rows if isinstance(raw_rows, list) else []
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows):
        if not isinstance(row, Mapping):
            continue
        entry = freeze_production_rule_input_row(
            row,
            index,
            RULE_INPUTS_CONTRACT_VERSION,
        )
        market = entry.get("market")
        code = entry.get("code")
        source_candidate = _source_candidate(snapshot, market, code)
        entry.update({
            "source_candidate_present": source_candidate is not None,
            "source_data_quality_score": _source_data_quality(source_candidate),
        })
        evaluated = _evaluate_candidate(
            snapshot,
            entry,
            input_contract_version=RULE_INPUTS_CONTRACT_VERSION,
        )
        if evaluated.get("status") == "QUALIFIED":
            entry["candidate_snapshot"] = copy.deepcopy(evaluated.get("candidate_snapshot"))
        rows.append(entry)
    result: dict[str, Any] = {
        "contract_version": RULE_INPUTS_CONTRACT_VERSION,
        "action_basis": ACTION_BASIS,
        "rule_model_id": RULE_MODEL_ID,
        "evaluated_candidate_count": len(source_rows),
        "rows": rows,
    }
    result["ledger_sha256"] = production_rule_inputs_sha256(result)
    return result


def _rule_input_ledger(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    inputs = snapshot.get("production_rule_inputs")
    return inputs if isinstance(inputs, Mapping) else build_production_rule_inputs(snapshot)


def _evaluate_from_rule_input(
    snapshot: Mapping[str, Any],
    entry: Mapping[str, Any] | None,
    index: int,
    input_contract_version: str,
) -> dict[str, Any]:
    row = entry if isinstance(entry, Mapping) else {}
    identity_matches = bool(isinstance(entry, Mapping) and entry.get("input_index") == index)
    source_present = identity_matches and entry.get("source_candidate_present") is True
    source_candidate = None
    if source_present:
        source_candidate = {
            "data_quality": {"score": entry.get("source_data_quality_score")},
        }
    candidate_snapshot = (
        entry.get("candidate_snapshot")
        if identity_matches and "candidate_snapshot" in entry
        else None
    )
    return _evaluate_candidate(
        snapshot,
        row,
        source_candidate_override=source_candidate,
        qualified_candidate_snapshot=candidate_snapshot,
        input_contract_version=input_contract_version,
    )


def build_production_decision(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return one market-isolated, evidence-backed rule candidate or abstain."""
    global_decision = snapshot.get("global_decision")
    global_decision = global_decision if isinstance(global_decision, Mapping) else {}
    rows = global_decision.get("evaluated_candidates")
    input_ledger = _rule_input_ledger(snapshot)
    input_rows = input_ledger.get("rows")
    input_rows = input_rows if isinstance(input_rows, list) else []
    input_contract_version = _text(input_ledger.get("contract_version")) or RULE_INPUTS_CONTRACT_VERSION
    evaluated = [
        _evaluate_from_rule_input(
            snapshot,
            entry,
            index,
            input_contract_version,
        )
        for index, entry in enumerate(input_rows)
        if isinstance(entry, Mapping)
    ]
    evaluated.sort(key=lambda row: (
        -float(row.get("qualification_score") or 0.0),
        str(row.get("market") or ""),
        str(row.get("code") or ""),
    ))
    qualified = [row for row in evaluated if row.get("status") == "QUALIFIED"]
    primary = copy.deepcopy(qualified[0]) if qualified else None
    blockers = [] if primary else ["NO_RULE_CANDIDATE_PASSED"]
    if not isinstance(rows, list):
        blockers.insert(0, "EVALUATED_CANDIDATES_MISSING")
    return {
        "contract_version": CONTRACT_VERSION,
        "decision_scope": DECISION_SCOPE,
        "horizon_trade_days": HORIZON_TRADE_DAYS,
        "action": ACTION_PICK if primary else ACTION_NONE,
        "action_basis": ACTION_BASIS,
        "rule_model_id": RULE_MODEL_ID,
        "score_kind": SCORE_KIND,
        "score_disclaimer": "0-100 分为规则资格匹配分，不是上涨概率、收益预测或买入承诺。",
        "probability_status": "NOT_APPLICABLE",
        "probability": None,
        "calibrated": False,
        "expected_net_utility": None,
        "source_global_contract_version": global_decision.get("contract_version"),
        "source_global_action": global_decision.get("action"),
        "source_rule_inputs_contract_version": input_ledger.get("contract_version"),
        "source_rule_inputs_sha256": production_rule_inputs_sha256(input_ledger),
        "source_rule_input_count": len(input_rows),
        "generated_at": snapshot.get("generated_at"),
        "signal_date": snapshot.get("signal_date"),
        "primary": primary,
        "qualified_candidates": [copy.deepcopy(row) for row in qualified],
        "qualified_candidate_count": len(qualified),
        "rejected_candidate_count": len(evaluated) - len(qualified),
        "evaluated_candidate_count": len(evaluated),
        "evaluated_candidates": evaluated,
        "blocker_codes": blockers,
        "policy": {
            "market_thresholds": copy.deepcopy(MARKET_POLICY),
            "legacy_market_action": "DIAGNOSTIC_ONLY",
            "candidate_level_legacy_threshold_required": True,
            "maximum_v2_rank_fraction": MAX_V2_RANK_FRACTION,
            "verified_positive_event_required": False,
            "minimum_risk_reward_ratio": MIN_RISK_REWARD_RATIO,
            "score_weights": {
                "legacy_recommendation": 0.30,
                "v2_rank_strength": 0.30,
                "data_quality": 0.15,
                "verified_event_evidence": 0.15,
                "risk_reward_scenario": 0.10,
            },
            "tracks": {
                TRACK_EVENT_CATALYST: {
                    "market_thresholds": copy.deepcopy(MARKET_POLICY),
                    "verified_positive_event_required": True,
                    "event_scan_required": True,
                    "maximum_v2_rank_fraction": MAX_V2_RANK_FRACTION,
                    "minimum_risk_reward_ratio": MIN_RISK_REWARD_RATIO,
                    "minimum_qualification_score": None,
                },
                TRACK_QUALITY_TECHNICAL: {
                    "market_thresholds": copy.deepcopy(QUALITY_POLICY),
                    "verified_positive_event_required": False,
                    "event_scan_required": False,
                    "maximum_v2_rank_fraction": QUALITY_MAX_V2_RANK_FRACTION,
                    "minimum_data_quality": QUALITY_MIN_DATA_QUALITY,
                    "minimum_risk_reward_ratio": QUALITY_MIN_RISK_REWARD_RATIO,
                    "minimum_qualification_score": QUALITY_MIN_QUALIFICATION_SCORE,
                },
            },
            "ignored_model_availability_blocker_codes": sorted(MODEL_AVAILABILITY_BLOCKERS),
        },
    }


__all__ = [
    "ACTION_BASIS",
    "ACTION_NONE",
    "ACTION_PICK",
    "CONTRACT_VERSION",
    "RULE_INPUTS_CONTRACT_VERSION",
    "SUPPORTED_RULE_INPUTS_CONTRACT_VERSIONS",
    "HORIZON_RANGE_CONTRACT_VERSION",
    "HORIZON_RANGE_METHOD_ID",
    "TEN_DAY_TRADE_PLAN_CONTRACT_VERSION",
    "RULE_MODEL_ID",
    "SCORE_KIND",
    "TRACK_EVENT_CATALYST",
    "TRACK_QUALITY_TECHNICAL",
    "build_production_decision",
    "build_production_rule_inputs",
    "freeze_production_rule_input_row",
    "production_rule_inputs_sha256",
]
