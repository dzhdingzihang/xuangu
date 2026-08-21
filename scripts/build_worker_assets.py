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
        range_ = primary.get("estimated_2w_range") or primary.get("estimated_2d_range") or {}
        summary.update(
            {
                "code": primary.get("code"),
                "name": primary.get("name"),
                "confidence": primary.get("recommendation_degree") or primary.get("confidence"),
                "recommendation_degree": primary.get("recommendation_degree") or primary.get("confidence"),
                "estimated_2w_range": range_.get("text"),
                "estimated_2d_range": range_.get("text"),
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


def summarize_pick(path: pathlib.Path) -> dict | None:
    try:
        pick = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
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
        **summarize_decision(pick.get("decision") or {}),
    }
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
        "files": files,
        "summaries": summaries,
    }
    (public_picks / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
