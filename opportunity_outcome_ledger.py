"""Forward observations of frozen, verified-published opportunity rankings.

This ledger never reruns a scorer. Self-contained predictions outlive snapshot
retention, and descriptive observations never authorize production or calibration.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import pathlib
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping

import market_calendar
import rule_outcome_ledger as prices

TRACK = "RETURN_OPPORTUNITY"
PREDICTION_SCHEMA_VERSION = "opportunity-prediction-v1"
OUTCOME_SCHEMA_VERSION = "opportunity-outcome-v1"
BATCH_SCHEMA_VERSION = "opportunity-outcome-batch-v1"
DEFAULT_OUTCOME_DIRECTORY = pathlib.Path(__file__).resolve().parent / "data/outcomes/opportunity-settlements"
TRANSACTION_COSTS = dict(prices.TRANSACTION_COSTS)
REGISTERED_BENCHMARKS = dict(prices.REGISTERED_BENCHMARKS)
COST_VERSION = prices.COST_VERSION


class OpportunityOutcomeContractError(ValueError):
    pass


class OpportunityOutcomeConflictError(OpportunityOutcomeContractError):
    pass


def _digest(value):
    return prices._digest(value)


def _aware(value):
    try:
        return prices._aware(value).astimezone(dt.timezone.utc)
    except (ValueError, TypeError) as exc:
        raise OpportunityOutcomeContractError("timestamp must be timezone-aware") from exc


def _time(value):
    return _aware(value).isoformat()


def _number(value, *, positive=False):
    try:
        return prices._finite(value, "value", positive=positive)
    except ValueError as exc:
        raise OpportunityOutcomeContractError(str(exc)) from exc


def _key(value):
    if not isinstance(value, str) or not prices.VALID_SAFE_SNAPSHOT.fullmatch(value) or value == "latest.json":
        raise OpportunityOutcomeContractError("snapshot_key must be immutable and safe")
    return value


def _hash_without(value, field):
    return _digest({k: v for k, v in value.items() if k != field})


def prediction_id(row):
    return "opppred_" + _digest({k: v for k, v in row.items() if k not in {"prediction_id", "prediction_sha256"}})[:24]


def prediction_sha256(row):
    return _hash_without(row, "prediction_sha256")


def outcome_sha256(row):
    return _hash_without(row, "outcome_sha256")


def batch_sha256(batch):
    return _hash_without(batch, "batch_sha256")


def _source_digest(snapshot):
    # Runtime-only outcome summaries do not alter the frozen ranking evidence.
    return _digest({k: v for k, v in snapshot.items() if k != "opportunity_outcome_tracking"})


def _score_identity(board):
    weights = board.get("weights")
    if not isinstance(weights, dict) or not weights or any(type(v) not in (int, float) for v in weights.values()) or abs(sum(_number(v) for v in weights.values()) - 1) > 1e-8 or any(v < 0 for v in weights.values()):
        raise OpportunityOutcomeContractError("score weights are invalid")
    identity = {"contract_version": board["contract_version"], "score_version": board.get("score_version") or "return-opportunity-score-v1", "score_kind": board["score_kind"], "weights": copy.deepcopy(weights), "selection_policy": copy.deepcopy(board.get("selection_policy") or {})}
    if identity["score_version"] == "return-opportunity-score-v3":
        from return_opportunity import ENTRY_POLICY
        if board.get("entry_policy") != ENTRY_POLICY or any((board.get("entry_policy") or {}).get(key) is not False for key in ("execution_ready", "automatic_execution")):
            raise OpportunityOutcomeContractError("entry review policy is invalid")
        identity["entry_policy"] = copy.deepcopy(board["entry_policy"])
    return identity


def _registration_evidence(snapshot, source_snapshot=None):
    """Freeze the whole opportunity board, including policies for empty boards."""
    board = snapshot["return_opportunities"]
    generated = _time(snapshot.get("generated_at"))
    return {"schema_version": "opportunity-registration-evidence-v1",
            "snapshot_key": _key(source_snapshot or snapshot.get("snapshot_key")),
            "generated_at": generated,
            "feature_cutoff_at": _time(snapshot.get("feature_cutoff_at") or generated),
            "opportunity_board_sha256": _digest(board),
            "score_identity": _score_identity(board)}


def build_opportunity_predictions(snapshot, source_snapshot=None, *, published_at=None):
    """Freeze published candidates verbatim; require verified publication time."""
    key = _key(source_snapshot or snapshot.get("snapshot_key"))
    board = snapshot.get("return_opportunities")
    if not isinstance(board, dict) or board.get("contract_version") not in {"return-opportunities-v1", "return-opportunities-v2"} or board.get("score_kind") != "RETURN_OPPORTUNITY_RULE_SCORE" or board.get("horizon_trade_days") != 10 or board.get("calibrated") is not False or board.get("production_eligible") is not False:
        raise OpportunityOutcomeContractError("published opportunity contract is invalid")
    entry_version = board.get("score_version") == "return-opportunity-score-v3"
    if entry_version:
        from return_opportunity import validate_return_opportunities
        if validate_return_opportunities(board):
            raise OpportunityOutcomeContractError("published entry priority contract is invalid")
    rows = board.get("candidates")
    if not isinstance(rows, list) or len(rows) > 12:
        raise OpportunityOutcomeContractError("published candidates must contain at most twelve rows")
    eligible = board.get("eligible_count")
    if type(eligible) is not int or eligible < 0 or len(rows) != min(12, eligible) or (rows and (board.get("primary") != rows[0] or rows[0].get("rank") != 1 or board.get("status") != "RESEARCH_READY")) or (not rows and (board.get("primary") is not None or board.get("status") != "NO_OPPORTUNITY")):
        raise OpportunityOutcomeContractError("published shortlist count or primary identity invalid")
    publication = _time(published_at or snapshot.get("published_at"))
    generated = _time(snapshot.get("generated_at"))
    feature_cutoff = _time(snapshot.get("feature_cutoff_at") or generated)
    cutoff = max(_aware(publication), _aware(feature_cutoff), _aware(generated)).isoformat()
    identity = _score_identity(board)
    score_id = "oppscore_" + _digest(identity)[:24]
    source_digest = _source_digest(snapshot)
    predictions = []
    seen = set()
    previous_rank, previous_score = 0, 101
    for row in rows:
        market, code = row.get("market"), row.get("code")
        rank, score = row.get("rank"), _number(row.get("opportunity_score"))
        if market not in REGISTERED_BENCHMARKS or not isinstance(code, str) or not code or (market, code) in seen or type(rank) is not int or rank <= previous_rank or not (0 if entry_version else 60) <= score <= previous_score:
            raise OpportunityOutcomeContractError("published candidate identity, rank or score is invalid")
        if row.get("qualification_status") != "RESEARCH_ELIGIBLE" or row.get("qualification_blockers") != [] or row.get("score_kind") != board["score_kind"] or row.get("calibrated") is not False or row.get("production_eligible") is not False:
            raise OpportunityOutcomeContractError("published candidate research boundary is invalid")
        seen.add((market, code))
        previous_rank, previous_score = rank, score
        window = market_calendar.market_trade_window(market, cutoff, horizon_sessions=10)
        prediction = {"schema_version": PREDICTION_SCHEMA_VERSION, "track": TRACK,
            "snapshot_key": key, "source_snapshot_sha256": source_digest,
            "candidate_evidence_sha256": _digest(row), "score_identity": identity,
            "score_version_id": score_id, "score_version": identity["score_version"],
            "generated_at": generated, "feature_cutoff_at": feature_cutoff,
            "published_at": publication, "publication_time_basis": "FIRST_VERIFIED_PUBLICATION",
            "information_cutoff_at": cutoff, "market": market, "code": code,
            "name": str(row.get("name") or code), "rank": rank,
            "market_rank": row.get("market_rank"), "opportunity_score": score,
            **window, "currency": prices.CURRENCIES[market],
            "transaction_cost": TRANSACTION_COSTS[market], "transaction_cost_version": COST_VERSION,
            "benchmark_code": REGISTERED_BENCHMARKS[market],
            "benchmark_transaction_cost": TRANSACTION_COSTS[market], "benchmark_transaction_cost_version": COST_VERSION,
            "calibrated": False, "authorizes_production": False}
        if entry_version:
            prediction.update(evidence_score=row["evidence_score"],
                entry_assessment=copy.deepcopy(row["entry_assessment"]),
                entry_metrics={field: row["metrics"][field] for field in ("return_5d_pct", "return_10d_pct", "distance_ma20_pct")})
        prediction["prediction_id"] = prediction_id(prediction)
        prediction["prediction_sha256"] = prediction_sha256(prediction)
        predictions.append(prediction)
    return validate_prediction_sequence(predictions)


def validate_prediction_sequence(rows):
    if not isinstance(rows, list) or len(rows) > 12:
        raise OpportunityOutcomeContractError("predictions must be a list")
    seen, previous_rank, previous_score = set(), 0, 101
    for row in rows:
        if not isinstance(row, dict) or row.get("schema_version") != PREDICTION_SCHEMA_VERSION or row.get("track") != TRACK or row.get("prediction_id") != prediction_id(row) or row.get("prediction_sha256") != prediction_sha256(row):
            raise OpportunityOutcomeConflictError("prediction hash or isolation identity invalid")
        market, code, rank = row.get("market"), row.get("code"), row.get("rank")
        score = _number(row.get("opportunity_score"))
        entry_version = row.get("score_version") == "return-opportunity-score-v3"
        if market not in REGISTERED_BENCHMARKS or not isinstance(code, str) or not code or (market, code) in seen or type(rank) is not int or rank <= previous_rank or not (0 if entry_version else 60) <= score <= previous_score:
            raise OpportunityOutcomeConflictError("frozen candidate order or identity invalid")
        seen.add((market, code))
        previous_rank, previous_score = rank, score
        _key(row.get("snapshot_key"))
        if any(not re.fullmatch(r"[a-f0-9]{64}", str(row.get(field) or "")) for field in ("source_snapshot_sha256", "candidate_evidence_sha256")):
            raise OpportunityOutcomeConflictError("source evidence digest invalid")
        identity = row.get("score_identity") or {}
        if identity.get("contract_version") not in {"return-opportunities-v1", "return-opportunities-v2"} or identity.get("score_kind") != "RETURN_OPPORTUNITY_RULE_SCORE" or row.get("score_version_id") != "oppscore_" + _digest(identity)[:24] or row.get("score_version") != identity.get("score_version"):
            raise OpportunityOutcomeConflictError("score version identity invalid")
        _score_identity(identity)
        if entry_version:
            from return_opportunity import entry_assessment
            try:
                expected_entry = entry_assessment(row.get("entry_metrics") or {})
                evidence = _number(row.get("evidence_score"))
                if row.get("entry_assessment") != expected_entry or row["entry_assessment"].get("execution_ready") is not False or not 60 <= evidence <= 100 or score != round(max(0, evidence - expected_entry["penalty_points"]), 2):
                    raise ValueError("frozen entry assessment changed")
            except (TypeError, ValueError, AttributeError) as exc:
                raise OpportunityOutcomeConflictError("frozen entry assessment changed") from exc
        cutoff = max(_aware(row.get(k)) for k in ("feature_cutoff_at", "generated_at", "published_at")).isoformat()
        if row.get("information_cutoff_at") != cutoff:
            raise OpportunityOutcomeConflictError("information cutoff changed")
        expected = market_calendar.market_trade_window(market, cutoff, horizon_sessions=10)
        if any(row.get(k) != v for k, v in expected.items()):
            raise OpportunityOutcomeConflictError("forward calendar window changed")
        fixed = {"transaction_cost": TRANSACTION_COSTS[market], "benchmark_transaction_cost": TRANSACTION_COSTS[market], "benchmark_code": REGISTERED_BENCHMARKS[market], "transaction_cost_version": COST_VERSION, "benchmark_transaction_cost_version": COST_VERSION, "currency": prices.CURRENCIES[market], "publication_time_basis": "FIRST_VERIFIED_PUBLICATION", "calibrated": False, "authorizes_production": False}
        if any(row.get(k) != v or (v is False and row.get(k) is not False) for k, v in fixed.items()):
            raise OpportunityOutcomeConflictError("frozen cost or research boundary changed")
    return copy.deepcopy(rows)


def _pending(prediction, status, reason):
    row = {**copy.deepcopy(prediction), "schema_version": OUTCOME_SCHEMA_VERSION, "status": status, "reason_code": reason}
    row["outcome_sha256"] = outcome_sha256(row)
    return row


def _window_rows(loaded, prediction, moment):
    payload = prices._price_rows(loaded, market=prediction["market"], as_of=moment)
    if payload is None:
        raise OpportunityOutcomeContractError("adjusted price source missing")
    by_date, source = payload
    rows = []
    for date in market_calendar.session_dates(prediction["market"], prediction["entry_trade_date"], prediction["forecast_end_trade_date"]):
        day = date.isoformat()
        raw = by_date.get(day) or {}
        bar = {"date": day, **{k: round(_number(raw.get(k), positive=True), 8) for k in ("open", "high", "low", "close")}}
        if not 0 < bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
            raise OpportunityOutcomeContractError("adjusted OHLC inconsistent")
        rows.append(bar)
    if len(rows) != 10:
        raise OpportunityOutcomeContractError("complete ten session window missing")
    return rows, source


def _arithmetic(stock, benchmark, prediction):
    entry, exit_ = stock[0]["open"], stock[-1]["close"]
    bentry, bexit = benchmark[0]["open"], benchmark[-1]["close"]
    gross, bgross = round(exit_ / entry - 1, 8), round(bexit / bentry - 1, 8)
    net, bnet = round(gross - prediction["transaction_cost"], 8), round(bgross - prediction["benchmark_transaction_cost"], 8)
    peak, drawdown = entry, 0.0
    for bar in stock:
        # Low versus prior closes or today's open uses a known chronological peak.
        peak = max(peak, bar["open"])
        drawdown = min(drawdown, bar["low"] / peak - 1)
        peak = max(peak, bar["close"])
    return {"entry_open": entry, "exit_close": exit_, "gross_total_return": gross,
        "net_total_return": net, "benchmark_entry_open": bentry, "benchmark_exit_close": bexit,
        "benchmark_gross_return": bgross, "benchmark_net_return": bnet,
        "net_excess_return": round(net - bnet, 8),
        "maximum_adverse_excursion": round(min(0.0, min(bar["low"] for bar in stock) / entry - 1), 8),
        "maximum_drawdown": round(drawdown, 8)}


def _settled(prediction, moment, price_loader):
    try:
        stock, source = _window_rows(price_loader(prediction["market"], prediction["code"]), prediction, moment)
        benchmark, bsource = _window_rows(price_loader(prediction["market"], prediction["benchmark_code"]), prediction, moment)
    except Exception:
        return _pending(prediction, "PENDING_DATA", "COMPLETE_ADJUSTED_WINDOW_MISSING")
    evidence = {"schema_version": "opportunity-price-evidence-v1", "corporate_action_adjusted": True,
        "stock_source": source, "benchmark_source": bsource, "stock_rows": stock, "benchmark_rows": benchmark}
    evidence["evidence_sha256"] = _digest(evidence)
    row = _pending(prediction, "SETTLED", None)
    row.update({**_arithmetic(stock, benchmark, prediction), "settled_at": moment.isoformat(),
        "price_source": source, "benchmark_price_source": bsource, "corporate_action_adjusted": True,
        "price_evidence": evidence, "price_evidence_sha256": evidence["evidence_sha256"]})
    row["outcome_sha256"] = outcome_sha256(row)
    return row


def validate_opportunity_outcome_batch(payload):
    if not isinstance(payload, dict):
        raise OpportunityOutcomeContractError("batch must be an object")
    batch = copy.deepcopy(payload)
    if batch.get("schema_version") != BATCH_SCHEMA_VERSION or batch.get("track") != TRACK or batch.get("authorizes_production") is not False or batch.get("calibrated") is not False or batch.get("batch_sha256") != batch_sha256(batch):
        raise OpportunityOutcomeConflictError("batch hash or research identity invalid")
    key = _key(batch.get("snapshot_key"))
    if not re.fullmatch(r"[a-f0-9]{64}", str(batch.get("source_snapshot_sha256") or "")):
        raise OpportunityOutcomeConflictError("batch source digest invalid")
    moment = _aware(batch.get("evaluated_at"))
    predictions = validate_prediction_sequence(batch.get("predictions"))
    registration = batch.get("registration_evidence")
    if registration is not None:
        if (not isinstance(registration, dict)
            or registration.get("schema_version") != "opportunity-registration-evidence-v1"
            or registration.get("snapshot_key") != key
            or not re.fullmatch(r"[a-f0-9]{64}", str(registration.get("opportunity_board_sha256") or ""))):
            raise OpportunityOutcomeConflictError("registration evidence identity invalid")
        identity = registration.get("score_identity")
        if (not isinstance(identity, dict)
            or identity.get("contract_version") not in {"return-opportunities-v1", "return-opportunities-v2"}
            or identity.get("score_kind") != "RETURN_OPPORTUNITY_RULE_SCORE"
            or _score_identity(identity) != identity):
            raise OpportunityOutcomeConflictError("registration score policy invalid")
        if max(_aware(registration.get(field)) for field in ("generated_at", "feature_cutoff_at")) > _aware(batch.get("published_at")):
            raise OpportunityOutcomeConflictError("registration evidence postdates publication")
        if any(any(prediction.get(field) != registration.get(field)
                   for field in ("generated_at", "feature_cutoff_at", "score_identity"))
               for prediction in predictions):
            raise OpportunityOutcomeConflictError("registration evidence differs from frozen predictions")
    if len({p["score_version_id"] for p in predictions}) > 1:
        raise OpportunityOutcomeConflictError("one published shortlist cannot mix score versions")
    outcomes = batch.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != len(predictions) or batch.get("prediction_count") != len(predictions) or batch.get("prediction_ids") != [p["prediction_id"] for p in predictions]:
        raise OpportunityOutcomeConflictError("prediction coverage changed")
    counts = Counter()
    for prediction, row in zip(predictions, outcomes):
        if prediction["snapshot_key"] != key or prediction["source_snapshot_sha256"] != batch.get("source_snapshot_sha256") or prediction["published_at"] != batch.get("published_at"):
            raise OpportunityOutcomeConflictError("batch source identity changed")
        if not isinstance(row, dict) or row.get("schema_version") != OUTCOME_SCHEMA_VERSION or row.get("outcome_sha256") != outcome_sha256(row) or any(row.get(k) != v for k, v in prediction.items() if k != "schema_version"):
            raise OpportunityOutcomeConflictError("outcome frozen identity or hash changed")
        status = row.get("status")
        maturity = _aware(prediction["forecast_end_session_close_at"])
        if status not in {"PENDING_MATURITY", "PENDING_DATA", "SETTLED"}:
            raise OpportunityOutcomeConflictError("outcome status invalid")
        if status == "PENDING_MATURITY":
            if moment > maturity or row != _pending(prediction, status, "FORECAST_WINDOW_OPEN"):
                raise OpportunityOutcomeConflictError("pending maturity contains returns or has matured")
        elif moment <= maturity:
            raise OpportunityOutcomeConflictError("outcome matures before exchange close")
        elif status == "PENDING_DATA":
            if row != _pending(prediction, status, "COMPLETE_ADJUSTED_WINDOW_MISSING"):
                raise OpportunityOutcomeConflictError("pending data contains returns")
        else:
            evidence = row.get("price_evidence")
            if not isinstance(evidence, dict) or evidence.get("schema_version") != "opportunity-price-evidence-v1" or evidence.get("corporate_action_adjusted") is not True or evidence.get("evidence_sha256") != _hash_without(evidence, "evidence_sha256") or row.get("price_evidence_sha256") != evidence["evidence_sha256"] or row.get("corporate_action_adjusted") is not True or row.get("reason_code") is not None:
                raise OpportunityOutcomeConflictError("adjusted price evidence invalid")
            stock, source = _window_rows((evidence.get("stock_rows"), evidence.get("stock_source"), True), prediction, moment)
            benchmark, bsource = _window_rows((evidence.get("benchmark_rows"), evidence.get("benchmark_source"), True), prediction, moment)
            if evidence.get("stock_rows") != stock or evidence.get("benchmark_rows") != benchmark or row.get("price_source") != source or row.get("benchmark_price_source") != bsource or any(row.get(k) != v for k, v in _arithmetic(stock, benchmark, prediction).items()):
                raise OpportunityOutcomeConflictError("settlement arithmetic or same-date evidence changed")
            if not maturity < _aware(row.get("settled_at")) <= moment:
                raise OpportunityOutcomeConflictError("settled_at outside legal window")
        counts[status] += 1
    expected_status = "EMPTY" if not outcomes else next(iter(counts)) if len(counts) == 1 else "PARTIAL"
    if batch.get("status_counts") != dict(sorted(counts.items())) or batch.get("status") != expected_status:
        raise OpportunityOutcomeConflictError("batch status counts changed")
    if moment < _aware(batch.get("published_at")):
        raise OpportunityOutcomeConflictError("batch evaluation precedes publication")
    return batch


def _batch(predictions, *, key, source_digest, publication, moment, outcomes, registration_evidence=None):
    counts = Counter(row["status"] for row in outcomes)
    batch = {"schema_version": BATCH_SCHEMA_VERSION, "track": TRACK, "snapshot_key": key,
        "source_snapshot_sha256": source_digest, "published_at": publication,
        "evaluated_at": moment.isoformat(), "prediction_count": len(predictions),
        "prediction_ids": [p["prediction_id"] for p in predictions], "predictions": predictions,
        "outcomes": outcomes, "status_counts": dict(sorted(counts.items())),
        "status": "EMPTY" if not outcomes else next(iter(counts)) if len(counts) == 1 else "PARTIAL",
        "calibrated": False, "authorizes_production": False}
    if registration_evidence is not None:
        batch["registration_evidence"] = copy.deepcopy(registration_evidence)
    batch["batch_sha256"] = batch_sha256(batch)
    return validate_opportunity_outcome_batch(batch)


def register_opportunity_snapshot(snapshot, *, published_at, existing=None, source_snapshot=None):
    """Register once, after verifying publication; repeat publication keeps anchor."""
    if existing is not None:
        old = validate_opportunity_outcome_batch(existing)
        if old["snapshot_key"] != _key(source_snapshot or snapshot.get("snapshot_key")):
            raise OpportunityOutcomeConflictError("published snapshot key changed")
        if _aware(published_at) < _aware(old["published_at"]):
            raise OpportunityOutcomeConflictError("repeat publication precedes first verified publication")
        reconstructed = build_opportunity_predictions(snapshot, source_snapshot, published_at=old["published_at"])
        registration = old.get("registration_evidence")
        if registration is not None:
            if registration != _registration_evidence(snapshot, source_snapshot):
                raise OpportunityOutcomeConflictError("frozen opportunity board or score policy changed")
        elif old["source_snapshot_sha256"] != _source_digest(snapshot):
            # Older batches did not freeze the whole board/empty-board policy.
            # Keep them readable, but do not infer missing evidence on replay.
            raise OpportunityOutcomeConflictError("legacy batch cannot verify changed publication envelope")
        envelope_fields = {"source_snapshot_sha256", "prediction_id", "prediction_sha256"}
        original_evidence = [{key: value for key, value in row.items() if key not in envelope_fields} for row in old["predictions"]]
        repeated_evidence = [{key: value for key, value in row.items() if key not in envelope_fields} for row in reconstructed]
        if original_evidence != repeated_evidence:
            raise OpportunityOutcomeConflictError("frozen opportunity prediction evidence or window changed")
        return old
    predictions = build_opportunity_predictions(snapshot, source_snapshot, published_at=published_at)
    moment = _aware(published_at)
    if any(moment < _aware(p["information_cutoff_at"]) for p in predictions):
        raise OpportunityOutcomeContractError("publication verification precedes feature availability")
    return _batch(predictions, key=_key(source_snapshot or snapshot.get("snapshot_key")), source_digest=_source_digest(snapshot), publication=moment.isoformat(), moment=moment,
        outcomes=[_pending(p, "PENDING_MATURITY", "FORECAST_WINDOW_OPEN") for p in predictions],
        registration_evidence=_registration_evidence(snapshot, source_snapshot))


def settle_opportunity_batch(batch, as_of, price_loader):
    old = validate_opportunity_outcome_batch(batch)
    moment = _aware(as_of)
    if moment < _aware(old["evaluated_at"]):
        raise OpportunityOutcomeConflictError("settlement clock moved backwards")
    outcomes = [copy.deepcopy(row) if row["status"] == "SETTLED" else
        _pending(p, "PENDING_MATURITY", "FORECAST_WINDOW_OPEN") if moment <= _aware(p["forecast_end_session_close_at"]) else
        _settled(p, moment, price_loader) for p, row in zip(old["predictions"], old["outcomes"])]
    if outcomes == old["outcomes"]:
        return old
    return _batch(old["predictions"], key=old["snapshot_key"], source_digest=old["source_snapshot_sha256"], publication=old["published_at"], moment=moment, outcomes=outcomes,
                  registration_evidence=old.get("registration_evidence"))


def merge_opportunity_batches(existing, incoming):
    """Merge monotonic outcomes from concurrent archives, refusing any rewrite."""
    old, new = validate_opportunity_outcome_batch(existing), validate_opportunity_outcome_batch(incoming)
    for field in ("snapshot_key", "source_snapshot_sha256", "published_at", "predictions", "prediction_ids"):
        if old[field] != new[field]:
            raise OpportunityOutcomeConflictError("refusing changed frozen opportunity predictions")
    if old.get("registration_evidence") != new.get("registration_evidence"):
        raise OpportunityOutcomeConflictError("refusing changed registration evidence")
    outcomes = []
    order = {"PENDING_MATURITY": 0, "PENDING_DATA": 1, "SETTLED": 2}
    for left, right in zip(old["outcomes"], new["outcomes"]):
        if left["status"] == right["status"] == "SETTLED" and left != right:
            raise OpportunityOutcomeConflictError("refusing changed settled opportunity outcome")
        outcomes.append(copy.deepcopy(left if order[left["status"]] >= order[right["status"]] else right))
    if outcomes == old["outcomes"]:
        return old
    if outcomes == new["outcomes"]:
        return new
    moment = max(_aware(old["evaluated_at"]), _aware(new["evaluated_at"]))
    return _batch(old["predictions"], key=old["snapshot_key"], source_digest=old["source_snapshot_sha256"], publication=old["published_at"], moment=moment, outcomes=outcomes,
                  registration_evidence=old.get("registration_evidence"))


def write_opportunity_outcome_batch(directory, batch):
    validated = validate_opportunity_outcome_batch(batch)
    root = pathlib.Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    target = root / validated["snapshot_key"]
    if target.exists():
        old = validate_opportunity_outcome_batch(json.loads(target.read_text(encoding="utf-8")))
        merged = merge_opportunity_batches(old, validated)
        if merged != validated:
            raise OpportunityOutcomeConflictError("refusing outcome downgrade")
        if old == validated:
            return target
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=root, prefix=".opportunity-", suffix=".tmp", delete=False) as handle:
        json.dump(validated, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        temporary = pathlib.Path(handle.name)
    temporary.replace(target)
    return target


def load_opportunity_outcome_batches(directory=DEFAULT_OUTCOME_DIRECTORY):
    result = {}
    for path in sorted(pathlib.Path(directory).glob("*.json")):
        try:
            batch = validate_opportunity_outcome_batch(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise OpportunityOutcomeConflictError(f"invalid opportunity outcome: {path.name}") from exc
        if batch["snapshot_key"] != path.name:
            raise OpportunityOutcomeConflictError("opportunity batch filename mismatch")
        result[path.name] = batch
    return result


def _metrics(rows):
    settled = [r for r in rows if r["status"] == "SETTLED"]
    # Freeze earliest published membership across ALL observations first. Never
    # substitute a later successful quote for an earlier pending observation.
    unique = {}
    for row in sorted(rows, key=lambda r: (r["published_at"], r["prediction_id"])):
        unique.setdefault((row["score_version_id"], row["market"], row["code"], row["entry_trade_date"]), row)
    all_groups = defaultdict(list)
    for row in unique.values():
        all_groups[(row["score_version_id"], row["market"], row["entry_trade_date"])].append(row)
    groups = {key: group for key, group in all_groups.items() if all(r["status"] == "SETTLED" for r in group)}
    observations = [row for group in groups.values() for row in group]
    def average(field):
        # Each market-entry cohort has equal weight; this is not a portfolio PnL.
        values = [sum(r[field] for r in group) / len(group) for group in groups.values()]
        return round(sum(values) / len(values), 8) if values else None
    non_overlapping = 0
    last_end = {}
    for (version, market, entry), group in sorted(groups.items()):
        if entry > last_end.get((version, market), ""):
            non_overlapping += 1
            last_end[(version, market)] = max(r["forecast_end_trade_date"] for r in group)
    return {"prediction_count": len(rows), "settled_count": len(settled),
        "pending_maturity_count": sum(r["status"] == "PENDING_MATURITY" for r in rows),
        "pending_data_count": sum(r["status"] == "PENDING_DATA" for r in rows),
        "independent_entry_session_count": len({(r["market"], r["entry_trade_date"]) for r in rows}),
        "independent_entry_date_count": len({r["entry_trade_date"] for r in rows}),
        "settled_entry_session_count": len(groups), "settled_entry_date_count": len({r["entry_trade_date"] for r in observations}),
        "incomplete_entry_session_count": len(all_groups) - len(groups),
        "mature_pending_data_entry_session_count": sum(any(r["status"] == "PENDING_DATA" for r in group) for group in all_groups.values()),
        "metric_observation_count": len(observations),
        "unique_security_entry_count": len(unique),
        "duplicate_settled_observation_count": len(settled) - len({(r["score_version_id"], r["market"], r["code"], r["entry_trade_date"]) for r in settled}),
        "non_overlapping_entry_session_count": non_overlapping,
        "mean_net_return": average("net_total_return"), "mean_excess_return": average("net_excess_return"),
        "mean_net_excess_return": average("net_excess_return"),
        "win_rate": round(sum(r["net_total_return"] > 0 for r in observations) / len(observations), 8) if observations else None,
        "maximum_adverse_excursion": min((r["maximum_adverse_excursion"] for r in observations), default=None),
        "maximum_drawdown": min((r["maximum_drawdown"] for r in observations), default=None)}


def _ranking_evaluation(batches):
    """Compare frozen global Top N; never pick later successful publications.

    Use one first verified board per scoring identity and Beijing publication
    date, selected BEFORE looking at outcome status. All board members must be
    settled, including non-Top-N members, so absent losers cannot inflate Top N.
    Later publications are still retained in the underlying ledger.
    """
    first = {}
    source_count = 0
    for batch in sorted(batches, key=lambda item: (item["published_at"], item["snapshot_key"])):
        rows = batch["outcomes"]
        if not rows:
            continue
        source_count += 1
        publication_day = _aware(batch["published_at"]).astimezone(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
        first.setdefault((rows[0]["score_version_id"], publication_day), rows)
    cohorts = list(first.values())
    groups = {}
    for name, size in (("top1", 1), ("top3", 3), ("board", None)):
        complete, insufficient, pending_count, pending_data = [], 0, 0, 0
        entry_windows = set()
        duplicate_windows = 0
        for rows in cohorts:
            selected = [row for row in rows if size is None or row["rank"] <= size]
            if size is not None and (len(selected) != size or {row["rank"] for row in selected} != set(range(1, size + 1))):
                insufficient += 1
                continue
            # Weekend refreshes or later publication dates can still refer to
            # the same tradable open. Freeze the first Top-N selection for that
            # market-entry window BEFORE checking whether prices are present.
            entry_window = tuple(sorted({(row["market"], row["entry_trade_date"]) for row in selected}))
            if entry_window in entry_windows:
                duplicate_windows += 1
                continue
            entry_windows.add(entry_window)
            if any(row["status"] != "SETTLED" for row in rows):
                pending_count += 1
                pending_data += any(row["status"] == "PENDING_DATA" for row in rows)
                continue
            complete.append({
                "net": sum(row["net_total_return"] for row in selected) / len(selected),
                "excess": sum(row["net_excess_return"] for row in selected) / len(selected),
                "selected": selected,
                "entry": min(_aware(row["entry_session_open_at"]) for row in rows),
                "exit": max(_aware(row["forecast_end_session_close_at"]) for row in rows),
            })
        net_returns = sorted(cohort["net"] for cohort in complete)
        tail_count = math.ceil(len(net_returns) * .1)
        non_overlapping, last_exit = 0, None
        for cohort in sorted(complete, key=lambda item: (item["entry"], item["exit"])):
            if last_exit is None or cohort["entry"] > last_exit:
                non_overlapping += 1
                last_exit = cohort["exit"]
        count = len(complete)
        groups[name] = {
            "status": "PARTIAL_DATA" if pending_data else "OBSERVING" if count >= 20 and non_overlapping >= 5 else "EARLY_SAMPLE" if count else "COLLECTING",
            "cohort_count": len(cohorts) - duplicate_windows, "complete_cohort_count": count,
            "pending_cohort_count": pending_count, "pending_data_cohort_count": pending_data,
            "insufficient_member_cohort_count": insufficient,
            "duplicate_publication_count": source_count - len(cohorts) + duplicate_windows,
            "non_overlapping_cohort_count": non_overlapping,
            "settled_security_count": sum(len(cohort["selected"]) for cohort in complete),
            "mean_net_return": round(sum(cohort["net"] for cohort in complete) / count, 8) if count else None,
            "mean_net_excess_return": round(sum(cohort["excess"] for cohort in complete) / count, 8) if count else None,
            "positive_return_rate": round(sum(value > 0 for value in net_returns) / count, 8) if count else None,
            "worst_cohort_net_return": round(net_returns[0], 8) if count else None,
            "expected_shortfall_10pct": round(sum(net_returns[:tail_count]) / tail_count, 8) if tail_count >= 5 else None,
            "tail_sample_count": tail_count, "minimum_tail_sample_count": 5,
            "maximum_adverse_excursion": min((row["maximum_adverse_excursion"] for cohort in complete for row in cohort["selected"]), default=None),
        }
    return {"contract_version": "opportunity-ranking-performance-v1",
            "status": "OBSERVING" if groups["board"]["complete_cohort_count"] else "COLLECTING",
            "primary_metric": "mean_net_return", "secondary_metric": "mean_net_excess_return",
            "cohort_policy": "first_verified_board_per_score_version_beijing_publication_date",
            "entry_window_policy": "first_selection_per_group_market_entry_window_before_outcomes",
            "rank_basis": "FROZEN_GLOBAL_RANK", "completion_policy": "ENTIRE_BOARD_SETTLED",
            "weighting": "equal_board_date_equal_selected_security", "calibrated": False,
            "authorizes_production": False, "groups": groups}


def evaluate_opportunity_performance(batches):
    validated = [validate_opportunity_outcome_batch(b) for b in batches.values()]
    rows = [row for batch in validated for row in batch["outcomes"]]
    by_version = defaultdict(list)
    for row in rows:
        by_version[row["score_version_id"]].append(row)
    batches_by_version = defaultdict(list)
    for batch in validated:
        if batch["predictions"]:
            batches_by_version[batch["predictions"][0]["score_version_id"]].append(batch)
    metrics = _metrics(rows)
    # Mixing different ranking policies is not an estimate of either model.
    if len(by_version) > 1:
        for key in ("mean_net_return", "mean_excess_return", "mean_net_excess_return", "win_rate"):
            metrics[key] = None
    ranking_evaluation = _ranking_evaluation(validated if len(by_version) <= 1 else [])
    if len(by_version) > 1:
        ranking_evaluation["status"] = "BY_VERSION_ONLY"
    recent_fields = ("prediction_id", "snapshot_key", "score_version_id", "score_version", "published_at", "information_cutoff_at", "name", "market", "code", "rank", "opportunity_score", "entry_trade_date", "forecast_end_trade_date", "status", "reason_code", "net_total_return", "net_excess_return", "maximum_adverse_excursion", "maximum_drawdown")
    return {"schema_version": "opportunity-performance-v1", "track": TRACK,
        "status": "OBSERVING" if metrics["settled_count"] else "COLLECTING", **metrics,
        "snapshot_count": len(validated), "calibrated": False, "authorizes_production": False,
        "first_maturity_date": min((r["forecast_end_trade_date"] for r in rows), default=None),
        "metric_weighting": "equal_complete_market_entry_session_after_first_publication_security_entry_deduplication",
        "sampling_warning": "同日重复榜单不是独立交易；不同入场日的10日窗口仍可能重叠，日期数不代表统计独立样本。收益为研究观察，未经校准。",
        "ranking_evaluation": ranking_evaluation,
        "by_version": [{"score_version_id": version, "score_version": group[0]["score_version"], "score_identity": group[0]["score_identity"], **_metrics(group),
                        "ranking_evaluation": _ranking_evaluation(batches_by_version[version])} for version, group in sorted(by_version.items())],
        "recent_outcomes": [{k: row.get(k) for k in recent_fields} for row in sorted(rows, key=lambda r: (r["published_at"], -r["rank"]), reverse=True)[:60]]}
