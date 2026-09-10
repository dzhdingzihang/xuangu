import unittest
from unittest import mock

import server


class SecurityIdentityRegressionTests(unittest.TestCase):
    def test_directory_stream_stops_at_byte_ceiling_and_closes_resources(self):
        response = mock.Mock()
        read_bytes = 0
        def read(size, **_kwargs):
            nonlocal read_bytes
            read_bytes += size
            return b"x" * size
        response.raw.read.side_effect = read
        session = mock.Mock()
        session.get.return_value = response
        server._us_security_directory.cache_clear()
        with mock.patch.object(server.requests, "Session", return_value=session), mock.patch.object(server.time, "monotonic", return_value=0):
            result = server._us_security_directory("test-body-limit")
        self.assertEqual(result, {})
        self.assertEqual(read_bytes, 3_000_000)
        self.assertTrue(session.get.call_args.kwargs["stream"])
        self.assertEqual(session.get.call_count, 1)
        response.close.assert_called_once()
        session.close.assert_called_once()
        server._us_security_directory.cache_clear()

    def test_directory_deadline_expires_before_reading_more_bytes(self):
        response = mock.Mock()
        session = mock.Mock()
        session.get.return_value = response
        server._us_security_directory.cache_clear()
        with mock.patch.object(server.requests, "Session", return_value=session), mock.patch.object(server.time, "monotonic", side_effect=[0, 16]):
            self.assertEqual(server._us_security_directory("test-deadline"), {})
        response.raw.read.assert_not_called()
        response.close.assert_called_once()
        server._us_security_directory.cache_clear()

    def test_observed_leveraged_product_is_not_an_ordinary_stock(self):
        self.assertTrue(server._blocked_dynamic_security_name("GRANITESHARES 2X LONG SK HYNIX", "us"))

    def test_product_patterns_and_ordinary_company_boundaries(self):
        for name in ("GraniteShares 2X Long NVDA", "Daily -2x Inverse Tesla", "Leverage Shares NVIDIA", "Invesco QQQ Trust", "Sprott Physical Silver Trust", "Example Company Warrants", "Example Company Units"):
            with self.subTest(name=name):
                self.assertTrue(server._blocked_dynamic_security_name(name, "us"))
        for name in ("Granite Construction Incorporated", "BlackRock Inc", "State Street Corporation", "WisdomTree Inc", "Funding Circle Holdings", "United Rentals", "Rightside Group"):
            with self.subTest(name=name):
                self.assertFalse(server._blocked_dynamic_security_name(name, "us"))

    def test_missing_type_is_not_a_verified_common_share(self):
        import security_identity
        result = security_identity.assess_security({"symbol": "TEST", "name": "Test Holdings"}, "us")
        self.assertTrue(result["eligible"])
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_provider_etf_evidence_wins_even_after_name_translation(self):
        import security_identity
        result = security_identity.assess_security({"symbol": "SKUU", "name": "海力士", "security_type_evidence": [{"source": "nasdaq_symbol_directory", "field": "ETF", "raw_value": "Y", "symbol": "SKUU", "retrieved_at": "2026-09-10T14:00:00+00:00"}]}, "us")
        self.assertFalse(result["eligible"])

    def test_type_evidence_cannot_be_borrowed_from_another_symbol(self):
        import security_identity
        result = security_identity.assess_security({"symbol": "TEST", "name": "Test", "security_type_evidence": [{"source": "nasdaq_symbol_directory", "field": "ETF", "raw_value": "N", "instrument_type": "COMMON_STOCK", "symbol": "AAPL", "retrieved_at": "2026-09-10T14:00:00+00:00"}]}, "us")
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_stale_or_future_positive_type_cannot_authorize_verification(self):
        import security_identity
        for stamp in ("2026-08-10T14:00:00+00:00", "2026-09-11T14:00:00+00:00", "not-a-time"):
            row = {"symbol": "TEST", "name": "Test", "observed_at": "2026-09-10T14:00:00+00:00", "security_type_evidence": [{"symbol": "TEST", "source": "yahoo_chart_meta", "field": "instrumentType", "raw_value": "EQUITY", "retrieved_at": stamp}]}
            self.assertFalse(security_identity.assess_security(row, "us")["verified"])
        row["security_type_evidence"][0]["retrieved_at"] = "2026-09-10T14:00:00+00:00"
        self.assertTrue(security_identity.assess_security(row, "us")["verified"])

    def test_unproven_negative_type_still_blocks_but_does_not_claim_verification(self):
        import security_identity
        verdict = security_identity.assess_security({"symbol": "TEST", "name": "Test", "security_type": "ETF"}, "us")
        self.assertFalse(verdict["eligible"])
        self.assertFalse(verdict["verified"])

    def test_directory_etf_flag_cannot_be_hidden_by_translated_name(self):
        import security_identity
        text = "Symbol|Security Name|ETF|Test Issue\nSKUU|GraniteShares 2x Long SK Hynix Daily ETF|Y|N\nAAPL|Apple Inc. - Common Stock|N|N\n"
        directory = security_identity.parse_nasdaq_directory(text, retrieved_at="2026-09-10T14:00:00+00:00")
        candidate = {"symbol": "SKUU", "name": "海力士", "observed_at": "2026-09-10T14:00:00+00:00", "security_type_evidence": directory["SKUU"]}
        self.assertFalse(security_identity.assess_security(candidate, "us")["eligible"])
        candidate.update(symbol="AAPL", name="苹果", security_type_evidence=directory["AAPL"])
        self.assertTrue(security_identity.assess_security(candidate, "us")["verified"])

    def test_final_scoring_excludes_known_product_before_network(self):
        from unittest import mock
        with mock.patch.object(server, "yahoo_realtime_quotes", return_value={}) as quotes, mock.patch.object(server, "yahoo_kline_map", return_value={}):
            result = server.score_serenity_candidates("us", [{"symbol": "SKUU", "name": "GRANITESHARES 2X LONG SK HYNIX"}])
        self.assertEqual(result["scored_size"], 0)
        self.assertEqual(result["quote_health"]["security_excluded_symbols"], ["SKUU"])
        self.assertNotIn("SKUU", quotes.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
