#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
STATIC = ROOT / "static"
PICKS = ROOT / "data" / "picks"
REQUIRED_STATIC_FILES = ("index.html", "styles.css", "app.js")
MANIFEST_VERSION = "selector-manifest-v2"
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


def write_public_pick(source: pathlib.Path, target: pathlib.Path) -> None:
    """Publish JSON without leaking machine-specific research metadata."""
    try:
        pick = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        shutil.copy2(source, target)
        return
    serenity = ((pick.get("research_runtime") or {}).get("serenity_skill") or {})
    if serenity:
        serenity.pop("path", None)
        serenity["skill_metadata_detected"] = bool(serenity.get("installed"))
        serenity["mode"] = "built-in-lens"
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
            for key in (
                "model_id",
                "status",
                "calibrated",
                "costs_ready",
                "tail_risk_ready",
                "participates_in_decision",
                "probability",
            )
            if key in ten_day
        }
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
                "label_version",
                "market",
                "code",
                "name",
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


def summarize_outcome(pick: dict) -> dict | None:
    outcome = pick.get("ten_day_outcome") or pick.get("outcome")
    if not isinstance(outcome, dict):
        return None
    keys = (
        "status",
        "prediction_id",
        "model_id",
        "label_version",
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
        "calendar_id",
        "currency",
        "fx_rate_source",
        "positive_label",
        "settled_at",
    )
    summary = {key: outcome.get(key) for key in keys if key in outcome}
    return summary or None


def summarize_pick(path: pathlib.Path) -> dict | None:
    try:
        pick = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
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
    outcome = summarize_outcome(pick)
    if outcome:
        summary["outcome"] = outcome
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
    return summary


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

    files = []
    summaries = []
    for path in sorted(PICKS.glob("*.json")):
        write_public_pick(path, public_picks / path.name)
        if path.name != "latest.json":
            files.append(path.name)
            summary = summarize_pick(path)
            if summary:
                summaries.append(summary)

    summaries.sort(
        key=lambda item: f"{item.get('target_date') or ''}{item.get('generated_at') or ''}",
        reverse=True,
    )
    latest_summary = summarize_pick(PICKS / "latest.json") if (PICKS / "latest.json").is_file() else None
    latest_summary = latest_summary or {}
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "schema_version": latest_summary.get("schema_version"),
        "selector_mode": latest_summary.get("selector_mode"),
        "model_version": latest_summary.get("model_version"),
        "weights_version": latest_summary.get("weights_version"),
        "universe_version": latest_summary.get("universe_version"),
        "market_regimes": latest_summary.get("market_regimes") or {},
        "analysis_models": latest_summary.get("analysis_models") or {},
        "files": files,
        "summaries": summaries,
    }
    (public_picks / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
