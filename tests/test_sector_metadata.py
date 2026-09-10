from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sector_metadata as sectors


NOW = dt.datetime(2026, 9, 10, 8, tzinfo=dt.timezone.utc)


def payload(*rows):
    return {"rc": 0, "data": {"total": len(rows), "diff": list(rows)}}


def provider_row(code, venue, industry):
    return {"f12": code, "f13": venue, "f100": industry}


class SectorMetadataTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sector-cache.json"

    def enrich(self, candidates, fetcher, metadata=None, now=NOW):
        return sectors.enrich_sector_metadata(metadata or {}, candidates,
                                             now=now, cache_path=self.path, fetcher=fetcher)

    def test_missing_industry_is_not_inferred_from_name(self):
        for value in ({"name": "Example AI Technology"}, {"industry": "-"},
                      {"industry": "Unknown"}, {"industry": "null"}, {"industry": 123}):
            self.assertIsNone(sectors.parse_sector_record(value, source="fixture"))

    def test_explicit_record_preserves_source_timestamp_and_granularity(self):
        row = sectors.parse_sector_record({"industry": " Banks "}, source="fixture",
                                          retrieved_at=NOW.isoformat(), source_url="https://example.test")
        self.assertEqual(row["name"], "Banks")
        self.assertEqual(row["source"], "fixture")
        self.assertEqual(row["retrieved_at"], NOW.isoformat())
        self.assertEqual(row["granularity"], "industry")

    def test_batched_markets_real_classification_and_identity(self):
        requested = []
        candidates = {"a_share": [{"code": "920001"}, {"code": "600000"}],
                      "hk": [{"code": "1191.HK"}],
                      "us": [{"code": "DELL", "recall_metrics": {"exchange": "NYSE"}},
                             {"code": "BRK-B", "market_segment": "nyse"}]}

        def fetch(secids):
            requested.extend(secids)
            return payload(provider_row("920001", 0, "光学光电子"),
                           provider_row("600000", 1, "银行Ⅱ"),
                           provider_row("01191", 116, "工业工程"),
                           provider_row("DELL", 106, "信息技术"),
                           provider_row("BRK_B", 106, "金融"),
                           provider_row("1191", 105, "Wrong market"))

        metadata = {"us": {"DELL": {"themes": ["AI服务器"], "role": "服务器"}}}
        original = copy.deepcopy(metadata)
        result, diagnostics = self.enrich(candidates, fetch, metadata)
        self.assertEqual(metadata, original)
        self.assertEqual(set(requested), {"0.920001", "1.600000", "116.01191", "106.DELL", "106.BRK_B"})
        self.assertEqual(result["hk"]["1191.HK"]["industry"], "工业工程")
        self.assertEqual(result["us"]["DELL"]["sector"], "信息技术")
        self.assertEqual(result["us"]["DELL"]["themes"], ["AI服务器"])
        evidence = result["us"]["BRK-B"]["sector_metadata"]
        self.assertEqual(evidence["source_field"], "f100")
        self.assertEqual(evidence["granularity"], "sector")
        self.assertEqual(evidence["taxonomy"], "eastmoney_sector")
        self.assertEqual(evidence["retrieved_at"], NOW.isoformat())
        self.assertEqual(evidence["status"], "FRESH")
        self.assertIn("106.BRK_B", evidence["source_url"])
        self.assertEqual(diagnostics["fresh_count"], 5)
        self.assertEqual(diagnostics["markets"]["hk"]["coverage_pct"], 100.0)

    def test_missing_exchange_uses_bounded_routes_and_rejects_ambiguity(self):
        requested = []

        def fetch(secids):
            requested.extend(secids)
            return payload(provider_row("AAPL", 105, "信息技术"),
                           provider_row("DUP", 105, "金融"), provider_row("DUP", 106, "金融"))

        result, diagnostics = self.enrich({"us": [{"code": "AAPL"}, {"code": "DUP"}]}, fetch)
        self.assertEqual(len(requested), 6)
        self.assertEqual(result["us"]["AAPL"]["sector"], "信息技术")
        self.assertEqual(result["us"]["DUP"]["sector_metadata"]["status"], "MISSING")
        self.assertEqual(diagnostics["failure_reasons"]["AMBIGUOUS_PROVIDER_IDENTITY"], 1)

    def test_wrong_venue_and_unsolicited_symbol_are_not_accepted(self):
        result, diagnostics = self.enrich(
            {"us": [{"code": "AAPL", "market_segment": "nasdaq"}]},
            lambda ids: payload(provider_row("AAPL", 106, "金融"), provider_row("MSFT", 105, "信息技术")))
        self.assertEqual(result["us"]["AAPL"]["sector_metadata"]["status"], "MISSING")
        self.assertNotIn("MSFT", result["us"])
        self.assertEqual(diagnostics["fresh_count"], 0)

    def test_multiple_venues_are_ambiguous_even_if_one_label_is_missing(self):
        result, diagnostics = self.enrich({"us": [{"code": "DUP"}]},
            lambda ids: payload(provider_row("DUP", 105, "信息技术"), provider_row("DUP", 106, "-")))
        self.assertEqual(result["us"]["DUP"]["sector_metadata"]["status"], "MISSING")
        self.assertEqual(diagnostics["failure_reasons"]["AMBIGUOUS_PROVIDER_IDENTITY"], 1)

    def test_conflicting_duplicate_provider_rows_are_not_last_write_wins(self):
        result, diagnostics = self.enrich({"a_share": [{"code": "600000"}]},
            lambda ids: payload(provider_row("600000", 1, "银行"), provider_row("600000", 1, "煤炭")))
        self.assertEqual(result["a_share"]["600000"]["sector_metadata"]["status"], "MISSING")
        self.assertEqual(diagnostics["fresh_count"], 0)

    def test_repeated_refresh_reuses_fresh_cache_without_external_calls(self):
        candidates = {"hk": [{"symbol": "00700.HK"}]}
        self.enrich(candidates, lambda ids: payload(provider_row("00700", 116, "软件服务")))
        result, diagnostics = self.enrich(candidates, lambda ids: self.fail("unexpected network"),
                                           now=NOW + dt.timedelta(days=1))
        self.assertEqual(diagnostics["request_count"], 0)
        self.assertEqual(diagnostics["cache_hit_count"], 1)
        self.assertEqual(result["hk"]["0700.HK"]["sector_metadata"]["retrieved_at"], NOW.isoformat())

    def test_failed_refresh_retains_good_record_and_failure_cooldown(self):
        candidates = {"a_share": [{"code": "600000"}]}
        self.enrich(candidates, lambda ids: payload(provider_row("600000", 1, "银行Ⅱ")))
        initial = json.loads(self.path.read_text())["records"]

        def broken(ids):
            raise TimeoutError("provider unreachable")

        later = NOW + dt.timedelta(days=8)
        result, diagnostics = self.enrich(candidates, broken, now=later)
        evidence = result["a_share"]["600000"]["sector_metadata"]
        self.assertEqual(evidence["status"], "STALE")
        self.assertTrue(evidence["stale"])
        self.assertEqual(evidence["retrieved_at"], NOW.isoformat())
        self.assertEqual(json.loads(self.path.read_text())["records"], initial)
        self.assertEqual(diagnostics["stale_count"], 1)
        _, suppressed = self.enrich(candidates, lambda ids: self.fail("failure cooldown missing"),
                                    now=later + dt.timedelta(hours=1))
        self.assertEqual(suppressed["negative_cache_hit_count"], 1)
        recovered, retry = self.enrich(candidates, lambda ids: payload(provider_row("600000", 1, "银行")),
                                       now=later + dt.timedelta(hours=7))
        self.assertEqual(retry["request_count"], 1)
        self.assertEqual(recovered["a_share"]["600000"]["sector_metadata"]["status"], "FRESH")
        self.assertEqual(json.loads(self.path.read_text())["failures"], {})

    def test_fresh_missing_field_has_negative_cache_and_preserves_curated_theme(self):
        candidates = {"us": [{"code": "AI", "name": "AI Semiconductors"}]}
        metadata = {"us": {"AI": {"themes": ["半导体"], "source": "reference_metadata"}}}
        result, first = self.enrich(candidates, lambda ids: payload(provider_row("AI", 106, "-")), metadata)
        self.assertNotIn("industry", result["us"]["AI"])
        self.assertEqual(result["us"]["AI"]["sector_metadata"]["status"], "MISSING")
        self.assertEqual(result["us"]["AI"]["sector_metadata"]["fallback"]["status"], "APPROXIMATE")
        _, repeat = self.enrich(candidates, lambda ids: self.fail("must use negative cache"), metadata)
        self.assertEqual(first["missing_count"], 1)
        self.assertEqual(repeat["negative_cache_hit_count"], 1)

    def test_future_and_expired_cached_data_cannot_supply_classification(self):
        candidates = {"us": [{"code": "AAPL", "market_segment": "nasdaq"}]}
        self.enrich(candidates, lambda ids: payload(provider_row("AAPL", 105, "信息技术")))
        for anchor in (NOW - dt.timedelta(days=1), NOW + dt.timedelta(days=91)):
            with self.subTest(anchor=anchor):
                result, _ = self.enrich(candidates, lambda ids: payload(), now=anchor)
                self.assertEqual(result["us"]["AAPL"]["sector_metadata"]["status"], "MISSING")

    def test_request_budget_deferred_records_are_not_cached_as_provider_failures(self):
        candidates = {"a_share": [{"code": f"{600000 + n}"} for n in range(12)]}
        calls = []

        def fetch(ids):
            calls.append(ids)
            return payload(*(provider_row(value.split(".")[1], 1, "银行") for value in ids))

        with patch.object(sectors, "BATCH_SIZE", 3), patch.object(sectors, "MAX_REQUESTS", 2):
            result, diagnostics = self.enrich(candidates, fetch)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(len(batch) <= 3 for batch in calls))
        self.assertEqual(diagnostics["deferred_count"], 6)
        self.assertEqual(diagnostics["fresh_count"], 6)
        self.assertEqual(json.loads(self.path.read_text())["failures"], {})
        self.assertEqual(result["a_share"]["600011"]["sector_metadata"]["refresh_status"], "DEFERRED_BUDGET")

    def test_unknown_exchange_identity_routes_remain_in_same_batch(self):
        calls = []

        def fetch(ids):
            calls.append(ids)
            return payload(*(provider_row(value.split(".")[1], 105, "信息技术")
                             for value in ids if value.startswith("105.")))

        with patch.object(sectors, "BATCH_SIZE", 4):
            result, _ = self.enrich({"us": [{"code": "AAA"}, {"code": "BBB"}]}, fetch)
        self.assertEqual([len(batch) for batch in calls], [3, 3])
        self.assertEqual(result["us"]["BBB"]["sector_metadata"]["status"], "FRESH")

    def test_invalid_json_cache_recovers_with_explicit_diagnostic(self):
        self.path.write_text("broken", encoding="utf-8")
        result, diagnostics = self.enrich({"hk": [{"code": "0700.HK"}]},
                                          lambda ids: payload(provider_row("00700", 116, "软件服务")))
        self.assertEqual(diagnostics["cache_read_status"], "INVALID")
        self.assertEqual(result["hk"]["0700.HK"]["industry"], "软件服务")

    def test_malformed_cached_record_cannot_crash_or_supply_classification(self):
        candidates = {"hk": [{"code": "0700.HK"}]}
        self.enrich(candidates, lambda ids: payload(provider_row("00700", 116, "软件服务")))
        cache = json.loads(self.path.read_text())
        cache["records"]["hk:0700.HK"].pop("granularity")
        self.path.write_text(json.dumps(cache), encoding="utf-8")
        result, diagnostics = self.enrich(candidates, lambda ids: payload())
        self.assertEqual(result["hk"]["0700.HK"]["sector_metadata"]["status"], "MISSING")
        self.assertEqual(diagnostics["cache_hit_count"], 0)

    def test_dictionary_provider_rows_are_parsed(self):
        result, _ = self.enrich({"a_share": [{"code": "600000"}]},
            lambda ids: {"rc": 0, "data": {"total": 1, "diff": {"0": provider_row("600000", 1, "银行")}}})
        self.assertEqual(result["a_share"]["600000"]["industry"], "银行")

    def test_provider_error_payload_is_not_a_successful_empty_scan(self):
        _, diagnostics = self.enrich({"hk": [{"code": "0700.HK"}]},
                                      lambda ids: {"rc": -1, "data": None})
        self.assertEqual(diagnostics["failure_reasons"]["PROVIDER_ERROR"], 1)

    def test_default_transport_has_bounded_timeout_and_correct_fields(self):
        with patch.object(sectors.requests, "get") as get:
            get.return_value.json.return_value = payload(provider_row("600000", 1, "银行"))
            sectors.enrich_sector_metadata({}, {"a_share": [{"code": "600000"}]},
                                           now=NOW, cache_path=self.path)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["timeout"], sectors.REQUEST_TIMEOUT)
        self.assertEqual(get.call_args.kwargs["params"]["fields"], "f12,f13,f100")

    def test_naive_now_is_rejected(self):
        with self.assertRaises(ValueError):
            self.enrich({}, lambda ids: self.fail("network"), now=dt.datetime(2026, 9, 10))


if __name__ == "__main__":
    unittest.main()
