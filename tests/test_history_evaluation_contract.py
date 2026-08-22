from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest import mock

import server


def write_snapshot(directory: pathlib.Path, name: str, payload: dict) -> None:
    (directory / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class HistoryEvaluationContractTests(unittest.TestCase):
    def test_history_payload_consolidates_runs_without_relabeling_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            picks = pathlib.Path(temporary)
            legacy = {
                "target_date": "2026-08-20",
                "signal_date": "2026-08-19",
                "generated_at": "2026-08-20T10:00:00+08:00",
                "decision": {
                    "action": "BUY_CANDIDATE",
                    "primary": {
                        "code": "600000",
                        "name": "旧策略标的",
                        "estimated_2d_range": {"text": "-1.0% ~ +3.0%"},
                    },
                },
            }
            write_snapshot(picks, "2026-08-20_2026-08-19_100000.json", legacy)
            legacy_latest = {**legacy, "generated_at": "2026-08-20T15:00:00+08:00"}
            write_snapshot(picks, "2026-08-20_2026-08-19_150000.json", legacy_latest)
            contract = {
                "target_date": "2026-08-21",
                "signal_date": "2026-08-20",
                "generated_at": "2026-08-21T15:30:00+08:00",
                "forecast_end_date": "2026-09-04",
                "global_decision": {
                    "contract_version": "global-10d-v1",
                    "decision_scope": "global_10d",
                    "action_basis": "strict_cross_market_gate_v1",
                    "action": "NO_VALID_PICK",
                    "primary": None,
                    "blocker_codes": ["NO_CANDIDATE_PASSED_STRICT_GATE"],
                },
            }
            write_snapshot(picks, "2026-08-21_2026-08-20_153000.json", contract)
            same_day_later_legacy = {
                **legacy,
                "target_date": "2026-08-21",
                "generated_at": "2026-08-21T22:00:00+08:00",
            }
            write_snapshot(picks, "2026-08-21_2026-08-20_220000.json", same_day_later_legacy)

            with mock.patch.object(server, "PICKS", picks):
                daily = server.history_payload(limit=120)
                raw = server.history_payload(limit=120, view="raw")

            self.assertEqual(len(daily["history"]), 2)
            self.assertEqual(daily["meta"]["raw_run_count"], 4)
            self.assertEqual(daily["meta"]["decision_day_count"], 2)
            self.assertEqual(daily["meta"]["duplicate_run_count"], 2)
            self.assertEqual(daily["meta"]["global_contract_day_count"], 1)
            self.assertEqual(daily["meta"]["legacy_day_count"], 1)
            self.assertEqual(raw["meta"]["view"], "raw")
            self.assertEqual(len(raw["history"]), 4)
            contract_row = next(row for row in daily["history"] if row["target_date"] == "2026-08-21")
            self.assertEqual(contract_row["history_kind"], "global_10d_v1")

            legacy_row = next(row for row in daily["history"] if row["history_kind"] == "legacy_snapshot")
            self.assertEqual(legacy_row["action"], "LEGACY_ONLY")
            self.assertIsNone(legacy_row["global_decision"])
            self.assertEqual(legacy_row["a_share_legacy"]["estimated_2d_range"], "-1.0% ~ +3.0%")
            self.assertIsNone(legacy_row["a_share_legacy"]["estimated_2w_range"])

    def test_invalid_settled_outcome_stays_out_of_settled_count(self) -> None:
        row = {
            "target_date": "2026-08-01",
            "generated_at": "2026-08-01T08:00:00+08:00",
            "forecast_end_date": "2026-08-15",
            "history_kind": "global_10d_v1",
            "global_decision": {
                "action": "REVIEW_EXECUTABLE_PICK",
                "primary": {"prediction_id": "p-1", "model_id": "m-1", "label_version": "labels-v1"},
            },
            "outcome": {
                "status": "SETTLED",
                "prediction_id": "p-1",
                "model_id": "wrong-model",
                "label_version": "labels-v1",
                "entry_at": "2026-08-01T09:30:00+08:00",
                "entry_price": 100.0,
                "entry_source": "exchange_open_v1",
                "exit_at": "2026-08-15T15:00:00+08:00",
                "exit_price": 108.0,
                "exit_source": "exchange_close_v1",
                "gross_total_return": 0.082,
                "net_total_return": 0.08,
                "transaction_cost": 0.002,
                "corporate_action_adjusted": True,
                "calendar_id": "XSHG-v1",
                "currency": "CNY",
                "fx_rate_source": "same_currency",
                "positive_label": True,
                "settled_at": "2026-08-16T16:00:00+08:00",
            },
        }
        invalid = server.history_metadata([row], [row], "daily", 1)
        self.assertEqual(invalid["executable_prediction_count"], 1)
        self.assertEqual(invalid["settled_sample_count"], 0)
        self.assertEqual(invalid["missing_outcome_count"], 1)

        row["outcome"]["model_id"] = "m-1"
        valid = server.history_metadata([row], [row], "daily", 1)
        self.assertEqual(valid["settled_sample_count"], 1)
        self.assertEqual(valid["missing_outcome_count"], 0)

        for invalid_return in (None, "", "0.08", True):
            with self.subTest(net_total_return=invalid_return):
                row["outcome"]["net_total_return"] = invalid_return
                invalid = server.history_metadata([row], [row], "daily", 1)
                self.assertEqual(invalid["settled_sample_count"], 0)
                self.assertEqual(invalid["missing_outcome_count"], 1)

        row["outcome"].update(
            {
                "net_total_return": 0.08,
                "positive_label": True,
                "exit_at": "2026-08-14T18:00:00Z",
                "settled_at": "2026-08-14T19:00:00Z",
            }
        )
        timezone_aligned = server.history_metadata([row], [row], "daily", 1)
        self.assertEqual(timezone_aligned["settled_sample_count"], 1)

    def test_no_valid_pick_is_abstention_not_prediction_or_loss(self) -> None:
        row = {
            "target_date": "2026-08-21",
            "history_kind": "global_10d_v1",
            "global_decision": {"action": "NO_VALID_PICK", "primary": None},
        }
        meta = server.history_metadata([row], [row], "daily", 1)
        self.assertEqual(meta["no_valid_pick_day_count"], 1)
        self.assertEqual(meta["executable_prediction_count"], 0)
        self.assertEqual(meta["settled_sample_count"], 0)


if __name__ == "__main__":
    unittest.main()
