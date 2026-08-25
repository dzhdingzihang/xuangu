"""Auditable ten-session production qualification rules.

The calibrated ``global_decision`` remains the only probability-bearing
contract. This module consumes its evaluated candidate ledger, removes only
the two blockers meaning that the probability model is unavailable, and then
applies a separate deterministic qualification policy. A qualification score
is a rule match score, never a probability or expected return.
"""

from __future__ import annotations

import copy
import hashlib
import math
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "production-rule-10d-v1"
DECISION_SCOPE = "global_10d_bounded_recall"
ACTION_BASIS = "candidate_level_rule_qualification_v2"
RULE_MODEL_ID = "ten-day-audited-rule-ensemble-v2"
SCORE_KIND = "RULE_QUALIFICATION_SCORE"
HORIZON_TRADE_DAYS = 10
ACTION_PICK = "QUALIFIED_PICK"
ACTION_NONE = "NO_QUALIFIED_PICK"

MARKET_POLICY = {
    "a_share": {"minimum_legacy": 64.0, "maximum_downside": 8.0, "minimum_upside": 5.0},
    "hk": {"minimum_legacy": 63.0, "maximum_downside": 8.0, "minimum_upside": 5.0},
    "us": {"minimum_legacy": 64.0, "maximum_downside": 10.0, "minimum_upside": 6.0},
}
MAX_V2_RANK_FRACTION = 0.20
MIN_RISK_REWARD_RATIO = 1.20

# A real non-positive utility, unknown future blocker, or data/event/risk
# blocker remains blocking. Only model unavailability is irrelevant here.
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


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


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


