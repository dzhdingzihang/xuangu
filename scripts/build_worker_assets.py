#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
STATIC = ROOT / "static"
PICKS = ROOT / "data" / "picks"


def copy_tree(source: pathlib.Path, target: pathlib.Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


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
        "model_version": pick.get("model_version"),
        **summarize_decision(pick.get("decision") or {}),
    }
    markets = pick.get("markets") or {}
    if markets:
        summary["markets"] = {
            key: summarize_decision((section or {}).get("decision") or {})
            for key, section in markets.items()
        }
    return summary


def main() -> None:
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
        shutil.copy2(path, public_picks / path.name)
        if path.name != "latest.json":
            files.append(path.name)
            summary = summarize_pick(path)
            if summary:
                summaries.append(summary)

    summaries.sort(
        key=lambda item: f"{item.get('target_date') or ''}{item.get('generated_at') or ''}",
        reverse=True,
    )
    manifest = {"files": files, "summaries": summaries}
    (public_picks / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
