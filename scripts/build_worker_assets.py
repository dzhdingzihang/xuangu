#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shutil
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import history_evaluation


PUBLIC = ROOT / "public"
STATIC = ROOT / "static"
PICKS = ROOT / "data" / "picks"
OUTCOMES = ROOT / "data" / "outcomes"
REQUIRED_STATIC_FILES = ("index.html", "styles.css", "app.js")
MANIFEST_VERSION = "selector-manifest-v2"
MAX_PUBLIC_FULL_SNAPSHOT_DAYS = 30
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
    evaluation = history_evaluation.build_history_evaluation(
        summaries,
        snapshots,
        shadow_inventory,
        executable_inventory,
    )
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
    }
    (public_picks / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
