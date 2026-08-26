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


PUBLIC = ROOT / "public"
STATIC = ROOT / "static"
PICKS = ROOT / "data" / "picks"
OUTCOMES = ROOT / "data" / "outcomes"
REQUIRED_STATIC_FILES = ("index.html", "styles.css", "app.js")
MANIFEST_VERSION = "selector-manifest-v2"
MAX_PUBLIC_FULL_SNAPSHOT_DAYS = 30
MAX_QUALIFIED_SUMMARY_CANDIDATES = 20
CURRENT_PRODUCTION_MODEL_VERSION = "smart-selector-2026-08-26.2-dual-track-rule"
PRODUCTION_RULE_CONTRACTS = {
    ("strict_rule_qualification_v1", "ten-day-audited-rule-ensemble-v1"),
    ("candidate_level_rule_qualification_v2", "ten-day-audited-rule-ensemble-v2"),
    ("dual_track_candidate_qualification_v3", "ten-day-audited-rule-ensemble-v3"),
}
CURRENT_PRODUCTION_RULE_CONTRACT = (
    "dual_track_candidate_qualification_v3",
    "ten-day-audited-rule-ensemble-v3",
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
    "generation_attempt",
    "run_id",
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
WORKER_LIVE_CODE_NORMALIZATION = "worker-facing-live-code-v1"
RUNTIME_FORBIDDEN_KEYS = {
    "candidate_snapshot",
    "evaluated_candidates",
    "production_rule_inputs",
    "events",
}


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
            "research_priority",
            "blocker_codes",
            "market_states",
            "automatic_external_evidence_count",
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
    # CURRENT model <-> V3 contract is a strict bijection.  Historical V1/V2
    # contracts remain readable, while a V3 decision under an older (or
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
    }
    for name, payload in assets.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )


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
    )
    observation_summary = model_observation_ledger.summarize_observation_cohorts(
        model_observation_ledger.load_observation_cohorts(outcome_root / "observations")
    )
    evaluation["observation_ledger"] = observation_summary
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
    }
    (public_picks / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
