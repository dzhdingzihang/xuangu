#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pathlib


VALID_MODEL_STATUSES = {"available", "unavailable"}
VALID_CANDIDATE_STATUSES = {"ranked", "rejected", "unavailable", "not_applicable"}
VALID_EXECUTABLE_SCORE_KINDS = {"TEN_DAY_EXPECTED_NET_UTILITY"}
STATE_SEVERITY = {"READY": 0, "DEGRADED": 1, "BLOCKED": 2}


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def probability(value) -> bool:
    return finite_number(value) and 0 <= value <= 1


def strict_boolean(value) -> bool:
    return type(value) is bool


def decision_candidates(decision: dict) -> list[dict]:
    rows = [decision.get("primary"), decision.get("blocked_candidate"), *(decision.get("watchlist") or [])]
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or row.get("symbol") or id(row))
        if code in seen:
            continue
        seen.add(code)
        result.append(row)
    return result


def derive_market_coverage_state(section: dict) -> tuple[str, list[str]]:
    """Recompute the minimum safe market state from published source fields."""

    section = section or {}
    decision = section.get("decision") or {}
    stats = section.get("stats") or {}
    pool = section.get("pool_health") or {}
    quote_health = section.get("quote_health") or {}
    pool_state = str(pool.get("state") or pool.get("status") or pool.get("data_state") or "").upper()
    pool_codes = list(pool.get("reason_codes") or [])
    decision_codes = list(decision.get("blocker_codes") or [])
    pool_degraded = pool_state == "DEGRADED" or bool(pool_codes) or any(
        any(token in str(code) for token in ("POOL_COVERAGE", "BROAD_POOL", "QUOTE_COVERAGE"))
        for code in decision_codes
    )
    origin = str(stats.get("universe_origin") or section.get("universe_origin") or "")
    regime_payload = section.get("market_regime") or {}
    regime = regime_payload if isinstance(regime_payload, str) else regime_payload.get("state")
    quote_coverage = quote_health.get("quote_coverage")
    quote_ready = (
        str(quote_health.get("status") or "").lower() == "available"
        and finite_number(quote_coverage)
        and quote_coverage >= 0.98
        and isinstance(quote_health.get("requested_count"), int)
        and quote_health.get("requested_count") > 0
    )
    reasons: list[str] = []
    if pool_degraded:
        reasons.append("POOL_COVERAGE_INCOMPLETE")
    if origin == "curated_static":
        reasons.append("CURATED_STATIC_UNIVERSE")
    if not regime or regime == "unknown":
        reasons.append("MARKET_CONTEXT_MISSING")
    if not quote_ready:
        reasons.append("QUOTE_HEALTH_INCOMPLETE")
    return ("BLOCKED" if pool_degraded else "DEGRADED" if reasons else "READY"), reasons


