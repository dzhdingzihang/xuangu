#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pathlib


VALID_MODEL_STATUSES = {"available", "unavailable"}
VALID_CANDIDATE_STATUSES = {"ranked", "rejected", "unavailable", "not_applicable"}


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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

    markets = snapshot.get("markets") or {}
    for market_key in ("a_share", "hk", "us"):
        if market_key not in markets:
            errors.append(f"markets.{market_key} is missing")
            continue
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
