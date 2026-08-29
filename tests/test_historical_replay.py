import copy
import datetime as dt
import hashlib
import json
import pathlib
import tempfile
import unittest

import historical_replay
import market_calendar


def _write_snapshot(path, *, generated_at, signal_date, root=None, markets=None):
    payload = {
        "generated_at": generated_at,
        "signal_date": signal_date,
        "decision": root or {},
    }
    if markets is not None:
        payload["markets"] = markets
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _legacy_snapshot(directory, *, filename="2026-01-06_2026-01-05.json"):
    path = directory / filename
    _write_snapshot(
        path,
        generated_at="2026-01-05T08:00:00+08:00",
        signal_date="2026-01-02",
        root={
            "action": "BUY_CANDIDATE",
            "primary": {"code": "000001", "name": "平安银行", "score": 91.2},
            "watchlist": [
                {"code": "600000", "name": "浦发银行", "score": 88.1},
                {"code": "000001", "name": "重复项", "score": 1},
            ],
        },
    )
    return path


def _bars(cohort, *, stock=True, entry=10.0, exit_=12.0):
    sessions = [
        day.isoformat()
        for day in market_calendar.session_dates(
            cohort["market"],
            cohort["entry_trade_date"],
            cohort["forecast_end_trade_date"],
        )
    ]
    if len(sessions) != 10:
        raise AssertionError("test fixture expected exactly ten sessions")
    start = entry if stock else 100.0
    end = exit_ if stock else 105.0
    rows = []
    for index, day in enumerate(sessions):
        close = start + (end - start) * index / 9
        rows.append(
            {
                "date": day,
                "open": start if index == 0 else close,
                "low": min(start, close) * 0.98,
                "close": end if index == 9 else close,
            }
        )
    return rows


def _settlement_moment(cohort):
    maturity = dt.datetime.fromisoformat(cohort["forecast_end_session_close_at"])
    return maturity + dt.timedelta(hours=1)


class HistoricalReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp_path = pathlib.Path(temporary.name)

    def assertResearchOnly(self, record):
        self.assertEqual(record["track"], "ARCHIVED_SHORTLIST_REPLAY")
        self.assertEqual(record["evidence_class"], "RETROSPECTIVE")
        self.assertEqual(record["universe_scope"], "ARCHIVED_SHORTLIST_ONLY")
        for field in historical_replay.AUTHORITY_FIELDS:
            self.assertIs(record[field], False, field)

    def test_discovery_uses_only_archived_primary_and_watchlist(self):
        legacy_path = _legacy_snapshot(self.tmp_path)
        _write_snapshot(
            self.tmp_path / "2026-01-07_2026-01-06.json",
            generated_at="2026-01-06T20:00:00+08:00",
            signal_date="2026-01-06",
            root={
                "action": "NO_TRADE",
                "watchlist": [{"code": "ROOT-DUPLICATE", "name": "不应被读取"}],
            },
            markets={
                "a_share": {
                    "decision": {
                        "action": "NO_TRADE",
                        "primary": None,
                        "watchlist": [
                            {"code": "300001", "name": "特锐德", "score": 72}
                        ],
                    }
                },
                "hk": {
                    "decision": {
                        "action": "BUY_CANDIDATE",
                        "primary": {
                            "code": "0700.HK",
                            "name": "腾讯控股",
                            "score": 90,
                        },
                        "watchlist": [],
                    }
                },
                "us": {
                    "decision": {
                        "action": "NO_TRADE",
                        "primary": None,
                        "watchlist": [],
                    }
                },
            },
        )
        _write_snapshot(
            self.tmp_path / "latest.json",
            generated_at="2026-01-06T21:00:00+08:00",
            signal_date="2026-01-06",
            root={"watchlist": [{"code": "LATEST", "name": "别名"}]},
        )

        cohorts = historical_replay.discover_replay_cohorts(self.tmp_path)

        self.assertEqual(
            [(row["market"], row["shortlist_count"]) for row in cohorts],
            [("a_share", 2), ("a_share", 1), ("hk", 1)],
        )
        first = cohorts[0]
        self.assertEqual(first["source_snapshot"], legacy_path.name)
        self.assertEqual(
            first["source_snapshot_sha256"],
            hashlib.sha256(legacy_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            [row["code"] for row in first["shortlist"]], ["000001", "600000"]
        )
        self.assertEqual(
            [row["shortlist_role"] for row in first["shortlist"]],
            ["PRIMARY", "WATCHLIST"],
        )
        self.assertEqual(first["entry_trade_date"], "2026-01-05")
        self.assertEqual(first["forecast_end_trade_date"], "2026-01-16")
        self.assertNotIn(
            "ROOT-DUPLICATE",
            [item["code"] for row in cohorts for item in row["shortlist"]],
        )
        self.assertResearchOnly(first)
        self.assertResearchOnly(first["shortlist"][0])

        limited = historical_replay.discover_replay_cohorts(
            self.tmp_path,
            as_of="2026-01-07T20:30:00+08:00",
            max_cohorts=1,
        )
        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0]["market"], "hk")

    def test_build_settles_exact_adjusted_window_and_benchmark_excess(self):
        _legacy_snapshot(self.tmp_path)
        cohort = historical_replay.discover_replay_cohorts(self.tmp_path)[0]
        stock_rows = _bars(cohort, stock=True)
        benchmark_rows = _bars(cohort, stock=False)

        def loader(market, code):
            self.assertEqual(market, "a_share")
            rows = benchmark_rows if code == "510300" else stock_rows
            return rows, "adjusted-test-source", True

        artifact = historical_replay.build_replay_artifact(
            [cohort], as_of=_settlement_moment(cohort), price_loader=loader
        )

        self.assertEqual(artifact["status"], "SETTLED")
        self.assertEqual(artifact["status_counts"], {"SETTLED": 2})
        row = artifact["outcomes"][0]
        self.assertEqual(row["entry_open"], 10.0)
        self.assertEqual(row["exit_close"], 12.0)
        self.assertEqual(row["gross_total_return"], 0.2)
        self.assertEqual(row["net_total_return"], 0.1985)
        self.assertEqual(row["benchmark_gross_return"], 0.05)
        self.assertEqual(row["benchmark_net_return"], 0.0485)
        self.assertEqual(row["net_excess_return"], 0.15)
        self.assertIs(row["corporate_action_adjusted"], True)
        self.assertEqual(len(row["price_evidence"]["session_lows"]), 10)
        self.assertResearchOnly(artifact)
        self.assertResearchOnly(row)

        summary = historical_replay.public_model_summary(artifact)
        self.assertEqual(summary, historical_replay.summarize_replay_artifact(artifact))
        self.assertEqual(summary["cohort_count"], 1)
        self.assertEqual(summary["signal_date_count"], 1)
        self.assertEqual(summary["independent_entry_date_count"], 1)
        self.assertEqual(summary["shortlist_count"], 2)
        self.assertEqual(summary["settled_count"], 2)
        self.assertEqual(summary["metrics"]["sample_count"], 2)
        self.assertEqual(summary["metrics"]["mean_net_excess_return"], 0.15)
        self.assertResearchOnly(summary)
        self.assertEqual(historical_replay.validate_replay_artifact(artifact), artifact)

    def test_discovery_keeps_latest_revision_per_market_entry_session(self):
        for filename, generated_at, code in (
            ("early.json", "2026-01-05T07:00:00+08:00", "EARLY"),
            ("late.json", "2026-01-05T08:30:00+08:00", "LATE"),
            ("after-open.json", "2026-01-05T10:00:00+08:00", "AFTER"),
        ):
            _write_snapshot(
                self.tmp_path / filename,
                generated_at=generated_at,
                signal_date="2026-01-02",
                root={
                    "action": "BUY_CANDIDATE",
                    "primary": {"code": code, "name": code},
                    "watchlist": [],
                },
            )

        cohorts = historical_replay.discover_replay_cohorts(self.tmp_path)

        self.assertEqual(len(cohorts), 2)
        self.assertEqual(
            [row["shortlist"][0]["code"] for row in cohorts], ["LATE", "AFTER"]
        )
        self.assertEqual(
            [row["entry_trade_date"] for row in cohorts],
            ["2026-01-05", "2026-01-06"],
        )

    def test_discovery_defers_a_revision_cell_until_its_entry_open(self):
        for filename, generated_at, code in (
            ("early.json", "2026-01-05T07:00:00+08:00", "EARLY"),
            ("late.json", "2026-01-05T08:30:00+08:00", "LATE"),
        ):
            _write_snapshot(
                self.tmp_path / filename,
                generated_at=generated_at,
                signal_date="2026-01-02",
                root={
                    "action": "BUY_CANDIDATE",
                    "primary": {"code": code, "name": code},
                    "watchlist": [],
                },
            )

        before_open = historical_replay.discover_replay_cohorts(
            self.tmp_path,
            as_of="2026-01-05T08:45:00+08:00",
        )
        after_open = historical_replay.discover_replay_cohorts(
            self.tmp_path,
            as_of="2026-01-05T09:31:00+08:00",
        )

        self.assertEqual(before_open, [])
        self.assertEqual(len(after_open), 1)
        self.assertEqual(after_open[0]["shortlist"][0]["code"], "LATE")

    def test_pending_does_not_fetch_and_settled_rows_are_immutable(self):
        _legacy_snapshot(self.tmp_path)
        cohort = historical_replay.discover_replay_cohorts(self.tmp_path)[0]
        calls = []

        def forbidden_loader(market, code):
            calls.append((market, code))
            raise AssertionError("immature rows must not fetch prices")

        before_maturity = dt.datetime.fromisoformat(
            cohort["forecast_end_session_close_at"]
        )
        pending = historical_replay.build_replay_artifact(
            [cohort], as_of=before_maturity, price_loader=forbidden_loader
        )
        self.assertEqual(pending["status"], "PENDING_MATURITY")
        self.assertEqual(calls, [])

        stock_rows = _bars(cohort, stock=True)
        benchmark_rows = _bars(cohort, stock=False)

        def first_loader(market, code):
            rows = benchmark_rows if code == "510300" else stock_rows
            return rows, "adjusted-v1", True

        settled = historical_replay.build_replay_artifact(
            [cohort],
            as_of=_settlement_moment(cohort),
            price_loader=first_loader,
            existing=pending,
        )

        def changed_loader(market, code):
            rows = _bars(cohort, stock=code != "510300", entry=10.0, exit_=50.0)
            return rows, "adjusted-v2", True

        later = historical_replay.build_replay_artifact(
            [cohort],
            as_of=_settlement_moment(cohort) + dt.timedelta(days=1),
            price_loader=changed_loader,
            existing=settled,
        )
        self.assertEqual(later, settled)

        tampered = copy.deepcopy(settled)
        tampered["outcomes"][0]["net_excess_return"] = 99
        with self.assertRaises(historical_replay.HistoricalReplayConflictError):
            historical_replay.validate_replay_artifact(tampered)

    def test_unadjusted_or_ambiguous_price_evidence_stays_pending_data(self):
        _legacy_snapshot(self.tmp_path)
        cohort = historical_replay.discover_replay_cohorts(self.tmp_path)[0]
        rows = _bars(cohort)

        artifact = historical_replay.build_replay_artifact(
            [cohort],
            as_of=_settlement_moment(cohort),
            price_loader=lambda market, code: (rows, "raw-close", False),
        )
        self.assertEqual(artifact["status"], "PENDING_DATA")
        self.assertEqual(
            artifact["outcomes"][0]["reason_code"],
            "ADJUSTED_PRICE_EVIDENCE_MISSING",
        )

        duplicate_rows = rows + [dict(rows[-1])]
        artifact = historical_replay.build_replay_artifact(
            [cohort],
            as_of=_settlement_moment(cohort),
            price_loader=lambda market, code: (
                duplicate_rows,
                "bad-adjusted-source",
                True,
            ),
        )
        self.assertEqual(artifact["outcomes"][0]["status"], "PENDING_DATA")

    def test_validation_rejects_any_point_in_time_or_authority_claim(self):
        _legacy_snapshot(self.tmp_path)
        cohort = historical_replay.discover_replay_cohorts(self.tmp_path)[0]
        artifact = historical_replay.build_replay_artifact(
            [cohort],
            as_of=dt.datetime.fromisoformat(cohort["forecast_end_session_close_at"]),
            price_loader=lambda market, code: ([], "", False),
        )

        for field in historical_replay.AUTHORITY_FIELDS:
            changed = copy.deepcopy(artifact)
            changed[field] = True
            with self.subTest(field=field):
                with self.assertRaises(historical_replay.HistoricalReplayConflictError):
                    historical_replay.validate_replay_artifact(changed)

    def test_write_refuses_to_replace_an_immutable_settled_row(self):
        picks = self.tmp_path / "picks"
        picks.mkdir()
        _legacy_snapshot(picks)
        cohort = historical_replay.discover_replay_cohorts(picks)[0]
        moment = _settlement_moment(cohort)

        first = historical_replay.build_replay_artifact(
            [cohort],
            as_of=moment,
            price_loader=lambda market, code: (
                _bars(cohort, stock=code != "510300"),
                "adjusted-one",
                True,
            ),
        )
        target = self.tmp_path / "artifact.json"
        historical_replay.write_replay_artifact(target, first)

        replacement = historical_replay.build_replay_artifact(
            [cohort],
            as_of=moment + dt.timedelta(hours=1),
            price_loader=lambda market, code: (
                _bars(cohort, stock=code != "510300", exit_=20.0),
                "adjusted-two",
                True,
            ),
        )
        with self.assertRaises(historical_replay.HistoricalReplayConflictError):
            historical_replay.write_replay_artifact(target, replacement)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), first)


if __name__ == "__main__":
    unittest.main()
