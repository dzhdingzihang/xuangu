from __future__ import annotations

import datetime as dt
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import event_pipeline


CN = ZoneInfo("Asia/Shanghai")
NOW = dt.datetime(2026, 8, 23, 20, 0, tzinfo=CN)


def snapshot() -> dict:
    markets = {}
    for market, code in (("a_share", "300502"), ("hk", "0700.HK"), ("us", "NVDA")):
        markets[market] = {"_candidate_pool": [{"code": code, "name": code}], "decision": {}}
    return {"generated_at": NOW.isoformat(), "markets": markets}


class EventPipelineTests(unittest.TestCase):
    def test_event_scan_prefers_rule_ensemble_and_preserves_market_decision_rows(self) -> None:
        pool = []
        for index in range(1, 21):
            pool.append(
                {
                    "code": f"{index:04d}.HK",
                    "recommendation_degree": 35,
                    "v2": {"rank_percentile": 0.10},
                    "data_quality": {"score": 70},
                    "estimated_10d_range": {"low_pct": -8, "high_pct": 4},
                    "decision_gates": [{"status": "PASS"}],
                }
            )
        best = {
            "code": "0300.HK",
            "recommendation_degree": 82,
            "v2": {"rank_percentile": 0.98},
            "data_quality": {"score": 100},
            "estimated_10d_range": {"low_pct": -4, "high_pct": 10},
            "decision_gates": [{"status": "PASS"}],
            # A huge Shadow probability must not be needed by the pre-sort.
            "shadow_model": {"probability": 0.01},
        }
        pool.append(best)
        required = [pool[18], pool[17], *pool[8:16]]
        snap = snapshot()
        snap["markets"]["hk"] = {
            "_candidate_pool": pool,
            "decision": {
                "action": "BUY_CANDIDATE",
                "primary": required[0],
                "blocked_candidate": required[1],
                "watchlist": required[2:],
            },
        }

        symbols = event_pipeline._candidate_symbols(snap, "hk", 16)

        self.assertEqual(symbols[0], "0300.HK")
        self.assertEqual(len(symbols), 16)
        self.assertTrue({row["code"] for row in required}.issubset(symbols))

    def test_event_scan_priority_does_not_use_shadow_probability(self) -> None:
        baseline = {
            "recommendation_degree": 70,
            "v2": {"rank_percentile": 0.8},
            "data_quality": {"score": 100},
            "estimated_10d_range": {"low_pct": -4, "high_pct": 8},
        }
        low_shadow = {**baseline, "shadow_model": {"probability": 0.01}}
        high_shadow = {**baseline, "shadow_model": {"probability": 0.99}}
        self.assertEqual(
            event_pipeline._event_scan_priority(low_shadow, "BUY_CANDIDATE"),
            event_pipeline._event_scan_priority(high_shadow, "BUY_CANDIDATE"),
        )

    def test_published_production_primary_is_always_in_the_event_scan(self) -> None:
        snap = snapshot()
        snap["production_decision"] = {
            "action": "QUALIFIED_PICK",
            "primary": {"market": "hk", "code": "0300.HK"},
        }
        snap["markets"]["hk"]["decision"] = {
            "primary": snap["markets"]["hk"]["_candidate_pool"][0]
        }

        symbols = event_pipeline._candidate_symbols(snap, "hk", 1)

        self.assertIn("0300.HK", symbols)
        self.assertIn("0700.HK", symbols)

    def test_collection_defaults_to_sixteen_candidates_per_market(self) -> None:
        snap = snapshot()
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch.object(event_pipeline, "_candidate_symbols", return_value=[]) as choose,
            mock.patch.object(event_pipeline, "_collect_a_share", return_value=[]),
            mock.patch.object(event_pipeline, "_collect_hk", return_value=[]),
            mock.patch.object(event_pipeline, "_collect_us", return_value=[]),
        ):
            result = event_pipeline.collect_for_snapshot(snap, "run-1", now=NOW)

        self.assertEqual(result["pipeline"]["status"], "READY_EMPTY")
        self.assertEqual(result["pipeline"]["scan_purpose"], "positive_event_enrichment")
        self.assertEqual(result["pipeline"]["selection_policy"], "rule_priority_and_published_decision_v1")
        self.assertEqual(result["pipeline"]["candidate_limit_per_market"], 16)
        self.assertEqual(
            choose.call_args_list,
            [
                mock.call(snap, "a_share", 16),
                mock.call(snap, "hk", 16),
                mock.call(snap, "us", 16),
            ],
        )

    def test_cninfo_parser_keeps_official_direction_and_release_time(self) -> None:
        payload = {
            "announcements": [
                {
                    "announcementId": "a1",
                    "announcementTitle": "关于签订重大合同的公告",
                    "announcementTime": int((NOW - dt.timedelta(days=1)).timestamp() * 1000),
                    "adjunctUrl": "finalpage/2026-08-22/a1.pdf",
                }
            ]
        }
        event = event_pipeline.parse_cninfo_announcements(payload, "300502", "run-1", now=NOW)[0]
        self.assertEqual(event["direction"], "positive")
        self.assertTrue(event["decision_eligible"])
        self.assertEqual(event["released_at"], event["effective_at"])
        self.assertIsNone(event["scheduled_for"])
        self.assertTrue(event["url"].startswith("https://static.cninfo.com.cn/"))

    def test_prior_day_material_negative_remains_auditable(self) -> None:
        released = NOW - dt.timedelta(days=1)
        item = event_pipeline._event(
            market="us",
            symbol="NVDA",
            title="profit warning",
            url="https://www.sec.gov/Archives/edgar/data/1/a.htm",
            released_at=released,
            run_id="run-1",
            source_document_id="doc-1",
        )
        snap = snapshot()
        snap["events"] = {
            "pipeline": {
                "contract_version": "official-event-pipeline-v1",
                "run_id": "run-1",
                "status": "READY",
                "markets": ["a_share", "hk", "us"],
                "scanned_symbols": {"a_share": ["300502"], "hk": ["0700.HK"], "us": ["NVDA"]},
                "source_manifest": [
                    {"source_id": row["source_id"], "status": "SUCCESS"}
                    for row in event_pipeline.SOURCE_REGISTRY.values()
                ],
            }
        }
        self.assertTrue(event_pipeline.event_is_auditable(item, snap, "us", "NVDA"))
        self.assertTrue(item["decision_blocking"])

    def test_hkex_parser_accepts_exchange_day_month_year_format(self) -> None:
        page = """<table><tr><td>22/08/2026 18:30</td><td><a href='/listedco/listconews/sehk/2026/0822/a.pdf'>Major Contract Award</a></td></tr></table>"""
        events = event_pipeline.parse_hkex_titles(page, "0700.HK", "run-1", now=NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["released_at"][:10], "2026-08-22")
        self.assertTrue(events[0]["url"].startswith("https://www1.hkexnews.hk/"))

    def test_self_declared_official_event_on_untrusted_host_is_rejected(self) -> None:
        item = event_pipeline._event(
            market="a_share",
            symbol="300502",
            title="重大合同",
            url="https://example.com/fake.pdf",
            released_at=NOW - dt.timedelta(hours=1),
            run_id="run-1",
            source_document_id="fake",
        )
        snap = snapshot()
        snap["events"] = {"pipeline": {}}
        self.assertFalse(event_pipeline.event_is_auditable(item, snap))

    def test_collection_is_ready_empty_only_when_every_source_succeeds(self) -> None:
        calls = []

        class Response:
            def __init__(self, *, payload=None, text=""):
                self.payload = payload
                self.text = text

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        def fetch(method, url, **kwargs):
            calls.append(url)
            if url.endswith("szse_stock.json"):
                return Response(payload={"stockList": [{"code": "300502", "orgId": "org"}]})
            if "hisAnnouncement" in url:
                return Response(payload={"announcements": []})
            if "prefix.do" in url:
                return Response(text='callback({"stockId":"7609"})')
            if "titlesearch" in url:
                return Response(text="<table></table>")
            if url.endswith("company_tickers.json"):
                return Response(payload={"0": {"ticker": "NVDA", "cik_str": 1045810}})
            if "submissions" in url:
                return Response(payload={"filings": {"recent": {}}})
            raise AssertionError(url)

        result = event_pipeline.collect_for_snapshot(snapshot(), "run-1", now=NOW, fetcher=fetch)
        self.assertEqual(result["pipeline"]["status"], "READY_EMPTY")
        self.assertTrue(event_pipeline.pipeline_complete(result))
        self.assertEqual(result["items"], [])
        self.assertEqual(set(result["pipeline"]["markets"]), {"a_share", "hk", "us"})
        self.assertGreaterEqual(len(calls), 6)

    def test_one_source_failure_makes_pipeline_partial(self) -> None:
        def fetch(method, url, **kwargs):
            raise OSError("offline")

        result = event_pipeline.collect_for_snapshot(snapshot(), "run-1", now=NOW, fetcher=fetch)
        self.assertEqual(result["pipeline"]["status"], "PARTIAL")
        self.assertFalse(event_pipeline.pipeline_complete(result))
        self.assertEqual(result["pipeline"]["markets"], [])

    def test_market_pipeline_health_is_isolated_from_other_source_failures(self) -> None:
        value = {
            "pipeline": {
                "contract_version": "official-event-pipeline-v1",
                "run_id": "run-1",
                "status": "PARTIAL",
                "markets": ["hk"],
                "scanned_symbols": {"a_share": ["300502"], "hk": ["0700.HK"], "us": ["NVDA"]},
                "source_manifest": [
                    {"source_id": event_pipeline.SOURCE_REGISTRY["a_share"]["source_id"], "status": "ERROR"},
                    {"source_id": event_pipeline.SOURCE_REGISTRY["hk"]["source_id"], "status": "SUCCESS"},
                    {"source_id": event_pipeline.SOURCE_REGISTRY["us"]["source_id"], "status": "ERROR"},
                ],
            }
        }
        self.assertFalse(event_pipeline.pipeline_complete(value))
        self.assertTrue(event_pipeline.pipeline_market_complete(value, "hk"))
        self.assertFalse(event_pipeline.pipeline_market_complete(value, "a_share"))
        self.assertFalse(event_pipeline.pipeline_market_complete(value, "us"))


if __name__ == "__main__":
    unittest.main()