def validate_snapshot(snapshot: dict) -> list[str]:
    errors: list[str] = []
    if snapshot.get("schema_version") != "selector-snapshot-v2":
        errors.append("schema_version must be selector-snapshot-v2")
    if snapshot.get("selector_mode") != "legacy_active_v2_dual_low_shadow":
        errors.append("selector_mode must expose the dual-low shadow")
    dual_model = ((snapshot.get("analysis_models") or {}).get("dual_low") or {})
    if dual_model.get("model_id") != "dsa-screening-score-v1":
        errors.append("analysis_models.dual_low.model_id is missing")
    if dual_model.get("status") not in VALID_MODEL_STATUSES:
        errors.append("analysis_models.dual_low.status is invalid")
    if dual_model.get("participates_in_decision") is not False:
        errors.append("dual-low model must not participate in the decision")
    if dual_model.get("status") == "available":
        counts = [dual_model.get(key) for key in ("input_count", "eligible_count", "rejected_count")]
        if not all(isinstance(value, int) and value >= 0 for value in counts):
            errors.append("dual-low available counts must be non-negative integers")
        elif counts[1] + counts[2] != counts[0]:
            errors.append("dual-low available counts do not add up")
        if dual_model.get("rank_universe_size") != dual_model.get("eligible_count"):
            errors.append("dual-low rank denominator must equal eligible_count")
        for item in dual_model.get("top_ranked") or []:
            if not finite_number(item.get("final_score")) or not 0 <= item["final_score"] <= 100:
                errors.append("dual-low top-ranked score is invalid")

    ten_day_model = ((snapshot.get("analysis_models") or {}).get("ten_day_return"))
    if ten_day_model is None:
        errors.append("analysis_models.ten_day_return is required")
    else:
        if not isinstance(ten_day_model, dict):
            errors.append("analysis_models.ten_day_return must be an object")
            ten_day_model = None
        else:
            for field in ("calibrated", "costs_ready", "tail_risk_ready", "participates_in_decision"):
                if field in ten_day_model and not strict_boolean(ten_day_model.get(field)):
                    errors.append(f"analysis_models.ten_day_return.{field} must be a boolean")
            ten_day_status = str(ten_day_model.get("status") or "").upper()
            if ten_day_status in {"READY", "CALIBRATED"} and ten_day_model.get("calibrated") is not True:
                errors.append("ten-day READY status requires calibrated=true")
            ten_day_probability = ten_day_model.get("probability")
            if ten_day_model.get("calibrated") is not True and ten_day_probability is not None:
                errors.append("uncalibrated ten-day model probability must be null")
            if ten_day_probability is not None and not probability(ten_day_probability):
                errors.append("analysis_models.ten_day_return.probability must be between 0 and 1")

    markets = snapshot.get("markets") or {}
    derived_market_states: dict[str, tuple[str, list[str]]] = {}
    for market_key in ("a_share", "hk", "us"):
        if market_key not in markets:
            errors.append(f"markets.{market_key} is missing")
            continue
        derived_market_states[market_key] = derive_market_coverage_state(markets[market_key] or {})
        for candidate in decision_candidates((markets[market_key] or {}).get("decision") or {}):
            analysis = ((candidate.get("analysis_projects") or {}).get("dual_low") or {})
            status = analysis.get("status")
            if status not in VALID_CANDIDATE_STATUSES:
                errors.append(f"{market_key}:{candidate.get('code')} dual-low status is invalid")
                continue
            if analysis.get("participates_in_decision") is not False:
                errors.append(f"{market_key}:{candidate.get('code')} dual-low decision flag is invalid")
            if market_key in {"hk", "us"} and status != "not_applicable":
                errors.append(f"{market_key}:{candidate.get('code')} must be not_applicable")
            if market_key == "a_share" and status == "not_applicable":
                errors.append(f"a_share:{candidate.get('code')} cannot be not_applicable")
            if status == "ranked":
                for field in ("base_score", "final_score"):
                    value = analysis.get(field)
                    if not finite_number(value) or not 0 <= value <= 100:
                        errors.append(f"a_share:{candidate.get('code')} {field} is invalid")
                rank = analysis.get("rank")
                denominator = analysis.get("rank_universe_size")
                if not isinstance(rank, int) or not isinstance(denominator, int) or not 1 <= rank <= denominator:
                    errors.append(f"a_share:{candidate.get('code')} rank is invalid")
            elif analysis.get("final_score") is not None or analysis.get("rank") is not None:
                errors.append(f"{market_key}:{candidate.get('code')} unscored values must be null")

    global_decision = snapshot.get("global_decision")
    if global_decision is None:
        errors.append("global_decision is required")
    else:
        if not isinstance(global_decision, dict):
            errors.append("global_decision must be an object")
        else:
            if global_decision.get("contract_version") != "global-10d-v1":
                errors.append("global_decision.contract_version is invalid")
            if global_decision.get("decision_scope") != "global_10d":
                errors.append("global_decision.decision_scope is invalid")
            action = global_decision.get("action")
            if action not in {"NO_VALID_PICK", "REVIEW_EXECUTABLE_PICK"}:
                errors.append("global_decision.action is invalid")
            if global_decision.get("action_basis") != "strict_cross_market_gate_v1":
                errors.append("global_decision.action_basis is invalid")
            if "calibrated" not in global_decision or not strict_boolean(global_decision.get("calibrated")):
                errors.append("global_decision.calibrated must be a boolean")
            calibrated = global_decision.get("calibrated") is True
            if not calibrated and global_decision.get("probability") is not None:
                errors.append("uncalibrated global decision probability must be null")
            if not calibrated and global_decision.get("probability_status") != "UNAVAILABLE":
                errors.append("uncalibrated global decision must be UNAVAILABLE")
            blocker_codes = global_decision.get("blocker_codes")
            if not isinstance(blocker_codes, list):
                errors.append("global_decision.blocker_codes must be a list")
                blocker_codes = []
            primary = global_decision.get("primary")
            if action == "NO_VALID_PICK":
                if primary is not None:
                    errors.append("NO_VALID_PICK must not expose a primary candidate")
                if not blocker_codes:
                    errors.append("NO_VALID_PICK must expose at least one blocker code")
            elif action == "REVIEW_EXECUTABLE_PICK":
                if not calibrated:
                    errors.append("REVIEW_EXECUTABLE_PICK requires calibrated=true")
                if global_decision.get("probability_status") != "CALIBRATED":
                    errors.append("REVIEW_EXECUTABLE_PICK probability_status must be CALIBRATED")
                if not probability(global_decision.get("probability")):
                    errors.append("REVIEW_EXECUTABLE_PICK probability must be between 0 and 1")
                if blocker_codes:
                    errors.append("REVIEW_EXECUTABLE_PICK must not expose blocker codes")
                if not isinstance(ten_day_model, dict):
                    errors.append("REVIEW_EXECUTABLE_PICK requires a ten-day model")
                else:
                    for field in ("calibrated", "costs_ready", "tail_risk_ready", "participates_in_decision"):
                        if ten_day_model.get(field) is not True:
                            errors.append(f"REVIEW_EXECUTABLE_PICK requires ten_day_return.{field}=true")
                if not isinstance(primary, dict):
                    errors.append("REVIEW_EXECUTABLE_PICK must expose a primary candidate")
                else:
                    if primary.get("status") != "EXECUTABLE":
                        errors.append("executable primary status must be EXECUTABLE")
                    if not isinstance(primary.get("prediction_id"), str) or not primary.get("prediction_id"):
                        errors.append("executable primary prediction_id is required")
                    if primary.get("score_kind") not in VALID_EXECUTABLE_SCORE_KINDS:
                        errors.append("executable primary score_kind must be a calibrated model output")
                    if not isinstance(primary.get("model_id"), str) or not primary.get("model_id"):
                        errors.append("executable primary model_id is required")
                    elif isinstance(ten_day_model, dict) and primary.get("model_id") != ten_day_model.get("model_id"):
                        errors.append("executable primary model_id must match ten_day_return.model_id")
                    if not isinstance(primary.get("label_version"), str) or not primary.get("label_version"):
                        errors.append("executable primary label_version is required")
                    elif isinstance(ten_day_model, dict) and primary.get("label_version") != ten_day_model.get("label_version"):
                        errors.append("executable primary label_version must match ten_day_return.label_version")
                    if primary.get("calibrated") is not True:
                        errors.append("executable primary must be calibrated")
                    if not probability(primary.get("probability")):
                        errors.append("executable primary probability must be between 0 and 1")
                    elif primary.get("probability") != global_decision.get("probability"):
                        errors.append("executable primary probability must match global_decision.probability")
                    if not finite_number(primary.get("expected_net_utility")):
                        errors.append("executable primary expected_net_utility must be finite")
                    if not finite_number(primary.get("transaction_cost")) or primary.get("transaction_cost", -1) < 0:
                        errors.append("executable primary transaction_cost must be a non-negative finite number")
                    if not finite_number(primary.get("tail_risk")) or primary.get("tail_risk", -1) < 0:
                        errors.append("executable primary tail_risk must be a non-negative finite number")
            research = global_decision.get("research_priority")
            if research is not None:
                if not isinstance(research, dict):
                    errors.append("research_priority must be an object")
                elif research.get("status") != "RESEARCH_ONLY":
                    errors.append("research_priority must be RESEARCH_ONLY")
                elif research.get("probability") is not None:
                    errors.append("research_priority probability must be null until calibrated")
            market_states = global_decision.get("market_states") or {}
            if not isinstance(market_states, dict) or set(market_states) != {"a_share", "hk", "us"}:
                errors.append("global_decision.market_states must cover three markets")
            for market_key, state in (market_states.items() if isinstance(market_states, dict) else []):
                if not isinstance(state, dict) or state.get("state") not in {"READY", "DEGRADED", "BLOCKED"}:
                    errors.append(f"global_decision.market_states.{market_key} is invalid")
                    continue
                published_state = state.get("state")
                derived_state, derived_reasons = derived_market_states.get(market_key, ("BLOCKED", []))
                if STATE_SEVERITY[published_state] < STATE_SEVERITY[derived_state]:
                    errors.append(
                        f"global_decision.market_states.{market_key} understates derived {derived_state} coverage"
                    )
                reason_codes = state.get("reason_codes") or []
                if not isinstance(reason_codes, list) or not set(derived_reasons).issubset(reason_codes):
                    errors.append(f"global_decision.market_states.{market_key}.reason_codes are incomplete")
                if action == "REVIEW_EXECUTABLE_PICK" and published_state != "READY":
                    errors.append(f"REVIEW_EXECUTABLE_PICK requires market_states.{market_key}=READY")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/picks/latest.json")
    args = parser.parse_args()
    path = pathlib.Path(args.path)
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_snapshot(snapshot)
    if errors:
        raise SystemExit("Snapshot validation failed:\n- " + "\n- ".join(errors))
    model = snapshot["analysis_models"]["dual_low"]
    print(
        f"Snapshot valid: {path} | dual_low={model.get('status')} "
        f"input={model.get('input_count')} eligible={model.get('eligible_count')}"
    )


if __name__ == "__main__":
    main()
