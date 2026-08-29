from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scripts import build_historical_replay


class BuildHistoricalReplayScriptTests(unittest.TestCase):
    def test_prefetch_is_bounded_deduplicated_and_skips_pending_or_settled_rows(self) -> None:
        cohorts = [
            {
                "shortlist": [
                    {
                        "candidate_id": "mature-a",
                        "market": "us",
                        "code": "AAPL",
                        "benchmark_code": "SPY",
                        "forecast_end_session_close_at": "2026-08-28T20:00:00Z",
                    },
                    {
                        "candidate_id": "mature-b",
                        "market": "us",
                        "code": "AAPL",
                        "benchmark_code": "SPY",
                        "forecast_end_session_close_at": "2026-08-28T20:00:00Z",
                    },
                    {
                        "candidate_id": "pending",
                        "market": "us",
                        "code": "MSFT",
                        "benchmark_code": "SPY",
                        "forecast_end_session_close_at": "2026-09-01T20:00:00Z",
                    },
                    {
                        "candidate_id": "settled",
                        "market": "us",
                        "code": "NVDA",
                        "benchmark_code": "SPY",
                        "forecast_end_session_close_at": "2026-08-28T20:00:00Z",
                    },
                ]
            }
        ]
        existing = {"outcomes": [{"candidate_id": "settled", "status": "SETTLED"}]}
        network = mock.Mock(return_value=([{"date": "2026-08-28"}], "fixture", True))

        loader, symbol_count, worker_limit = build_historical_replay._prefetched_price_loader(
            network,
            cohorts,
            existing,
            "2026-08-29T05:37:00Z",
            max_workers=8,
        )

        self.assertEqual(symbol_count, 2)
        self.assertEqual(worker_limit, 2)
        self.assertEqual(
            {call.args for call in network.call_args_list},
            {("us", "AAPL"), ("us", "SPY")},
        )
        calls_before_lookup = network.call_count
        self.assertEqual(loader("us", "AAPL")[1], "fixture")
        self.assertEqual(network.call_count, calls_before_lookup)

    def test_price_cache_accelerates_same_day_but_never_crosses_day_boundary(self) -> None:
        first_rows = [{"date": "2026-08-28", "open": 10.0}]
        second_rows = [{"date": "2026-08-29", "open": 11.0}]
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = pathlib.Path(directory)
            first_network = mock.Mock(return_value=(first_rows, "provider-a", True))
            first_loader = build_historical_replay._cached_price_loader(
                first_network,
                cache_dir=cache_dir,
                cache_day="2026-08-29",
            )
            self.assertEqual(first_loader("us", "AAPL"), (first_rows, "provider-a", True))
            first_network.assert_called_once_with("us", "AAPL")

            same_day_network = mock.Mock(side_effect=AssertionError("cache miss"))
            same_day_loader = build_historical_replay._cached_price_loader(
                same_day_network,
                cache_dir=cache_dir,
                cache_day="2026-08-29",
            )
            self.assertEqual(same_day_loader("us", "AAPL"), (first_rows, "provider-a", True))
            same_day_network.assert_not_called()

            next_day_network = mock.Mock(return_value=(second_rows, "provider-b", True))
            next_day_loader = build_historical_replay._cached_price_loader(
                next_day_network,
                cache_dir=cache_dir,
                cache_day="2026-08-30",
            )
            self.assertEqual(next_day_loader("us", "AAPL"), (second_rows, "provider-b", True))
            next_day_network.assert_called_once_with("us", "AAPL")

    def test_run_discovers_builds_validates_and_writes_canonical_artifact(self) -> None:
        cohorts = [{"cohort_id": "2026-08-01-a-share"}]
        artifact = {
            "contract_version": "archived-shortlist-replay-v1",
            "authorizes_production": False,
            "cohort_count": 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            output = root / "backtests" / "replay.json"
            picks.mkdir()

            with (
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "discover_replay_cohorts",
                    return_value=cohorts,
                ) as discover,
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "build_replay_artifact",
                    return_value=artifact,
                ) as build,
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "validate_replay_artifact",
                    return_value=artifact,
                ) as validate,
            ):
                price_loader = mock.Mock(return_value=([], "fixture", True))
                summary = build_historical_replay.run(
                    picks,
                    output,
                    as_of="2026-08-29T05:37:00Z",
                    max_cohorts=120,
                    price_loader=price_loader,
                )

            discover.assert_called_once_with(
                picks,
                as_of="2026-08-29T05:37:00Z",
                max_cohorts=120,
            )
            build.assert_called_once()
            build_args, build_kwargs = build.call_args
            self.assertEqual(build_args, (cohorts,))
            self.assertEqual(build_kwargs["as_of"], "2026-08-29T05:37:00Z")
            self.assertTrue(callable(build_kwargs["price_loader"]))
            self.assertIs(
                build_kwargs["benchmark_price_loader"],
                build_kwargs["price_loader"],
            )
            self.assertIsNone(build_kwargs["existing"])
            validate.assert_called_once_with(artifact)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), artifact)
            self.assertTrue(output.read_text(encoding="utf-8").endswith("\n"))
            self.assertEqual(
                summary,
                {
                    "changed": True,
                    "cohort_count": 1,
                    "output": str(output),
                    "authorizes_production": False,
                    "prefetched_symbol_count": 0,
                    "worker_limit": 0,
                },
            )

    def test_identical_replay_is_idempotent(self) -> None:
        artifact = {
            "contract_version": "archived-shortlist-replay-v1",
            "authorizes_production": False,
            "cohort_count": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            output = root / "replay.json"
            picks.mkdir()
            output.write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "discover_replay_cohorts",
                    return_value=[],
                ),
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "build_replay_artifact",
                    return_value=artifact,
                ),
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "validate_replay_artifact",
                    return_value=artifact,
                ),
                mock.patch.object(
                    build_historical_replay,
                    "_atomic_write",
                ) as atomic_write,
            ):
                summary = build_historical_replay.run(
                    picks,
                    output,
                    price_loader=mock.Mock(return_value=([], "fixture", True)),
                )

            self.assertFalse(summary["changed"])
            atomic_write.assert_not_called()

    def test_validation_failure_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            output = root / "replay.json"
            picks.mkdir()
            old = {
                "contract_version": "archived-shortlist-replay-v1",
                "authorizes_production": False,
                "cohort_count": 0,
            }
            output.write_text(json.dumps(old) + "\n", encoding="utf-8")
            with (
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "discover_replay_cohorts",
                    return_value=[],
                ),
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "build_replay_artifact",
                    return_value={"contract_version": "broken"},
                ),
                mock.patch.object(
                    build_historical_replay.historical_replay,
                    "validate_replay_artifact",
                    side_effect=[old, ValueError("invalid replay")],
                ),
            ):
                with self.assertRaisesRegex(ValueError, "invalid replay"):
                    build_historical_replay.run(
                        picks,
                        output,
                        price_loader=mock.Mock(return_value=([], "fixture", True)),
                    )

            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), old)

    def test_validate_file_rejects_non_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "replay.json"
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                build_historical_replay.validate_file(path)


if __name__ == "__main__":
    unittest.main()
