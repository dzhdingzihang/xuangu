#!/usr/bin/env python3
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import shutil
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import history_evaluation
import model_observation_ledger
import observation_outcome_ledger
import rule_outcome_ledger


PUBLIC = ROOT / "public"
STATIC = ROOT / "static"
PICKS = ROOT / "data" / "picks"
OUTCOMES = ROOT / "data" / "outcomes"
REQUIRED_STATIC_FILES = ("index.html", "styles.css", "app.js")
MANIFEST_VERSION = "selector-manifest-v2"
MAX_PUBLIC_FULL_SNAPSHOT_DAYS = 30
MAX_QUALIFIED_SUMMARY_CANDIDATES = 20
CURRENT_PRODUCTION_MODEL_VERSION = "smart-selector-2026-08-29.1-two-tier-rule"
PRODUCTION_RULE_CONTRACTS = {
    ("strict_rule_qualification_v1", "ten-day-audited-rule-ensemble-v1"),
    ("candidate_level_rule_qualification_v2", "ten-day-audited-rule-ensemble-v2"),
    ("dual_track_candidate_qualification_v3", "ten-day-audited-rule-ensemble-v3"),
    ("dual_track_candidate_qualification_v4", "ten-day-audited-rule-ensemble-v4"),
}
CURRENT_PRODUCTION_RULE_CONTRACT = (
    "dual_track_candidate_qualification_v4",
    "ten-day-audited-rule-ensemble-v4",
)
PRODUCTION_CANDIDATE_SUMMARY_FIELDS = (
    "qualification_id",
    "status",
    "market",
    "code",
    "name",
    "rule_model_id",
    "score_kind",
    "qualification_score",
    "score_components",
    "probability_status",
    "probability",
    "calibrated",
    "expected_net_utility",
    "legacy_signal",
    "legacy_recommendation_degree",
    "v2_rank",
    "v2_rank_universe_size",
    "data_quality_score",
    "event_candidate_scanned",
    "verified_positive_event_ids",
    "qualification_track",
    "track_evaluations",
    "entry_price",
    "entry_trade_date",
    "forecast_end_trade_date",
    "calendar_id",
    "calendar_version",
    "estimated_10d_range",
    "risk_reward",
    "ten_day_trade_plan",
    "blocker_codes",
)
DUAL_LOW_SUMMARY_FIELDS = (
    "status",
    "mode",
    "model_id",
    "package_version",
    "strategy_id",
    "strategy_version",
    "pool_scope",
    "participates_in_decision",
    "score_as_of",
    "input_count",
    "eligible_count",
    "rejected_count",
    "rank_universe_size",
)
TEN_DAY_SUMMARY_FIELDS = (
    "model_id",
    "status",
    "label_version",
    "feature_schema_version",
    "training_cutoff",
    "fit_data_cutoff",
    "validation_cutoff",
    "last_training_signal_date",
    "last_calibration_signal_date",
    "training_provenance",
    "quality_gate",
    "calibrated",
    "costs_ready",
    "tail_risk_ready",
    "participates_in_decision",
    "production_eligible",
    "shadow_prediction_count",
    "prediction_count",
    "probability",
    "artifact_sha256",
)
TEN_DAY_VALIDATION_SUMMARY_FIELDS = (
    "status",
    "independent_train_date_count",
    "independent_calibration_date_count",
    "independent_test_date_count",
    "independent_test_dates",
    "test_date_count",
    "held_out_days",
    "validation_weighting",
    "top_decile_policy",
    "train_row_count",
    "calibration_row_count",
    "test_row_count",
    "brier_score",
    "baseline_brier_score",
    "brier_skill",
    "ece_10bin",
    "auc",
    "positive_rate",
    "mean_net_return",
    "top_decile_mean_net_return",
    "top_decile_excess_vs_mean",
    "expected_shortfall_10pct",
)
TEN_DAY_RANK_SUMMARY_FIELDS = (
    "model_id",
    "status",
    "target",
    "label_version",
    "feature_schema_version",
    "training_provenance",
    "benchmark_registry",
    "sampling_policy",
    "validation_method",
    "minimum_train_days",
    "test_block_days",
    "sample_count",
    "signal_date_count",
    "fold_count",
    "first_signal_date",
    "last_signal_date",
    "calibrated",
    "participates_in_decision",
    "production_eligible",
    "artifact_sha256",
    "reason_codes",
)
WORKER_RUNTIME_CONTRACT_VERSION = "worker-runtime-v1"
WORKER_LIVE_INDEX_CONTRACT_VERSION = "worker-live-index-v1"
WORKER_UI_BOOTSTRAP_CONTRACT_VERSION = "ui-bootstrap-v1"
WORKER_UI_CANDIDATES_CONTRACT_VERSION = "ui-candidates-v1"
WORKER_UI_EVENTS_CONTRACT_VERSION = "ui-events-v1"
DATA_MANIFEST_CONTRACT_VERSION = "data-manifest-v1"
CANDIDATE_LIST_CONTRACT_VERSION = "candidate-list-v1"
CANDIDATE_DETAIL_CONTRACT_VERSION = "candidate-detail-v1"
EVENT_LIST_CONTRACT_VERSION = "event-list-v1"
HISTORY_LIST_CONTRACT_VERSION = "history-list-v1"
WORKER_RUNTIME_IDENTITY_FIELDS = (
    "schema_version",
    "selector_mode",
    "model_version",
    "weights_version",
    "universe_version",
    "calendar_version",
)
WORKER_AUTOMATION_FIELDS = (
    "trigger",
    "scheduled_slot",
    "scheduled_invocation_slot",
    "source_invocation_slot",
    "scheduler_delay_seconds",
    "recovery_mode",
    "generation_attempt",
    "run_id",
    "scheduler_health",
)
GLOBAL_RUNTIME_DECISION_FIELDS = (
    "contract_version",
    "decision_scope",
    "horizon_trade_days",
    "action",
    "action_basis",
    "probability_status",
    "probability",
    "calibrated",
    "blocker_codes",
    "market_states",
    "automatic_external_evidence_count",
    "event_coverage",
)
GLOBAL_RUNTIME_PREDICTION_FIELDS = (
    "prediction_id",
    "status",
    "market",
    "code",
    "name",
    "score_kind",
    "probability",
    "expected_net_utility",
    "transaction_cost",
    "tail_risk",
    "model_id",
    "label_version",
    "calibrated",
    "calendar_id",
    "calendar_version",
    "entry_trade_date",
    "forecast_end_trade_date",
    "verified_positive_event_ids",
)
LIVE_CANDIDATE_FIELDS = ("code", "symbol", "name", "currency", "realtime", "kline")
LIVE_MARKETS = ("a_share", "hk", "us")
LIVE_MARKET_CURRENCIES = {"a_share": "CNY", "hk": "HKD", "us": "USD"}
LIVE_MARKET_VOLUME_UNITS = {
    "a_share": {"lot", "share", "shares"},
    "hk": {"share", "shares"},
    "us": {"share", "shares"},
}
MAX_WORKER_LIVE_CANDIDATES = 90
MAX_WORKER_LIVE_INDEX_BYTES = 512 * 1024
MAX_WORKER_UI_BOOTSTRAP_BYTES = 192 * 1024
MAX_WORKER_UI_CANDIDATES_BYTES = 768 * 1024
MAX_WORKER_UI_EVENTS_BYTES = 512 * 1024
MAX_DATA_SUMMARY_BYTES = 100 * 1024
MAX_DATA_CANDIDATE_LIST_BYTES = 100 * 1024
MAX_DATA_CANDIDATE_DETAIL_BYTES = 100 * 1024
MAX_DATA_EVENT_ROW_BYTES = 2 * 1024
MAX_DATA_HISTORY_ROW_BYTES = 20 * 1024
WORKER_LIVE_CODE_NORMALIZATION = "worker-facing-live-code-v1"
RUNTIME_FORBIDDEN_KEYS = {
    "candidate_snapshot",
    "evaluated_candidates",
    "production_rule_inputs",
    "events",
}

UI_MARKET_STAT_FIELDS = (
    "universe_origin",
    "eligible_discovery_size",
    "broad_pool_size",
    "raw_pool_size",
    "universe_size",
    "recall_target",
    "recall_selected_size",
    "valid_quote_size",
    "base_scored_size",
    "technical_attempted_size",
    "technical_scored_size",
    "technical_kline_complete_size",
    "technical_kline_coverage",
    "deep_eligible_size",
    "deep_attempted_size",
    "deep_scored_size",
    "scored_size",
)
UI_MARKET_SECTION_FIELDS = (
    "key",
    "label",
    "description",
    "trade_window",
    "market_regime",
    "market_context",
)


def validate_required_assets() -> None:
    missing = [name for name in REQUIRED_STATIC_FILES if not (STATIC / name).is_file()]
    empty = [name for name in REQUIRED_STATIC_FILES if (STATIC / name).is_file() and (STATIC / name).stat().st_size == 0]
    problems = [*(f"missing:{name}" for name in missing), *(f"empty:{name}" for name in empty)]
    if problems:
        raise FileNotFoundError(f"Required Worker static assets are invalid: {', '.join(problems)}")