def _evaluate_candidate(snapshot: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    source_blockers = row.get("blocker_codes")
    blockers = (
        _dedupe([str(code) for code in source_blockers if str(code) not in MODEL_AVAILABILITY_BLOCKERS])
        if isinstance(source_blockers, list)
        else ["SOURCE_BLOCKER_CODES_INVALID"]
    )
    market = _text(row.get("market"))
    code = _text(row.get("code") or row.get("symbol"))
    name = _text(row.get("name"))
    policy = MARKET_POLICY.get(market or "")
    if not market or not code:
        blockers.append("CANDIDATE_IDENTITY_INVALID")
    if policy is None:
        blockers.append("MARKET_POLICY_MISSING")
        policy = {"minimum_legacy": 100.0, "maximum_downside": 0.0, "minimum_upside": 100.0}

    source_candidate = _source_candidate(snapshot, market, code)
    if source_candidate is None:
        blockers.append("CANDIDATE_SNAPSHOT_MISSING")

    # ``legacy_signal`` is a market-level decision: one failed Legacy primary
    # can set it to NO_TRADE for every candidate in that market. Requiring it
    # here made the independent production track reject otherwise valid
    # candidate-level evidence. Keep it for provenance; the per-stock Legacy
    # recommendation threshold below remains a hard gate.
    legacy_signal = _text(row.get("legacy_signal"))
    recommendation = row.get("legacy_recommendation_degree")
    if not _finite_number(recommendation):
        recommendation_value = 0.0
        blockers.append("LEGACY_RECOMMENDATION_INVALID")
    else:
        recommendation_value = _clamp(float(recommendation))
        if recommendation_value < float(policy["minimum_legacy"]):
            blockers.append("LEGACY_RECOMMENDATION_BELOW_THRESHOLD")

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
        blockers.append("V2_RANK_INVALID")
    else:
        rank_value = float(rank)
        universe_value = float(universe_size)
        rank_fraction = rank_value / universe_value
        v2_strength = _clamp((universe_value - rank_value + 1.0) / universe_value * 100.0)
        if rank_fraction > MAX_V2_RANK_FRACTION:
            blockers.append("V2_TOP_PERCENTILE_REQUIRED")

    quality_score = _raw_data_quality(row, source_candidate)
    if quality_score is None:
        quality_score = 0.0
        blockers.append("DATA_QUALITY_SCORE_INVALID")

    event_scanned = row.get("event_candidate_scanned") is True
    event_ids_raw = row.get("verified_positive_event_ids")
    event_ids = _dedupe([str(value) for value in event_ids_raw if _text(value)]) if isinstance(event_ids_raw, list) else []
    if not event_scanned:
        blockers.append("EVENT_CANDIDATE_NOT_SCANNED")
    if not event_ids:
        blockers.append("VERIFIED_POSITIVE_EVENT_MISSING")
    event_strength = min(100.0, 80.0 + 5.0 * len(event_ids)) if event_scanned and event_ids else 0.0

    estimated_range = row.get("estimated_10d_range")
    low_pct = estimated_range.get("low_pct") if isinstance(estimated_range, Mapping) else None
    high_pct = estimated_range.get("high_pct") if isinstance(estimated_range, Mapping) else None
    range_valid = _finite_number(low_pct) and _finite_number(high_pct) and float(low_pct) < 0 < float(high_pct)
    if not range_valid:
        low_value = high_value = downside = ratio = None
        risk_reward_strength = 0.0
        blockers.append("TEN_DAY_RANGE_INVALID")
    else:
        low_value = float(low_pct)
        high_value = float(high_pct)
        downside = abs(low_value)
        ratio = high_value / downside
        if high_value < float(policy["minimum_upside"]):
            blockers.append("TEN_DAY_UPSIDE_BELOW_THRESHOLD")
        if downside > float(policy["maximum_downside"]):
            blockers.append("TEN_DAY_DOWNSIDE_ABOVE_LIMIT")
        if ratio < MIN_RISK_REWARD_RATIO:
            blockers.append("RISK_REWARD_BELOW_THRESHOLD")
        risk_reward_strength = _clamp(ratio / 2.0 * 100.0)

    components = {
        "legacy_recommendation": round(recommendation_value * 0.30, 2),
        "v2_rank_strength": round(v2_strength * 0.30, 2),
        "data_quality": round(quality_score * 0.15, 2),
        "verified_event_evidence": round(event_strength * 0.15, 2),
        "risk_reward_scenario": round(risk_reward_strength * 0.10, 2),
    }
    qualification_score = round(_clamp(sum(components.values())), 2)
    blockers = _dedupe(blockers)
    qualified = not blockers
    result = {
        "market": market,
        "code": code,
        "name": name,
        "status": "QUALIFIED" if qualified else "REJECTED",
        "rule_model_id": RULE_MODEL_ID,
        "score_kind": SCORE_KIND,
        "qualification_score": qualification_score,
        "score_components": components,
        "probability": None,
        "probability_status": "NOT_APPLICABLE",
        "calibrated": False,
        "expected_net_utility": None,
        "legacy_signal": legacy_signal,
        "legacy_recommendation_degree": round(recommendation_value, 2) if _finite_number(recommendation) else None,
        "v2_rank": int(rank_value) if rank_valid else None,
        "v2_rank_universe_size": int(universe_value) if rank_valid else None,
        "v2_rank_fraction": round(rank_fraction, 4) if rank_fraction is not None else None,
        "data_quality_score": round(quality_score, 2),
        "event_candidate_scanned": event_scanned,
        "verified_positive_event_ids": event_ids,
        "entry_price": float(row["entry_price"]) if _finite_number(row.get("entry_price")) and float(row["entry_price"]) > 0 else None,
        "calendar_id": _text(row.get("calendar_id")),
        "calendar_version": _text(row.get("calendar_version")),
        "entry_trade_date": _text(row.get("entry_trade_date")),
        "forecast_end_trade_date": _text(row.get("forecast_end_trade_date")),
        "estimated_10d_range": {
            "low_pct": round(low_value, 2) if low_value is not None else None,
            "high_pct": round(high_value, 2) if high_value is not None else None,
            "horizon_trade_days": HORIZON_TRADE_DAYS,
        },
        "risk_reward": {
            "upside_pct": round(high_value, 2) if high_value is not None else None,
            "downside_pct": round(downside, 2) if downside is not None else None,
            "ratio": round(ratio, 2) if ratio is not None else None,
        },
        "blocker_codes": blockers,
    }
    if qualified:
        result["qualification_id"] = _stable_qualification_id(snapshot, market, code)
        result["candidate_snapshot"] = _compact_candidate_snapshot(source_candidate, market)
    return result


def build_production_decision(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return one market-isolated, evidence-backed rule candidate or abstain."""
    global_decision = snapshot.get("global_decision")
    global_decision = global_decision if isinstance(global_decision, Mapping) else {}
    rows = global_decision.get("evaluated_candidates")
    source_rows = rows if isinstance(rows, list) else []
    evaluated = [_evaluate_candidate(snapshot, row) for row in source_rows if isinstance(row, Mapping)]
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
            "verified_positive_event_required": True,
            "minimum_risk_reward_ratio": MIN_RISK_REWARD_RATIO,
            "score_weights": {
                "legacy_recommendation": 0.30,
                "v2_rank_strength": 0.30,
                "data_quality": 0.15,
                "verified_event_evidence": 0.15,
                "risk_reward_scenario": 0.10,
            },
            "ignored_model_availability_blocker_codes": sorted(MODEL_AVAILABILITY_BLOCKERS),
        },
    }


__all__ = ["ACTION_NONE", "ACTION_PICK", "CONTRACT_VERSION", "RULE_MODEL_ID", "SCORE_KIND", "build_production_decision"]