def copy_tree(source: pathlib.Path, target: pathlib.Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def read_outcome_map(outcomes_dir: pathlib.Path = OUTCOMES) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for path in outcomes_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        prediction_id = payload.get("prediction_id") if isinstance(payload, dict) else None
        if prediction_id and path.stem == prediction_id:
            results[str(prediction_id)] = payload
    return results


def public_outcome(outcome: dict | None) -> dict | None:
    if not isinstance(outcome, dict):
        return None
    keys = (
        "schema_version",
        "track",
        "status",
        "prediction_id",
        "model_id",
        "label_version",
        "artifact_sha256",
        "training_cutoff",
        "sampling_policy",
        "scheduled_slot",
        "source_snapshot",
        "market",
        "code",
        "probability",
        "expected_net_utility",
        "tail_risk",
        "entry_trade_date",
        "forecast_end_trade_date",
        "horizon_trade_sessions",
        "entry_policy",
        "exit_policy",
        "calendar_id",
        "calendar_version",
        "currency",
        "fx_rate_source",
        "entry_at",
        "entry_price",
        "entry_source",
        "exit_at",
        "exit_price",
        "exit_source",
        "gross_total_return",
        "net_total_return",
        "transaction_cost",
        "corporate_action_adjusted",
        "positive_label",
        "settled_at",
        "settlement_note",
    )
    return {key: outcome.get(key) for key in keys if key in outcome}


def matching_shadow_outcome(
    pick: dict,
    outcome_map: dict[str, dict],
    source_snapshot: str | None = None,
) -> dict | None:
    outcome = history_evaluation.matching_outcome(
        pick,
        outcome_map,
        history_evaluation.SHADOW_TRACK,
        source_snapshot,
    )
    return public_outcome(outcome)


def matching_executable_outcome(
    pick: dict,
    outcome_map: dict[str, dict],
    source_snapshot: str | None = None,
) -> dict | None:
    outcome = history_evaluation.matching_outcome(
        pick,
        outcome_map,
        history_evaluation.EXECUTABLE_TRACK,
        source_snapshot,
    )
    return public_outcome(outcome)


def write_public_pick(
    source: pathlib.Path,
    target: pathlib.Path,
    shadow_outcome_map: dict[str, dict] | None = None,
    executable_outcome_map: dict[str, dict] | None = None,
) -> None:
    """Publish JSON without leaking machine-specific research metadata."""
    try:
        pick = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        shutil.copy2(source, target)
        return
    source_snapshot = (
        str(pick.get("snapshot_key"))
        if source.name == "latest.json" and pick.get("snapshot_key")
        else source.name
    )
    serenity = ((pick.get("research_runtime") or {}).get("serenity_skill") or {})
    if serenity:
        serenity.pop("path", None)
        serenity["skill_metadata_detected"] = bool(serenity.get("installed"))
        serenity["mode"] = "built-in-lens"
    shadow_outcome = matching_shadow_outcome(
        pick,
        shadow_outcome_map or {},
        source_snapshot,
    )
    pick.pop("shadow_outcome", None)
    if shadow_outcome:
        pick["shadow_outcome"] = shadow_outcome
    # Formal performance is ledger-authoritative.  A snapshot may contain old
    # embedded outcome evidence, but it must never be published as a formal
    # settlement unless the isolated executable ledger joins successfully.
    pick.pop("ten_day_outcome", None)
    pick.pop("outcome", None)
    executable_outcome = matching_executable_outcome(
        pick,
        executable_outcome_map or {},
        source_snapshot,
    )
    if executable_outcome:
        pick["outcome"] = executable_outcome
    evaluation_row = dict(pick)
    evaluation_row["cache_key"] = source_snapshot
    evaluation_row["history_kind"] = (
        "global_10d_v1"
        if history_evaluation.is_global_ten_day_decision(pick.get("global_decision"))
        else "legacy_snapshot"
    )
    evaluation = history_evaluation.formal_sample_evaluation(evaluation_row)
    if evaluation is not None:
        pick.update(evaluation)
    target.write_text(json.dumps(pick, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize_decision(decision: dict) -> dict:
    primary = decision.get("primary") or decision.get("blocked_candidate")
    summary = {
        "action": decision.get("action"),
        "title": decision.get("title"),
        "message": decision.get("message"),
        "has_primary": bool(decision.get("primary")),
    }
    if primary:
        two_week_range = primary.get("estimated_2w_range") or {}
        two_day_range = primary.get("estimated_2d_range") or {}
        summary.update(
            {
                "code": primary.get("code"),
                "name": primary.get("name"),
                "confidence": primary.get("recommendation_degree") or primary.get("confidence"),
                "recommendation_degree": primary.get("recommendation_degree") or primary.get("confidence"),
                "estimated_2w_range": two_week_range.get("text") if isinstance(two_week_range, dict) else None,
                "estimated_2d_range": two_day_range.get("text") if isinstance(two_day_range, dict) else None,
                "entry_price": primary.get("entry_price") or primary.get("price"),
                "current_change_pct": primary.get("current_change_pct") or primary.get("change_pct"),
                "score": primary.get("score"),
                "reason_tags": primary.get("reason_tags"),
            }
        )
    return summary


def summarize_market_regime(section: dict) -> dict | None:
    regime = section.get("market_regime") or section.get("regime")
    if regime is None:
        decision = section.get("decision") or {}
        candidate = decision.get("primary") or decision.get("blocked_candidate")
        if candidate is None:
            watchlist = decision.get("watchlist") or []
            candidate = watchlist[0] if watchlist else {}
        v2 = (candidate or {}).get("v2") or {}
        regime = v2.get("market_regime")
    if isinstance(regime, str):
        return {"state": regime}
    if not isinstance(regime, dict):
        return None
    keys = ("state", "label", "confidence", "warnings", "effective_weights")
    summary = {key: regime.get(key) for key in keys if regime.get(key) is not None}
    return summary or None


def summarize_analysis_models(pick: dict) -> dict:
    """Keep model identity and batch health without copying pool-sized results."""
    dual_low = ((pick.get("analysis_models") or {}).get("dual_low") or {})
    if not isinstance(dual_low, dict):
        dual_low = {}

    summary = {
        key: dual_low.get(key)
        for key in DUAL_LOW_SUMMARY_FIELDS
        if dual_low.get(key) is not None
    }
    supported_markets = dual_low.get("supported_markets")
    if isinstance(supported_markets, list):
        summary["supported_markets"] = [
            market for market in supported_markets[:3] if isinstance(market, str)
        ]

    coverage = dual_low.get("required_field_coverage")
    if isinstance(coverage, dict):
        coverage_summary = {
            key: coverage.get(key)
            for key in ("input_count", "complete_count", "ratio")
            if coverage.get(key) is not None
        }
        if coverage_summary:
            summary["required_field_coverage"] = coverage_summary

    result = {"dual_low": summary} if summary else {}
    ten_day = ((pick.get("analysis_models") or {}).get("ten_day_return") or {})
    if isinstance(ten_day, dict):
        ten_day_summary = {
            key: ten_day.get(key)
            for key in TEN_DAY_SUMMARY_FIELDS
            if key in ten_day
        }
        validation = ten_day.get("validation")
        if isinstance(validation, dict):
            validation_summary = {
                key: validation.get(key)
                for key in TEN_DAY_VALIDATION_SUMMARY_FIELDS
                if key in validation
            }
            if validation_summary:
                ten_day_summary["validation"] = validation_summary
        market_models = ten_day.get("market_models")
        if isinstance(market_models, dict):
            market_summaries = {}
            for market in ("a_share", "hk", "us"):
                model = market_models.get(market)
                if not isinstance(model, dict):
                    continue
                model_summary = {
                    key: model.get(key)
                    for key in (
                        "status",
                        "model_id",
                        "artifact_sha256",
                        "training_cutoff",
                        "fit_data_cutoff",
                        "validation_cutoff",
                        "last_training_signal_date",
                        "last_calibration_signal_date",
                        "transaction_cost",
                        "quality_gate",
                        "reason_codes",
                    )
                    if key in model
                }
                market_validation = model.get("validation")
                if isinstance(market_validation, dict):
                    compact_validation = {
                        key: market_validation.get(key)
                        for key in TEN_DAY_VALIDATION_SUMMARY_FIELDS
                        if key in market_validation
                    }
                    if compact_validation:
                        model_summary["validation"] = compact_validation
                if model_summary:
                    market_summaries[market] = model_summary
            if market_summaries:
                ten_day_summary["market_models"] = market_summaries
        for list_field in ("reason_codes", "limitations"):
            values = ten_day.get(list_field)
            if isinstance(values, list):
                ten_day_summary[list_field] = [
                    str(value) for value in values[:12] if isinstance(value, str) and value
                ]
        if ten_day_summary:
            result["ten_day_return"] = ten_day_summary
    rank_model = ((pick.get("analysis_models") or {}).get("ten_day_excess_rank") or {})
    if isinstance(rank_model, dict):
        rank_summary = {
            key: rank_model.get(key)
            for key in TEN_DAY_RANK_SUMMARY_FIELDS
            if key in rank_model
        }
        validation = rank_model.get("validation")
        if isinstance(validation, dict):
            rank_summary["validation"] = {
                key: copy.deepcopy(validation.get(key))
                for key in ("combined_shadow", "final_holdout", "coverage", "per_market")
                if key in validation
            }
        if rank_summary:
            result["ten_day_excess_rank"] = rank_summary
    return result


def summarize_global_decision(pick: dict) -> dict | None:
    decision = pick.get("global_decision")
    if not isinstance(decision, dict):
        return None
    summary = {
        key: decision.get(key)
        for key in (
            "horizon_trade_days",
            "contract_version",
            "decision_scope",
            "action",
            "action_basis",
            "probability_status",
            "probability",
            "calibrated",
            "blocker_codes",
            "market_states",
            "automatic_external_evidence_count",
            "event_coverage",
        )
        if key in decision
    }
    primary = decision.get("primary")
    if isinstance(primary, dict):
        summary["primary"] = {
            key: primary.get(key)
            for key in (
                "prediction_id",
                "status",
                "label_version",
                "market",
                "code",
                "name",
                "entry_trade_date",
                "forecast_end_trade_date",
                "calendar_id",
                "calendar_version",
                "score_kind",
                "probability",
                "expected_net_utility",
                "transaction_cost",
                "tail_risk",
                "model_id",
                "calibrated",
            )
            if key in primary
        }
    else:
        summary["primary"] = None
    research_priority = decision.get("research_priority")
    if isinstance(research_priority, dict):
        summary["research_priority"] = {
            key: research_priority.get(key)
            for key in (
                "prediction_id",
                "status",
                "label_version",
                "market",
                "code",
                "name",
                "entry_trade_date",
                "forecast_end_trade_date",
                "calendar_id",
                "calendar_version",
                "score_kind",
                "probability",
                "expected_net_utility",
                "transaction_cost",
                "tail_risk",
                "model_id",
                "calibrated",
            )
            if key in research_priority
        }
    else:
        summary["research_priority"] = None
    return summary


def summarize_production_candidate(candidate: dict | None) -> dict | None:
    if not isinstance(candidate, dict):
        return None
    return {
        key: candidate.get(key)
        for key in PRODUCTION_CANDIDATE_SUMMARY_FIELDS
        if key in candidate
    }


def summarize_qualified_candidates(decision: dict) -> list[dict]:
    if decision.get("action") != "QUALIFIED_PICK":
        return []
    qualified_candidates = decision.get("qualified_candidates")
    raw_rows = [
        decision.get("primary"),
        *(qualified_candidates if isinstance(qualified_candidates, list) else []),
    ]
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in raw_rows:
        summary = summarize_production_candidate(row)
        if not summary or summary.get("status") != "QUALIFIED":
            continue
        identity = (str(summary.get("market") or ""), str(summary.get("code") or "").lower())
        if not all(identity) or identity in seen:
            continue
        seen.add(identity)
        result.append(summary)
        if len(result) >= MAX_QUALIFIED_SUMMARY_CANDIDATES:
            break
    return result


def valid_production_rule_contract(pick: dict, decision: dict) -> bool:
    pair = (decision.get("action_basis"), decision.get("rule_model_id"))
    if pair not in PRODUCTION_RULE_CONTRACTS:
        return False
    # CURRENT model <-> V4 contract is a strict bijection. Historical V1-V3
    # contracts remain readable, while a V4 decision under an older (or
    # missing) model version is excluded from both history and status assets.
    if (
        pick.get("model_version") == CURRENT_PRODUCTION_MODEL_VERSION
    ) != (pair == CURRENT_PRODUCTION_RULE_CONTRACT):
        return False
    return bool(
        decision.get("contract_version") == "production-rule-10d-v1"
        and decision.get("decision_scope") == "global_10d_bounded_recall"
        and decision.get("action") in {"QUALIFIED_PICK", "NO_QUALIFIED_PICK"}
        and decision.get("score_kind") == "RULE_QUALIFICATION_SCORE"
        and decision.get("probability") is None
        and decision.get("calibrated") is False
    )


def summarize_production_decision(pick: dict) -> dict | None:
    decision = pick.get("production_decision")
    if not isinstance(decision, dict) or not valid_production_rule_contract(pick, decision):
        return None
    summary = {
        key: decision.get(key)
        for key in (
            "contract_version",
            "decision_scope",
            "horizon_trade_days",
            "action",
            "action_basis",
            "rule_model_id",
            "score_kind",
            "score_disclaimer",
            "probability_status",
            "probability",
            "calibrated",
            "expected_net_utility",
            "qualified_candidate_count",
            "rejected_candidate_count",
            "evaluated_candidate_count",
            "blocker_codes",
        )
        if key in decision
    }
    primary = summarize_production_candidate(decision.get("primary"))
    summary["primary"] = primary
    qualified = summarize_qualified_candidates(decision)
    summary["qualified_candidates"] = qualified
    summary["qualified_candidates_truncated"] = int(decision.get("qualified_candidate_count") or 0) > len(qualified)
    return summary


def compact_runtime_value(value):
    """Deep-copy a summary while refusing pool-sized or candidate-sized evidence."""

    if isinstance(value, dict):
        return {
            key: compact_runtime_value(item)
            for key, item in value.items()
            if key not in RUNTIME_FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [compact_runtime_value(item) for item in value]
    return copy.deepcopy(value)


def compact_global_prediction(candidate: dict | None) -> dict | None:
    if not isinstance(candidate, dict):
        return None
    result = {
        key: copy.deepcopy(candidate.get(key))
        for key in GLOBAL_RUNTIME_PREDICTION_FIELDS
        if key in candidate
    }
    return result or None


def summarize_runtime_global_decision(snapshot: dict) -> dict | None:
    decision = snapshot.get("global_decision")
    if not isinstance(decision, dict):
        return None
    summary = {
        key: compact_runtime_value(decision.get(key))
        for key in GLOBAL_RUNTIME_DECISION_FIELDS
        if key in decision
    }
    summary["primary"] = compact_global_prediction(decision.get("primary"))
    summary["research_priority"] = compact_global_prediction(decision.get("research_priority"))
    return summary


def _required_snapshot_identity(snapshot: dict) -> tuple[str, str]:
    snapshot_key = snapshot.get("snapshot_key")
    generated_at = snapshot.get("generated_at")
    if not isinstance(snapshot_key, str) or not snapshot_key:
        raise ValueError("worker asset source snapshot_key is required")
    if not isinstance(generated_at, str) or not generated_at:
        raise ValueError("worker asset source generated_at is required")
    return snapshot_key, generated_at


def build_worker_runtime(
    snapshot: dict,
    latest_summary: dict,
    source_snapshot_bytes: bytes,
) -> dict:
    """Build the CPU-bounded status document from an already validated snapshot."""

    snapshot_key, generated_at = _required_snapshot_identity(snapshot)
    if not isinstance(source_snapshot_bytes, bytes) or not source_snapshot_bytes:
        raise ValueError("worker runtime source snapshot bytes are required")
    production_summary = summarize_production_decision(snapshot)
    global_summary = summarize_runtime_global_decision(snapshot)
    bounded_latest_summary = compact_runtime_value(latest_summary or {})
    bounded_latest_summary["global_decision"] = copy.deepcopy(global_summary)
    bounded_latest_summary["production_decision"] = copy.deepcopy(production_summary)
    bounded_latest_summary["snapshot_key"] = snapshot_key
    bounded_latest_summary["generated_at"] = generated_at
    quote_health_by_market = {
        market: copy.deepcopy((((snapshot.get("markets") or {}).get(market) or {}).get("quote_health") or {}))
        for market in LIVE_MARKETS
    }
    runtime = {
        "contract_version": WORKER_RUNTIME_CONTRACT_VERSION,
        "snapshot_key": snapshot_key,
        "generated_at": generated_at,
        "target_date": snapshot.get("target_date"),
        "signal_date": snapshot.get("signal_date"),
        "feature_cutoff_at": snapshot.get("feature_cutoff_at"),
        **{
            key: copy.deepcopy(snapshot.get(key))
            for key in WORKER_RUNTIME_IDENTITY_FIELDS
            if key in snapshot
        },
        "automation": {
            key: copy.deepcopy((snapshot.get("automation") or {}).get(key))
            for key in WORKER_AUTOMATION_FIELDS
            if key in (snapshot.get("automation") or {})
        },
        "quote_health_by_market": quote_health_by_market,
        "global_decision": global_summary,
        "production_decision": production_summary,
        "latest_summary": bounded_latest_summary,
        "source_snapshot": {
            "sha256": hashlib.sha256(source_snapshot_bytes).hexdigest(),
            "byte_size": len(source_snapshot_bytes),
        },
    }
    encoded = json.dumps(runtime, ensure_ascii=False, separators=(",", ":"))
    for forbidden in RUNTIME_FORBIDDEN_KEYS:
        if f'"{forbidden}"' in encoded:
            raise ValueError(f"worker runtime unexpectedly contains {forbidden}")
    return runtime


def normalize_live_code(value, market: str) -> str | None:
    raw = str(value or "").strip().upper()
    if market == "a_share":
        match = re.fullmatch(r"(?:(?:SH|SZ)\.?)?(\d{6})(?:\.(?:SH|SZ))?", raw)
        return match.group(1) if match else None
    if market == "hk":
        match = re.fullmatch(r"0*(\d{1,5})(?:\.HK)?", raw)
        if not match:
            return None
        number = int(match.group(1))
        return f"{number:04d}.HK" if 1 <= number <= 9999 else None
    if market == "us":
        normalized = raw.replace("_", "-").replace(".", "-")
        return normalized if re.fullmatch(r"[A-Z][A-Z0-9-]{0,14}", normalized) else None
    return None


def _candidate_snapshot(candidate: dict | None) -> dict | None:
    if not isinstance(candidate, dict):
        return None
    nested = candidate.get("candidate_snapshot")
    result = copy.deepcopy(nested) if isinstance(nested, dict) else copy.deepcopy(candidate)
    for key in ("code", "symbol", "name", "currency", "realtime", "kline"):
        if result.get(key) in (None, "", [], {}) and candidate.get(key) not in (None, "", [], {}):
            result[key] = copy.deepcopy(candidate.get(key))
    return result


def compact_live_candidate(candidate: dict, market: str) -> dict:
    code = normalize_live_code(candidate.get("code") or candidate.get("symbol"), market)
    if not code:
        raise ValueError(f"invalid live candidate code for {market}")
    return {
        "code": code,
        "symbol": code,
        "name": str(candidate.get("name") or code),
        "currency": LIVE_MARKET_CURRENCIES[market],
        "realtime": copy.deepcopy(candidate.get("realtime") or {}),
        "kline": copy.deepcopy(candidate.get("kline") or []),
    }


def _aware_datetime(value) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _quote_sort_key(realtime: dict) -> tuple[float, str]:
    source = _aware_datetime(realtime.get("source_as_of")) if isinstance(realtime, dict) else None
    return (
        source.timestamp() if source is not None else float("-inf"),
        json.dumps(realtime, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def merge_live_candidate(existing: dict, candidate: dict) -> dict:
    merged = copy.deepcopy(existing)
    if _quote_sort_key(candidate.get("realtime") or {}) > _quote_sort_key(existing.get("realtime") or {}):
        merged["realtime"] = copy.deepcopy(candidate.get("realtime") or {})
    if len(candidate.get("kline") or []) > len(existing.get("kline") or []):
        merged["kline"] = copy.deepcopy(candidate.get("kline") or [])
    if not merged.get("name") and candidate.get("name"):
        merged["name"] = candidate["name"]
    return merged


def iter_live_candidates(snapshot: dict):
    markets = snapshot.get("markets") or {}
    for market in LIVE_MARKETS:
        decision = ((markets.get(market) or {}).get("decision") or {})
        for role in ("primary", "blocked_candidate"):
            candidate = _candidate_snapshot(decision.get(role))
            if candidate is not None:
                yield market, candidate
        for row in decision.get("watchlist") or []:
            candidate = _candidate_snapshot(row)
            if candidate is not None:
                yield market, candidate
    global_decision = snapshot.get("global_decision") or {}
    for role in ("primary", "research_priority"):
        row = global_decision.get(role)
        if not isinstance(row, dict) or row.get("market") not in LIVE_MARKETS:
            continue
        candidate = _candidate_snapshot(row)
        if candidate is not None:
            yield str(row["market"]), candidate
    production_decision = snapshot.get("production_decision") or {}
    rows = [production_decision.get("primary"), *(production_decision.get("qualified_candidates") or [])]
    for row in rows:
        if not isinstance(row, dict) or row.get("market") not in LIVE_MARKETS:
            continue
        candidate = _candidate_snapshot(row)
        if candidate is not None:
            yield str(row["market"]), candidate


def formal_qualified_candidate_identities(snapshot: dict) -> set[tuple[str, str]]:
    decision = snapshot.get("production_decision")
    if not isinstance(decision, dict) or decision.get("action") != "QUALIFIED_PICK":
        return set()
    raw_rows = [
        decision.get("primary"),
        *((decision.get("qualified_candidates") or []) if isinstance(decision.get("qualified_candidates"), list) else []),
    ]
    identities: set[tuple[str, str]] = set()
    for row in raw_rows:
        if not isinstance(row, dict) or row.get("status") != "QUALIFIED":
            continue
        market = row.get("market")
        if market not in LIVE_MARKETS:
            raise ValueError("formal qualified candidate has invalid market")
        code = normalize_live_code(row.get("code") or row.get("symbol"), market)
        if not code:
            raise ValueError(f"formal qualified candidate has invalid code for {market}")
        candidate = _candidate_snapshot(row)
        if candidate is None:
            raise ValueError(f"formal qualified candidate {market}:{code} has no candidate snapshot")
        candidate_code = normalize_live_code(
            candidate.get("code") or candidate.get("symbol"),
            market,
        )
        if candidate_code != code:
            raise ValueError(
                f"formal qualified candidate {market}:{code} snapshot identity does not match"
            )
        identities.add((market, code))
    published_count = decision.get("qualified_candidate_count")
    if (
        not isinstance(published_count, int)
        or isinstance(published_count, bool)
        or published_count != len(identities)
    ):
        raise ValueError(
            "formal qualified candidate count does not match published decision: "
            f"{len(identities)} != {published_count!r}"
        )
    return identities


def validate_live_candidate(candidate: dict, market: str) -> None:
    identity = f"{market}:{candidate.get('code') or '?'}"
    realtime = candidate.get("realtime")
    if not isinstance(realtime, dict):
        raise ValueError(f"{identity} realtime quote is required")
    try:
        price = float(realtime.get("price"))
    except (TypeError, ValueError):
        price = 0.0
    if not math.isfinite(price) or price <= 0:
        raise ValueError(f"{identity} positive realtime price is required")
    for field in ("source_as_of", "fetched_at"):
        if _aware_datetime(realtime.get(field)) is None:
            raise ValueError(f"{identity} timezone-aware realtime {field} is required")
    expected_units = LIVE_MARKET_VOLUME_UNITS[market]
    if realtime.get("volume_unit") not in expected_units:
        raise ValueError(
            f"{identity} realtime volume_unit must be one of {sorted(expected_units)!r}"
        )
    if not isinstance(candidate.get("kline"), list):
        raise ValueError(f"{identity} kline must be a list")


def build_worker_live_index(snapshot: dict, source_snapshot_bytes: bytes) -> dict:
    snapshot_key, generated_at = _required_snapshot_identity(snapshot)
    if not isinstance(source_snapshot_bytes, bytes) or not source_snapshot_bytes:
        raise ValueError("worker live index source snapshot bytes are required")
    formal_identities = formal_qualified_candidate_identities(snapshot)
    candidate_maps: dict[str, dict[str, dict]] = {market: {} for market in LIVE_MARKETS}
    for market, raw_candidate in iter_live_candidates(snapshot):
        compact = compact_live_candidate(raw_candidate, market)
        code = compact["code"]
        existing = candidate_maps[market].get(code)
        candidate_maps[market][code] = (
            merge_live_candidate(existing, compact) if existing is not None else compact
        )
    excluded_candidates: list[dict] = []
    for market in LIVE_MARKETS:
        validated: dict[str, dict] = {}
        for code in sorted(candidate_maps[market]):
            candidate = candidate_maps[market][code]
            try:
                validate_live_candidate(candidate, market)
            except ValueError as exc:
                if (market, code) in formal_identities:
                    raise ValueError(
                        f"formal qualified candidate {market}:{code} failed live contract: {exc}"
                    ) from exc
                excluded_candidates.append(
                    {"identity": f"{market}:{code}", "reason": str(exc)}
                )
                continue
            validated[code] = candidate
        candidate_maps[market] = validated
    counts = {market: len(candidate_maps[market]) for market in LIVE_MARKETS}
    candidate_count = sum(counts.values())
    if candidate_count > MAX_WORKER_LIVE_CANDIDATES:
        raise ValueError(
            "worker live index candidate limit exceeded: "
            f"{candidate_count} > {MAX_WORKER_LIVE_CANDIDATES}"
        )
    retained_identities = {
        (market, code)
        for market, candidates in candidate_maps.items()
        for code in candidates
    }
    missing_formal = sorted(formal_identities - retained_identities)
    if missing_formal:
        raise ValueError(
            "worker live index omitted formal qualified candidates: "
            + ", ".join(f"{market}:{code}" for market, code in missing_formal)
        )
    payload = {
        "contract_version": WORKER_LIVE_INDEX_CONTRACT_VERSION,
        "snapshot_key": snapshot_key,
        "generated_at": generated_at,
        "model_version": snapshot.get("model_version"),
        "source_snapshot": {
            "sha256": hashlib.sha256(source_snapshot_bytes).hexdigest(),
            "byte_size": len(source_snapshot_bytes),
        },
        "contract_metadata": {
            "candidate_limit": MAX_WORKER_LIVE_CANDIDATES,
            "byte_size_limit": MAX_WORKER_LIVE_INDEX_BYTES,
            "code_normalization": WORKER_LIVE_CODE_NORMALIZATION,
            "volume_units_by_market": {
                market: sorted(LIVE_MARKET_VOLUME_UNITS[market])
                for market in LIVE_MARKETS
            },
        },
        "candidates": candidate_maps,
        "market_candidate_counts": counts,
        "candidate_count": candidate_count,
        "formal_qualified_candidate_count": len(formal_identities),
        "excluded_candidate_count": len(excluded_candidates),
        "excluded_candidates": excluded_candidates,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_WORKER_LIVE_INDEX_BYTES:
        raise ValueError(
            "worker live index byte-size limit exceeded: "
            f"{len(encoded)} > {MAX_WORKER_LIVE_INDEX_BYTES}"
        )
    return payload


def _ui_identity_envelope(
    snapshot: dict,
    source_snapshot_bytes: bytes,
    contract_version: str,
) -> dict:
    snapshot_key, generated_at = _required_snapshot_identity(snapshot)
    if not isinstance(source_snapshot_bytes, bytes) or not source_snapshot_bytes:
        raise ValueError("worker UI asset source snapshot bytes are required")
    return {
        "contract_version": contract_version,
        "snapshot_key": snapshot_key,
        "generated_at": generated_at,
        "source_snapshot": {
            "sha256": hashlib.sha256(source_snapshot_bytes).hexdigest(),
            "byte_size": len(source_snapshot_bytes),
        },
    }


def _compact_ui_realtime(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    fields = (
        "price",
        "change_pct",
        "previous_close",
        "volume",
        "volume_unit",
        "currency",
        "source",
        "source_as_of",
        "fetched_at",
        "session",
        "session_label",
        "price_kind",
        "stale",
    )
    return {key: copy.deepcopy(value[key]) for key in fields if key in value}


def compact_ui_candidate(candidate: dict | None, market: str, *, detail: bool) -> dict | None:
    candidate = _candidate_snapshot(candidate)
    if not isinstance(candidate, dict):
        return None
    code = normalize_live_code(candidate.get("code") or candidate.get("symbol"), market)
    if not code:
        return None
    if detail:
        result = copy.deepcopy(candidate)
        result["code"] = code
        result["symbol"] = code
        result["market"] = market
        return result
    fields = (
        "name",
        "role",
        "reason_tags",
        "theme_tags",
        "recommendation_degree",
        "confidence",
        "score",
        "entry_price",
        "price",
        "current_change_pct",
        "legacy_rank",
        "legacy_complete",
        "execution_state",
        "risk_flags",
        "risk_items",
        "decision_gates",
        "candidate_lineage",
    )
    result = {key: copy.deepcopy(candidate[key]) for key in fields if key in candidate}
    result.update({
        "market": market,
        "code": code,
        "symbol": code,
        "name": str(candidate.get("name") or code),
        "realtime": _compact_ui_realtime(candidate.get("realtime")),
    })
    v2 = candidate.get("v2")
    if isinstance(v2, dict):
        result["v2"] = {
            key: copy.deepcopy(v2[key])
            for key in ("rank", "rank_universe_size", "rule_score")
            if key in v2
        }
    quality = candidate.get("data_quality")
    if isinstance(quality, dict):
        result["data_quality"] = {
            key: copy.deepcopy(quality[key])
            for key in ("score", "status", "missing_fields")
            if key in quality
        }
    projects = candidate.get("analysis_projects")
    if isinstance(projects, dict) and isinstance(projects.get("dual_low"), dict):
        dual = projects["dual_low"]
        result["analysis_projects"] = {
            "dual_low": {
                key: copy.deepcopy(dual[key])
                for key in (
                    "status", "interpretation", "final_score", "rank",
                    "rank_universe_size", "rank_percentile", "missing_fields",
                )
                if key in dual
            }
        }
    shadow = candidate.get("shadow_model")
    if isinstance(shadow, dict):
        result["shadow_model"] = {
            key: copy.deepcopy(shadow[key])
            for key in (
                "probability", "rank_eligible", "market_validation_status",
                "model_id", "status",
            )
            if key in shadow
        }
    return result


def _production_ui_summary(snapshot: dict) -> dict | None:
    summary = summarize_production_decision(snapshot)
    decision = snapshot.get("production_decision")
    if not summary or not isinstance(decision, dict):
        return None
    source_rows = [
        decision.get("primary"),
        *((decision.get("qualified_candidates") or []) if isinstance(decision.get("qualified_candidates"), list) else []),
    ]
    candidates_by_id: dict[str, dict] = {}
    for row in source_rows:
        if not isinstance(row, dict) or row.get("market") not in LIVE_MARKETS:
            continue
        compact = compact_ui_candidate(row, str(row["market"]), detail=False)
        qualification_id = row.get("qualification_id")
        if compact is not None and isinstance(qualification_id, str):
            candidates_by_id[qualification_id] = compact
    for row in [summary.get("primary"), *(summary.get("qualified_candidates") or [])]:
        if not isinstance(row, dict):
            continue
        compact = candidates_by_id.get(str(row.get("qualification_id") or ""))
        if compact is not None:
            row["candidate_snapshot"] = copy.deepcopy(compact)
    return summary


def _global_ui_summary(snapshot: dict) -> dict | None:
    """Keep the bounded global contract usable without the full candidate pool."""

    summary = summarize_runtime_global_decision(snapshot)
    decision = snapshot.get("global_decision")
    if not summary or not isinstance(decision, dict):
        return summary
    for role in ("primary", "research_priority"):
        row = decision.get(role)
        market = row.get("market") if isinstance(row, dict) else None
        if market not in LIVE_MARKETS or not isinstance(summary.get(role), dict):
            continue
        candidate = compact_ui_candidate(row, str(market), detail=False)
        if candidate is not None:
            summary[role]["candidate_snapshot"] = candidate
    return summary


def _compact_ui_market(snapshot: dict, market: str) -> dict:
    section = ((snapshot.get("markets") or {}).get(market) or {})
    result = {
        key: compact_runtime_value(section[key])
        for key in UI_MARKET_SECTION_FIELDS
        if key in section
    }
    result.setdefault("key", market)
    decision = section.get("decision") or {}
    result["decision"] = {
        key: copy.deepcopy(decision[key])
        for key in ("action", "title", "message", "data_state", "blocker_codes")
        if key in decision
    }
    for role in ("primary", "blocked_candidate"):
        compact = compact_ui_candidate(decision.get(role), market, detail=False)
        if compact is not None:
            result["decision"][role] = compact
    result["pool_health"] = compact_runtime_value(section.get("pool_health") or {})
    result["quote_health"] = compact_runtime_value(section.get("quote_health") or {})
    stats = section.get("stats") or {}
    result["stats"] = {
        key: copy.deepcopy(stats[key])
        for key in UI_MARKET_STAT_FIELDS
        if key in stats
    }
    return result


def _snapshot_event_items(snapshot: dict) -> list[dict]:
    raw_events = snapshot.get("events")
    items = raw_events.get("items") if isinstance(raw_events, dict) else raw_events
    return [item for item in (items or []) if isinstance(item, dict)]


def _decision_bound_event_ids(snapshot: dict) -> tuple[str, ...]:
    """Return every event id explicitly bound by either published decision track."""

    production = snapshot.get("production_decision") or {}
    global_decision = snapshot.get("global_decision") or {}
    rows = [
        production.get("primary"),
        *((production.get("qualified_candidates") or [])
          if isinstance(production.get("qualified_candidates"), list) else []),
        global_decision.get("primary"),
        global_decision.get("research_priority"),
    ]
    return tuple(sorted({
        str(event_id)
        for row in rows
        if isinstance(row, dict)
        for event_id in (row.get("verified_positive_event_ids") or [])
        if event_id
    }))


def _event_sort_key(item: dict) -> tuple:
    """Newest published/effective evidence first with a canonical tie-breaker."""

    def timestamp(*keys: str) -> float:
        for key in keys:
            parsed = _aware_datetime(item.get(key))
            if parsed is not None:
                return parsed.timestamp()
        return float("-inf")

    return (
        -timestamp("published_at", "released_at"),
        -timestamp("effective_at"),
        -timestamp("ingested_at"),
        str(item.get("event_id") or ""),
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _event_stats(snapshot: dict) -> dict:
    """Publish tab-independent event counts in the bootstrap asset."""

    raw_events = snapshot.get("events")
    source_stats = raw_events.get("stats") if isinstance(raw_events, dict) else {}
    source_stats = source_stats if isinstance(source_stats, dict) else {}
    items = _snapshot_event_items(snapshot)

    def nonnegative_count(key: str, fallback: int) -> int:
        value = source_stats.get(key)
        return int(value) if isinstance(value, int) and value >= 0 else fallback

    model_signals = sum(item.get("event_type") == "model_signal" for item in items)
    automatic_external = sum(
        item.get("event_type") not in {"model_signal", "manual_external"}
        and str(item.get("ingestion_mode") or "").lower() == "automatic"
        for item in items
    )
    global_decision = snapshot.get("global_decision") or {}
    return {
        "total": len(items),
        "model_signals": nonnegative_count("model_signals", model_signals),
        "automatic_external": nonnegative_count("automatic_external", automatic_external),
        "decision_eligible": sum(item.get("decision_eligible") is True for item in items),
        "decision_bound": len(_decision_bound_event_ids(snapshot)),
        "pipeline_status": global_decision.get("event_pipeline_status"),
        "pipeline_scanned": global_decision.get("event_pipeline_scanned") is True,
    }


def _decision_evidence(snapshot: dict) -> dict:
    wanted_ids = _decision_bound_event_ids(snapshot)
    wanted_set = set(wanted_ids)
    items = _snapshot_event_items(snapshot)
    available_ids = {
        str(item.get("event_id"))
        for item in items
        if item.get("event_id")
    }
    missing_ids = sorted(wanted_set - available_ids)
    if missing_ids:
        raise ValueError(
            "decision-bound event evidence is missing from snapshot: "
            + ", ".join(missing_ids)
        )
    selected = sorted(
        (
            compact_runtime_value(item)
            for item in items
            if str(item.get("event_id") or "") in wanted_set
        ),
        key=_event_sort_key,
    )
    return {
        "automatic_external_evidence_count": int(
            (snapshot.get("global_decision") or {}).get("automatic_external_evidence_count") or 0
        ),
        "bound_event_ids": list(wanted_ids),
        "bound_event_count": len(wanted_ids),
        "items": selected,
    }


def _candidate_role_maps(snapshot: dict) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], int]]:
    roles: dict[tuple[str, str], str] = {}
    ranks: dict[tuple[str, str], int] = {}
    priority = {"qualified": 0, "primary": 1, "research": 2, "watchlist": 3, "blocked": 4}

    def remember(market: str, candidate: dict | None, role: str, rank: int | None = None) -> None:
        compact = compact_ui_candidate(candidate, market, detail=False)
        if compact is None:
            return
        identity = (market, compact["code"])
        if identity not in roles or priority[role] < priority[roles[identity]]:
            roles[identity] = role
        if rank is not None:
            ranks.setdefault(identity, rank)

    for market in LIVE_MARKETS:
        decision = ((((snapshot.get("markets") or {}).get(market) or {}).get("decision") or {}))
        remember(market, decision.get("primary"), "primary", 1)
        remember(market, decision.get("blocked_candidate"), "blocked", 1)
        for index, row in enumerate(decision.get("watchlist") or [], start=1):
            remember(market, row, "watchlist", index)
    global_priority = (snapshot.get("global_decision") or {}).get("research_priority")
    if isinstance(global_priority, dict) and global_priority.get("market") in LIVE_MARKETS:
        remember(str(global_priority["market"]), global_priority, "research")
    production = snapshot.get("production_decision") or {}
    for row in [production.get("primary"), *(production.get("qualified_candidates") or [])]:
        if isinstance(row, dict) and row.get("market") in LIVE_MARKETS:
            remember(str(row["market"]), row, "qualified")
    return roles, ranks


def build_worker_ui_bootstrap(
    snapshot: dict,
    latest_summary: dict,
    source_snapshot_bytes: bytes,
) -> dict:
    payload = {
        **_ui_identity_envelope(snapshot, source_snapshot_bytes, WORKER_UI_BOOTSTRAP_CONTRACT_VERSION),
        **{
            key: copy.deepcopy(snapshot.get(key))
            for key in (
                "target_date", "signal_date", "feature_cutoff_at", "generated_label", "forecast_end_date",
                "forecast_horizon", "schema_version", "selector_mode", "model_version",
                "weights_version", "universe_version", "calendar_version",
            )
            if key in snapshot
        },
        "global_decision": _global_ui_summary(snapshot),
        "production_decision": _production_ui_summary(snapshot),
        "decision_evidence": _decision_evidence(snapshot),
        "event_stats": _event_stats(snapshot),
        "markets": {market: _compact_ui_market(snapshot, market) for market in LIVE_MARKETS},
        "analysis_models": summarize_analysis_models(snapshot),
        "history_summary": {
            key: compact_runtime_value(latest_summary[key])
            for key in ("formal_sample_status", "outcome_validation")
            if key in latest_summary
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_WORKER_UI_BOOTSTRAP_BYTES:
        raise ValueError(
            f"worker UI bootstrap byte-size limit exceeded: {len(encoded)} > {MAX_WORKER_UI_BOOTSTRAP_BYTES}"
        )
    forbidden = (
        '"evaluated_candidates"',
        '"production_rule_inputs"',
        '"point_in_time_universe"',
        '"kline"',
        '"events"',
    )
    encoded_text = encoded.decode("utf-8")
    for key in forbidden:
        if key in encoded_text:
            raise ValueError(f"worker UI bootstrap unexpectedly contains {key}")
    return payload


def build_worker_ui_candidates(snapshot: dict, source_snapshot_bytes: bytes) -> dict:
    roles, ranks = _candidate_role_maps(snapshot)
    candidates: dict[tuple[str, str], dict] = {}
    for market, raw_candidate in iter_live_candidates(snapshot):
        candidate = compact_ui_candidate(raw_candidate, market, detail=True)
        if candidate is None:
            continue
        identity = (market, candidate["code"])
        current = candidates.get(identity)
        if current is None or len(json.dumps(candidate, ensure_ascii=False)) > len(json.dumps(current, ensure_ascii=False)):
            candidates[identity] = candidate
    production = snapshot.get("production_decision") or {}
    qualifications: dict[tuple[str, str], dict] = {}
    for row in [production.get("primary"), *(production.get("qualified_candidates") or [])]:
        if not isinstance(row, dict) or row.get("market") not in LIVE_MARKETS:
            continue
        market = str(row["market"])
        code = normalize_live_code(row.get("code") or row.get("symbol"), market)
        if code:
            qualifications[(market, code)] = summarize_production_candidate(row) or {}
    rows = []
    for identity in sorted(candidates, key=lambda item: (LIVE_MARKETS.index(item[0]), ranks.get(item, 10_000), item[1])):
        candidate = candidates[identity]
        candidate["decision_role"] = roles.get(identity, "watchlist")
        if identity in ranks:
            candidate["legacy_rank"] = ranks[identity]
        if identity in qualifications:
            candidate["production_qualification"] = qualifications[identity]
        rows.append(candidate)
    payload = {
        **_ui_identity_envelope(snapshot, source_snapshot_bytes, WORKER_UI_CANDIDATES_CONTRACT_VERSION),
        "candidates": rows,
        "candidate_count": len(rows),
        "dual_low_model": compact_runtime_value(((snapshot.get("analysis_models") or {}).get("dual_low") or {})),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_WORKER_UI_CANDIDATES_BYTES:
        raise ValueError(
            f"worker UI candidates byte-size limit exceeded: {len(encoded)} > {MAX_WORKER_UI_CANDIDATES_BYTES}"
        )
    return payload


def build_worker_ui_events(snapshot: dict, source_snapshot_bytes: bytes) -> dict:
    raw_events = snapshot.get("events")
    original_items = _snapshot_event_items(snapshot)
    sorted_items = sorted(original_items, key=_event_sort_key)
    bound_ids = _decision_bound_event_ids(snapshot)
    bound_set = set(bound_ids)
    available_ids = {
        str(item.get("event_id"))
        for item in sorted_items
        if item.get("event_id")
    }
    missing_ids = sorted(bound_set - available_ids)
    if missing_ids:
        raise ValueError(
            "decision-bound event evidence is missing from UI event source: "
            + ", ".join(missing_ids)
        )
    bound_items = [
        item for item in sorted_items
        if str(item.get("event_id") or "") in bound_set
    ]
    other_items = [
        item for item in sorted_items
        if str(item.get("event_id") or "") not in bound_set
    ]
    identity = _ui_identity_envelope(
        snapshot,
        source_snapshot_bytes,
        WORKER_UI_EVENTS_CONTRACT_VERSION,
    )
    event_metadata = {
        key: copy.deepcopy(value)
        for key, value in (raw_events.items() if isinstance(raw_events, dict) else [])
        if key != "items"
    }

    def candidate_payload(other_count: int) -> dict:
        selected = sorted(
            [*bound_items, *other_items[:other_count]],
            key=_event_sort_key,
        )
        events = copy.deepcopy(event_metadata)
        if isinstance(raw_events, dict):
            events["items"] = copy.deepcopy(selected)
        else:
            events = copy.deepcopy(selected)
        published = len(selected)
        total = len(original_items)
        return {
            **identity,
            "events": events,
            "event_publication": {
                "total": total,
                "published": published,
                "truncated": total - published,
                "is_truncated": published < total,
                "decision_bound_event_count": len(bound_ids),
                "decision_bound_record_count": len(bound_items),
            },
        }

    def encoded_size(other_count: int) -> int:
        return len(json.dumps(
            candidate_payload(other_count),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode())

    if encoded_size(0) > MAX_WORKER_UI_EVENTS_BYTES:
        raise ValueError(
            "decision-bound events exceed worker UI event byte-size limit: "
            f"{encoded_size(0)} > {MAX_WORKER_UI_EVENTS_BYTES}"
        )
    low, high = 0, len(other_items)
    while low < high:
        middle = (low + high + 1) // 2
        if encoded_size(middle) <= MAX_WORKER_UI_EVENTS_BYTES:
            low = middle
        else:
            high = middle - 1
    payload = candidate_payload(low)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_WORKER_UI_EVENTS_BYTES:
        raise ValueError(
            f"worker UI events byte-size limit exceeded: {len(encoded)} > {MAX_WORKER_UI_EVENTS_BYTES}"
        )
    published_ids = {
        str(item.get("event_id"))
        for item in _snapshot_event_items({"events": payload["events"]})
        if item.get("event_id")
    }
    if not bound_set.issubset(published_ids):
        raise ValueError("worker UI events silently dropped decision-bound evidence")
    return payload


def build_worker_ui_assets(
    snapshot: dict,
    latest_summary: dict,
    source_snapshot_bytes: bytes,
) -> dict[str, dict]:
    return {
        "ui-bootstrap.json": build_worker_ui_bootstrap(snapshot, latest_summary, source_snapshot_bytes),
        "ui-candidates.json": build_worker_ui_candidates(snapshot, source_snapshot_bytes),
        "ui-events.json": build_worker_ui_events(snapshot, source_snapshot_bytes),
    }


def write_worker_runtime_assets(
    snapshot: dict,
    latest_summary: dict,
    source_snapshot_bytes: bytes,
    output_dir: pathlib.Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = {
        "runtime.json": build_worker_runtime(snapshot, latest_summary, source_snapshot_bytes),
        "live-index.json": build_worker_live_index(snapshot, source_snapshot_bytes),
        **build_worker_ui_assets(snapshot, latest_summary, source_snapshot_bytes),
    }
    for name, payload in assets.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )


def _stable_json_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _candidate_asset_id(snapshot_key: str, candidate: dict) -> str:
    market = str(candidate.get("market") or "")
    code = str(candidate.get("code") or candidate.get("symbol") or "")
    digest = hashlib.sha256(f"{snapshot_key}|{market}|{code}".encode()).hexdigest()[:20]
    return f"cand_{digest}"


def _candidate_list_row(snapshot_key: str, candidate: dict) -> dict:
    """Keep the first-page shortlist small while retaining decision fields."""

    qualification = candidate.get("production_qualification")
    qualification = qualification if isinstance(qualification, dict) else {}
    realtime = candidate.get("realtime")
    realtime = realtime if isinstance(realtime, dict) else {}
    plan = (
        qualification.get("ten_day_trade_plan")
        or candidate.get("ten_day_trade_plan")
        or {}
    )
    result = {
        "id": _candidate_asset_id(snapshot_key, candidate),
        "market": candidate.get("market"),
        "code": candidate.get("code") or candidate.get("symbol"),
        "name": candidate.get("name"),
        "currency": candidate.get("currency") or realtime.get("currency"),
        "decision_role": candidate.get("decision_role"),
        "legacy_rank": candidate.get("legacy_rank"),
        "recommendation_degree": candidate.get("recommendation_degree"),
        "score": candidate.get("score"),
        "price": realtime.get("price") or candidate.get("entry_price"),
        "change_pct": realtime.get("change_pct"),
        "source_as_of": realtime.get("source_as_of"),
        "estimated_10d_range": (
            qualification.get("estimated_10d_range")
            or candidate.get("estimated_10d_range")
        ),
        "risk_reward": qualification.get("risk_reward") or candidate.get("risk_reward"),
        "reason_tags": candidate.get("reason_tags") or [],
        "qualification": {
            key: copy.deepcopy(qualification.get(key))
            for key in (
                "qualification_id", "status", "qualification_track",
                "qualification_score", "score_kind", "probability_status",
                "data_quality_score", "entry_price", "entry_trade_date",
                "forecast_end_trade_date", "estimated_10d_range", "risk_reward",
            )
            if key in qualification
        } or None,
        # This is a lossless projection of the server-owned trade-plan
        # contract.  The asset layer must never infer prices or rename fields.
        "ten_day_trade_plan": {
            key: copy.deepcopy(plan.get(key))
            for key in (
                "contract_version", "status", "horizon_trade_days",
                "reference_quote", "entry_zone", "entry_trade_date",
                "invalidation", "target", "position_limit",
                "catalyst_expiry_date", "review_end_trade_date", "exit_rules",
                "is_personalized_advice",
            )
            if key in plan
        } if isinstance(plan, dict) else {},
        "detail_available": True,
    }
    return {key: value for key, value in result.items() if value is not None}


def _write_content_addressed_asset(
    data_root: pathlib.Path,
    kind: str,
    payload: dict,
) -> tuple[str, str, int]:
    encoded = _stable_json_bytes(payload)
    digest = hashlib.sha256(encoded).hexdigest()
    key = f"{kind}/{digest}.json"
    target = data_root / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    return key, digest, len(encoded)


def _scheduler_health(snapshot: dict, history_manifest: dict) -> dict:
    automation = snapshot.get("automation")
    automation = automation if isinstance(automation, dict) else {}
    source_health = automation.get("scheduler_health")
    source_health = source_health if isinstance(source_health, dict) else {}

    def parsed(value: object) -> dt.datetime | None:
        try:
            result = dt.datetime.fromisoformat(str(value or ""))
        except (TypeError, ValueError):
            return None
        return result if result.tzinfo is not None and result.utcoffset() is not None else None

    generated = parsed(snapshot.get("generated_at"))
    checkpoint = parsed(
        source_health.get("effective_checkpoint") or automation.get("scheduled_slot")
    )
    generation_delay = (
        max(0, int((generated - checkpoint).total_seconds()))
        if generated is not None and checkpoint is not None
        else None
    )
    # Snapshot history is deliberately selective (latest daily run, qualified
    # rules, and formal observations).  It is not a complete scheduler ledger
    # and therefore cannot truthfully prove that omitted checkpoints were
    # missed.  Publish an explicit unknown until a complete checkpoint ledger
    # is introduced; never turn retention policy into a false SLA incident.
    checkpoint_ledger = history_manifest.get("scheduler_checkpoint_ledger")
    checkpoint_ledger = checkpoint_ledger if isinstance(checkpoint_ledger, dict) else {}
    checkpoint_rows = checkpoint_ledger.get("checkpoints")
    checkpoint_complete = (
        checkpoint_ledger.get("contract_version") == "scheduler-checkpoint-ledger-v1"
        and checkpoint_ledger.get("coverage_complete_24h") is True
        and isinstance(checkpoint_rows, list)
        and all(isinstance(row, dict) for row in checkpoint_rows)
    )
    missed = (
        sum(str(row.get("status") or "").upper() == "MISSED" for row in checkpoint_rows)
        if checkpoint_complete
        else None
    )
    checkpoint_coverage_status = (
        "COMPLETE_24H_LEDGER" if checkpoint_complete else "UNAVAILABLE_NO_COMPLETE_LEDGER"
    )
    start_delay = source_health.get(
        "scheduler_start_delay_seconds", automation.get("scheduler_delay_seconds")
    )
    if not isinstance(start_delay, int) or isinstance(start_delay, bool) or start_delay < 0:
        start_delay = None
    recovery_mode = str(automation.get("recovery_mode") or "none")
    if recovery_mode == "late_cron_recovery" and start_delay == 0:
        start_delay = None
    source_invocation = source_health.get(
        "source_invocation_slot", automation.get("source_invocation_slot")
    )
    effective_checkpoint = source_health.get(
        "effective_checkpoint", automation.get("scheduled_slot")
    )
    effective_invocation = source_health.get(
        "effective_invocation_slot", automation.get("scheduled_invocation_slot")
    )
    return {
        "contract_version": "scheduler-health-v1",
        "source_invocation_slot": source_invocation,
        "effective_checkpoint": effective_checkpoint,
        "effective_invocation_slot": effective_invocation,
        "scheduler_start_delay_seconds": start_delay,
        "generation_delay_seconds": generation_delay,
        "publication_delay_seconds": None,
        "missed_checkpoints_24h": missed,
        "checkpoint_coverage_status": checkpoint_coverage_status,
        "checkpoint_evidence_contract_version": (
            checkpoint_ledger.get("contract_version") if checkpoint_complete else None
        ),
        "recovery_mode": source_health.get("recovery_mode") or recovery_mode,
        "generation_started_at": source_health.get("generation_started_at"),
        "generated_at": snapshot.get("generated_at"),
        "published_at": None,
    }


def compact_history_list_row(row: dict) -> dict:
    """Keep the paginated history index bounded without losing its primary audit row.

    Full model diagnostics and every qualified candidate remain available in
    the immutable snapshot and the archival manifest.  The history list UI
    only consumes the production primary plus the published counts, so copying
    those large duplicate structures into every list row is both unnecessary
    and capable of blocking an otherwise valid data publication.
    """

    result = copy.deepcopy(row)
    result.pop("analysis_models", None)
    production = result.get("production_decision")
    if isinstance(production, dict):
        production.pop("qualified_candidates", None)
    return result


def build_data_manifest_assets(
    snapshot: dict,
    source_snapshot_bytes: bytes,
    ui_assets: dict[str, dict],
    history_manifest: dict,
    data_root: pathlib.Path,
) -> dict:
    """Build one identity-bound immutable data generation plus a small alias.

    The generated files are also shipped as Worker assets.  Production can
    publish the exact same files to R2, while a missing R2 binding/object safely
    falls back to this last-known-good generation without mixing identities.
    """

    snapshot_key = str(snapshot.get("snapshot_key") or "")
    generated_at = str(snapshot.get("generated_at") or "")
    source_sha256 = hashlib.sha256(source_snapshot_bytes).hexdigest()
    source_byte_size = len(source_snapshot_bytes)
    identity = {
        "snapshot_key": snapshot_key,
        "generated_at": generated_at,
        "snapshot_sha256": source_sha256,
        "snapshot_byte_size": source_byte_size,
        "source_snapshot": {
            "sha256": source_sha256,
            "byte_size": source_byte_size,
        },
    }

    summary_payload = copy.deepcopy(ui_assets["ui-bootstrap.json"])
    runtime_payload = json.loads((data_root / "picks" / "runtime.json").read_text(encoding="utf-8"))
    live_index_payload = json.loads((data_root / "picks" / "live-index.json").read_text(encoding="utf-8"))
    candidate_source = ui_assets["ui-candidates.json"]
    candidate_rows = [
        row for row in (candidate_source.get("candidates") or [])
        if isinstance(row, dict)
    ]
    compact_rows = [_candidate_list_row(snapshot_key, row) for row in candidate_rows]
    scanned_count = sum(
        int(
            (((snapshot.get("markets") or {}).get(market) or {}).get("stats") or {}).get(
                "recall_selected_size"
            )
            or 0
        )
        for market in LIVE_MARKETS
    )
    candidate_payload = {
        "contract_version": CANDIDATE_LIST_CONTRACT_VERSION,
        **identity,
        "candidate_count": len(compact_rows),
        "scanned_count": scanned_count,
        "candidates": compact_rows,
        "dual_low_model": copy.deepcopy(candidate_source.get("dual_low_model") or {}),
    }
    event_source = ui_assets["ui-events.json"]
    raw_events = event_source.get("events")
    event_items = raw_events.get("items") if isinstance(raw_events, dict) else raw_events
    event_payload = {
        "contract_version": EVENT_LIST_CONTRACT_VERSION,
        **identity,
        "event_count": len(event_items or []),
        "event_publication": copy.deepcopy(event_source.get("event_publication") or {}),
        "events": copy.deepcopy(event_items or []),
    }
    for index, row in enumerate(event_payload["events"]):
        byte_size = len(_stable_json_bytes(row))
        if byte_size > MAX_DATA_EVENT_ROW_BYTES:
            raise ValueError(
                f"event list row {index} exceeds {MAX_DATA_EVENT_ROW_BYTES} bytes: {byte_size}"
            )
    history_rows = [
        compact_history_list_row(row)
        for row in (history_manifest.get("summaries") or [])
        if isinstance(row, dict)
    ]
    history_payload = {
        "contract_version": HISTORY_LIST_CONTRACT_VERSION,
        **identity,
        "history": history_rows,
        "history_evaluation": copy.deepcopy(history_manifest.get("history_evaluation") or {}),
        "observation_ledger": copy.deepcopy(history_manifest.get("observation_ledger") or {}),
        "observation_performance": copy.deepcopy(history_manifest.get("observation_performance") or {}),
        "rule_outcome_tracking": copy.deepcopy(history_manifest.get("rule_outcome_tracking") or {}),
    }
    for index, row in enumerate(history_payload["history"]):
        byte_size = len(_stable_json_bytes(row))
        if byte_size > MAX_DATA_HISTORY_ROW_BYTES:
            raise ValueError(
                f"history list row {index} exceeds {MAX_DATA_HISTORY_ROW_BYTES} bytes: {byte_size}"
            )

    runtime_key, runtime_sha, runtime_size = _write_content_addressed_asset(
        data_root, "runtime", runtime_payload
    )
    live_index_key, live_index_sha, live_index_size = _write_content_addressed_asset(
        data_root, "live-index", live_index_payload
    )
    summary_key, summary_sha, summary_size = _write_content_addressed_asset(
        data_root, "summary", summary_payload
    )
    candidates_key, candidates_sha, candidates_size = _write_content_addressed_asset(
        data_root, "candidates", candidate_payload
    )
    events_key, events_sha, events_size = _write_content_addressed_asset(
        data_root, "events", event_payload
    )
    history_key, history_sha, history_size = _write_content_addressed_asset(
        data_root, "history", history_payload
    )
    if summary_size > MAX_DATA_SUMMARY_BYTES:
        raise ValueError(f"data summary exceeds {MAX_DATA_SUMMARY_BYTES} bytes: {summary_size}")
    if candidates_size > MAX_DATA_CANDIDATE_LIST_BYTES:
        raise ValueError(
            f"candidate list exceeds {MAX_DATA_CANDIDATE_LIST_BYTES} bytes: {candidates_size}"
        )

    detail_keys: dict[str, str] = {}
    detail_meta: dict[str, dict] = {}
    for compact, detail in zip(compact_rows, candidate_rows, strict=True):
        candidate_id = str(compact["id"])
        payload = {
            "contract_version": CANDIDATE_DETAIL_CONTRACT_VERSION,
            **identity,
            "id": candidate_id,
            "candidate": copy.deepcopy(detail),
        }
        key, digest, byte_size = _write_content_addressed_asset(
            data_root, "candidate-details", payload
        )
        if byte_size > MAX_DATA_CANDIDATE_DETAIL_BYTES:
            raise ValueError(
                f"candidate detail {candidate_id} exceeds {MAX_DATA_CANDIDATE_DETAIL_BYTES} bytes: {byte_size}"
            )
        detail_keys[candidate_id] = key
        detail_meta[candidate_id] = {"sha256": digest, "byte_size": byte_size}

    manifest = {
        "contract_version": DATA_MANIFEST_CONTRACT_VERSION,
        **identity,
        "runtime_key": runtime_key,
        "live_index_key": live_index_key,
        "summary_key": summary_key,
        "candidates_key": candidates_key,
        "events_key": events_key,
        "history_key": history_key,
        "candidate_detail_keys": detail_keys,
        "scheduler_health": _scheduler_health(snapshot, history_manifest),
        "assets": {
            "runtime": {"key": runtime_key, "sha256": runtime_sha, "byte_size": runtime_size},
            "live_index": {"key": live_index_key, "sha256": live_index_sha, "byte_size": live_index_size},
            "summary": {"key": summary_key, "sha256": summary_sha, "byte_size": summary_size},
            "candidates": {"key": candidates_key, "sha256": candidates_sha, "byte_size": candidates_size},
            "events": {"key": events_key, "sha256": events_sha, "byte_size": events_size},
            "history": {"key": history_key, "sha256": history_sha, "byte_size": history_size},
            "candidate_details": detail_meta,
        },
    }
    published_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    manifest["published_at"] = published_at
    manifest["publication_mode"] = "embedded-worker-asset-v1"
    try:
        generated = dt.datetime.fromisoformat(generated_at)
        published = dt.datetime.fromisoformat(published_at)
        manifest["scheduler_health"]["publication_delay_seconds"] = max(
            0, int((published - generated).total_seconds())
        )
    except (TypeError, ValueError):
        manifest["scheduler_health"]["publication_delay_seconds"] = None
    manifest["scheduler_health"]["published_at"] = published_at
    manifest_without_digest = _stable_json_bytes(manifest)
    manifest["manifest_sha256"] = hashlib.sha256(manifest_without_digest).hexdigest()
    (data_root / "latest-manifest.json").write_bytes(_stable_json_bytes(manifest))
    return manifest


def history_kind(global_decision: dict | None) -> str:
    if (
        isinstance(global_decision, dict)
        and global_decision.get("contract_version") == "global-10d-v1"
        and global_decision.get("decision_scope") == "global_10d"
        and global_decision.get("action_basis") == "strict_cross_market_gate_v1"
    ):
        return "global_10d_v1"
    return "legacy_snapshot"


def select_public_snapshot_files(summaries: list[dict], limit: int = MAX_PUBLIC_FULL_SNAPSHOT_DAYS) -> set[str]:
    """Select bounded full assets while retaining every compact history row."""

    if limit <= 0:
        return set()
    ordered = sorted(
        (item for item in summaries if isinstance(item, dict)),
        key=lambda item: f"{item.get('target_date') or ''}{item.get('generated_at') or ''}",
        reverse=True,
    )
    representatives: dict[str, dict] = {}
    for item in ordered:
        day_key = str(
            item.get("target_date")
            or item.get("signal_date")
            or item.get("snapshot_key")
            or item.get("cache_key")
            or ""
        )
        if not day_key:
            continue
        current = representatives.get(day_key)
        if current is None or (
            current.get("history_kind") != "global_10d_v1"
            and item.get("history_kind") == "global_10d_v1"
        ):
            representatives[day_key] = item
    return {
        str(item.get("cache_key"))
        for item in list(representatives.values())[:limit]
        if isinstance(item.get("cache_key"), str) and item.get("cache_key")
    }


def summarize_pick(
    path: pathlib.Path,
    shadow_outcome_map: dict[str, dict] | None = None,
    executable_outcome_map: dict[str, dict] | None = None,
) -> dict | None:
    try:
        pick = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    source_snapshot = (
        str(pick.get("snapshot_key"))
        if path.name == "latest.json" and pick.get("snapshot_key")
        else path.name
    )
    legacy_summary = summarize_decision(pick.get("decision") or {})
    raw_global_decision = summarize_global_decision(pick)
    production_decision = summarize_production_decision(pick)
    kind = history_kind(raw_global_decision)
    is_global_contract = kind == "global_10d_v1"
    global_decision = raw_global_decision if is_global_contract else None
    if is_global_contract:
        action = global_decision.get("action") or "NO_VALID_PICK"
        title = "跨市场候选待复核" if action == "REVIEW_EXECUTABLE_PICK" else "当前没有可执行跨市场候选"
        message = " · ".join(global_decision.get("blocker_codes") or [])
        has_primary = bool(global_decision.get("primary"))
    else:
        action = "LEGACY_ONLY"
        title = "Legacy 规则快照"
        message = "PRE_GLOBAL_10D_CONTRACT"
        has_primary = False
    summary = {
        "target_date": pick.get("target_date"),
        "signal_date": pick.get("signal_date"),
        "feature_cutoff_at": pick.get("feature_cutoff_at"),
        "generated_at": pick.get("generated_at"),
        "generated_label": pick.get("generated_label"),
        "snapshot_key": pick.get("snapshot_key") or path.name,
        "cache_key": path.name,
        "forecast_end_date": pick.get("forecast_end_date"),
        "forecast_horizon": pick.get("forecast_horizon"),
        "schema_version": pick.get("schema_version"),
        "selector_mode": pick.get("selector_mode"),
        "model_version": pick.get("model_version"),
        "weights_version": pick.get("weights_version"),
        "universe_version": pick.get("universe_version"),
        "automation": compact_runtime_value(pick.get("automation") or {}),
        "history_kind": kind,
        "decision_scope": "global_10d" if is_global_contract else "legacy_market_rules",
        "action": action,
        "title": title,
        "message": message,
        "has_primary": has_primary,
        "a_share_legacy": legacy_summary,
        "global_decision": global_decision,
        "production_decision": production_decision,
        "production_action": (
            production_decision.get("action") if production_decision else "NO_QUALIFIED_PICK"
        ),
        "qualification_history_kind": (
            "qualified_rule_10d_v1"
            if production_decision
            and production_decision.get("contract_version") == "production-rule-10d-v1"
            else None
        ),
    }
    # Do not admit snapshot-embedded outcomes into formal performance.  Only a
    # track-aware join from data/outcomes/executable is authoritative.
    executable_outcome = matching_executable_outcome(
        pick,
        executable_outcome_map or {},
        source_snapshot,
    )
    if executable_outcome:
        summary["outcome"] = executable_outcome
    shadow_outcome = matching_shadow_outcome(
        pick,
        shadow_outcome_map or {},
        source_snapshot,
    )
    if shadow_outcome:
        summary["shadow_outcome"] = shadow_outcome
    analysis_models = summarize_analysis_models(pick)
    if analysis_models:
        summary["analysis_models"] = analysis_models
    primary = global_decision.get("primary") if global_decision else None
    if isinstance(primary, dict):
        for key in ("code", "name", "probability", "expected_net_utility", "transaction_cost", "tail_risk", "model_id"):
            if key in primary:
                summary[key] = primary.get(key)
    production_primary = production_decision.get("primary") if production_decision else None
    if isinstance(production_primary, dict):
        summary["qualification_id"] = production_primary.get("qualification_id")
        summary["qualification_score"] = production_primary.get("qualification_score")
    markets = pick.get("markets") or {}
    if markets:
        summary["markets"] = {}
        summary["market_regimes"] = {}
        for key, section in markets.items():
            section = section or {}
            decision_summary = summarize_decision(section.get("decision") or {})
            regime_summary = summarize_market_regime(section)
            decision_summary["market_regime"] = regime_summary
            summary["markets"][key] = decision_summary
            summary["market_regimes"][key] = regime_summary
    return history_evaluation.annotate_formal_sample(summary)


def main() -> None:
    validate_required_assets()
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(exist_ok=True)
    shutil.copy2(STATIC / "index.html", PUBLIC / "index.html")
    copy_tree(STATIC, PUBLIC / "static")

    public_picks = PUBLIC / "data" / "picks"
    public_picks.mkdir(parents=True, exist_ok=True)
    for stale in public_picks.glob("*.json"):
        stale.unlink()

    outcome_root = ROOT / "data" / "outcomes"
    shadow_inventory = history_evaluation.load_ledger_inventory(
        outcome_root,
        history_evaluation.SHADOW_TRACK,
    )
    executable_inventory = history_evaluation.load_ledger_inventory(
        outcome_root / "executable",
        history_evaluation.EXECUTABLE_TRACK,
    )
    shadow_outcome_map = shadow_inventory["records"]
    executable_outcome_map = executable_inventory["records"]
    rule_outcome_batches = rule_outcome_ledger.load_rule_outcome_batches(
        outcome_root / "rule-settlements"
    )
    summaries = []
    snapshots = {}
    for path in sorted(PICKS.glob("*.json")):
        if path.name != "latest.json":
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                snapshot = None
            if isinstance(snapshot, dict):
                snapshots[path.name] = snapshot
            summary = summarize_pick(path, shadow_outcome_map, executable_outcome_map)
            if summary:
                summaries.append(summary)

    summaries.sort(
        key=lambda item: f"{item.get('target_date') or ''}{item.get('generated_at') or ''}",
        reverse=True,
    )
    latest_summary = (
        summarize_pick(PICKS / "latest.json", shadow_outcome_map, executable_outcome_map)
        if (PICKS / "latest.json").is_file()
        else None
    )
    latest_summary = latest_summary or {}
    published_files = select_public_snapshot_files(summaries)
    latest_immutable = latest_summary.get("snapshot_key")
    if isinstance(latest_immutable, str) and (PICKS / latest_immutable).is_file():
        published_files.add(latest_immutable)
    for summary in summaries:
        summary["full_snapshot_available"] = summary.get("cache_key") in published_files
    for path in sorted(PICKS.glob("*.json")):
        if path.name == "latest.json" or path.name in published_files:
            write_public_pick(
                path,
                public_picks / path.name,
                shadow_outcome_map,
                executable_outcome_map,
            )
    public_latest = public_picks / "latest.json"
    if public_latest.is_file():
        source_snapshot_bytes = public_latest.read_bytes()
        try:
            public_latest_snapshot = json.loads(source_snapshot_bytes)
        except (TypeError, ValueError) as exc:
            raise ValueError("Published latest snapshot is not valid JSON") from exc
        if not isinstance(public_latest_snapshot, dict):
            raise ValueError("Published latest snapshot must be an object")
        write_worker_runtime_assets(
            public_latest_snapshot,
            latest_summary,
            source_snapshot_bytes,
            public_picks,
        )
    evaluation = history_evaluation.build_history_evaluation(
        summaries,
        snapshots,
        shadow_inventory,
        executable_inventory,
        rule_outcome_batches,
    )
    observation_cohorts = model_observation_ledger.load_observation_cohorts(
        outcome_root / "observations"
    )
    observation_batches = observation_outcome_ledger.load_outcome_batches(
        outcome_root / "observation-settlements"
    )
    observation_performance = history_evaluation.evaluate_observation_performance(
        observation_cohorts,
        observation_batches,
    )
    observation_summary = model_observation_ledger.summarize_observation_cohorts(
        observation_cohorts
    )
    observation_summary.update(
        {
            "settlement_status": observation_performance["status"],
            "outcome_prediction_count": observation_performance["prediction_count"],
            "pending_maturity_count": observation_performance["pending_maturity_count"],
            "pending_data_count": observation_performance["pending_data_count"],
            "settled_count": observation_performance["settled_count"],
            "untracked_count": observation_performance["untracked_count"],
        }
    )
    evaluation["observation_ledger"] = observation_summary
    evaluation["observation_performance"] = observation_performance
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "schema_version": latest_summary.get("schema_version"),
        "selector_mode": latest_summary.get("selector_mode"),
        "model_version": latest_summary.get("model_version"),
        "weights_version": latest_summary.get("weights_version"),
        "universe_version": latest_summary.get("universe_version"),
        "market_regimes": latest_summary.get("market_regimes") or {},
        "analysis_models": latest_summary.get("analysis_models") or {},
        "files": sorted(published_files),
        "full_snapshot_retention_days": MAX_PUBLIC_FULL_SNAPSHOT_DAYS,
        "summaries": summaries,
        "history_evaluation": evaluation,
        "shadow_ledger": evaluation["shadow_ledger"],
        "executable_ledger": evaluation["executable_ledger"],
        "observation_ledger": observation_summary,
        "observation_performance": observation_performance,
        "rule_outcome_tracking": evaluation.get("rule_outcome_tracking") or {},
    }
    (public_picks / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if public_latest.is_file():
        ui_assets = {
            name: json.loads((public_picks / name).read_text(encoding="utf-8"))
            for name in ("ui-bootstrap.json", "ui-candidates.json", "ui-events.json")
        }
        build_data_manifest_assets(
            public_latest_snapshot,
            source_snapshot_bytes,
            ui_assets,
            manifest,
            PUBLIC / "data",
        )


if __name__ == "__main__":
    main()
