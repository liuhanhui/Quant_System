"""网页看板 API。"""
from __future__ import annotations
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class DashboardAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_index_serves_dashboard(self):
        rv = self.client.get("/")
        self.assertEqual(rv.status_code, 200)
        html = rv.get_data(as_text=True)
        self.assertIn("研究看板", html)
        self.assertIn("回测", html)
        self.assertIn("no-store", rv.headers.get("Cache-Control", ""))

    def test_strategies_endpoint(self):
        rv = self.client.get("/api/strategies")
        self.assertEqual(rv.status_code, 200)
        keys = {s["key"] for s in rv.get_json()["strategies"]}
        self.assertEqual(keys, {"dma", "boll"})

    def test_source_status(self):
        rv = self.client.get("/api/source")
        self.assertEqual(rv.status_code, 200)
        self.assertIn("tushare_token", rv.get_json())

    def test_run_rejects_unknown_strategy(self):
        rv = self.client.post("/api/run", json={"strategy": "nope"})
        self.assertEqual(rv.status_code, 400)

    def test_run_dma_on_tiny_csv(self):
        csv = (
            "datetime,symbol,price,volume\n"
            + "\n".join(
                f"2026-09-21 10:00:{i:02d},TESTA,10.{i:02d},100" for i in range(40)
            )
        )
        rv = self.client.post(
            "/api/run",
            data={
                "strategy": "dma",
                "symbol": "TESTA",
                "cash": "1000000",
                "fast": "5",
                "slow": "12",
                "file": (io.BytesIO(csv.encode("utf-8")), "ticks.csv"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(rv.status_code, 200)
        body = rv.get_json()
        self.assertEqual(body["strategy"], "dma")
        self.assertEqual(body["symbol"], "TESTA")
        self.assertGreater(body["tick_count"], 0)
        self.assertIn("equity", body)
        self.assertIn("report", body)

    def test_index_has_quotes_tab(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("行情", html)
        self.assertIn("data-tab=\"quotes\"", html)
        self.assertIn("美股", html)
        self.assertIn("data-tab=\"us\"", html)
        self.assertIn("class=\"tab active\"", html)
        self.assertIn("港股", html)
        self.assertIn("data-tab=\"hk\"", html)
        self.assertIn("usCloseChart", html)
        self.assertIn("/api/us/quotes?symbol=AAPL", html)

    def test_app_js_defines_us_status_helper(self):
        js_path = os.path.join(ROOT, "web", "static", "app.js")
        with open(js_path, encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("function setUsStatus", js)
        self.assertIn("function loadUsQuotes", js)

    def test_stocks_search_endpoint(self):
        from unittest.mock import patch
        fake = [{"ts_code": "688256.SH", "symbol": "688256", "name": "寒武纪",
                 "industry": "半导体", "market": "科创板"}]
        with patch("web.app.search_stocks", return_value=fake):
            rv = self.client.get("/api/stocks?q=寒武纪")
        self.assertEqual(rv.status_code, 200)
        body = rv.get_json()
        self.assertEqual(body["stocks"][0]["name"], "寒武纪")

    def test_quotes_requires_symbol(self):
        rv = self.client.get("/api/quotes")
        self.assertEqual(rv.status_code, 400)

    def test_quotes_endpoint(self):
        from unittest.mock import patch
        fake = {
            "ts_code": "688256.SH",
            "name": "寒武纪",
            "note": "Tushare 日线（未复权）",
            "bars": [{"date": "2025-09-29", "open": 1300, "high": 1350,
                      "low": 1280, "close": 1323.5, "vol": 10000,
                      "amount": 1.3e6, "pct_chg": 2.1}],
            "stats": {"first_close": 1323.5, "last_close": 1323.5,
                      "change_pct": 0.0, "high": 1350, "low": 1280, "bars": 1},
        }
        with patch("web.app.fetch_quote_daily", return_value=fake):
            rv = self.client.get(
                "/api/quotes?symbol=688256&start=2025-09-29&end=2025-09-30"
            )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()["name"], "寒武纪")

    def test_us_stocks_search_endpoint(self):
        from unittest.mock import patch
        fake = [{"ts_code": "AAPL", "symbol": "AAPL", "name": "苹果",
                 "enname": "Apple Inc.", "market": "US"}]
        with patch("web.app.search_us_stocks", return_value=fake):
            rv = self.client.get("/api/us/stocks?q=AAPL")
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()["stocks"][0]["ts_code"], "AAPL")

    def test_us_quotes_requires_symbol(self):
        rv = self.client.get("/api/us/quotes")
        self.assertEqual(rv.status_code, 400)

    def test_us_quotes_endpoint(self):
        from unittest.mock import patch
        fake = {
            "ts_code": "AAPL",
            "name": "苹果",
            "market": "US",
            "note": "Tushare 美股日线（未复权）",
            "bars": [{"date": "2025-09-29", "open": 250, "high": 255,
                      "low": 248, "close": 253, "vol": 4.5e7,
                      "amount": 1.1e10, "pct_chg": 1.2}],
            "stats": {"first_close": 253, "last_close": 253,
                      "change_pct": 0.0, "high": 255, "low": 248, "bars": 1},
        }
        with patch("web.app.fetch_us_quote_daily", return_value=fake):
            rv = self.client.get(
                "/api/us/quotes?symbol=AAPL&start=2025-09-29&end=2025-09-30"
            )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()["ts_code"], "AAPL")

    def test_hk_stocks_search_endpoint(self):
        from unittest.mock import patch
        fake = [{"ts_code": "00700.HK", "symbol": "00700.HK", "name": "腾讯控股",
                 "enname": "TENCENT", "market": "HK"}]
        with patch("web.app.search_hk_stocks", return_value=fake):
            rv = self.client.get("/api/hk/stocks?q=腾讯")
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()["stocks"][0]["ts_code"], "00700.HK")

    def test_hk_quotes_requires_symbol(self):
        rv = self.client.get("/api/hk/quotes")
        self.assertEqual(rv.status_code, 400)

    def test_hk_quotes_endpoint(self):
        from unittest.mock import patch
        fake = {
            "ts_code": "00700.HK",
            "name": "腾讯控股",
            "market": "HK",
            "note": "Tushare 港股日线（未复权）",
            "bars": [{"date": "2025-09-29", "open": 500, "high": 510,
                      "low": 495, "close": 508, "vol": 1.2e7,
                      "amount": 6.0e9, "pct_chg": 1.1}],
            "stats": {"first_close": 508, "last_close": 508,
                      "change_pct": 0.0, "high": 510, "low": 495, "bars": 1},
        }
        with patch("web.app.fetch_hk_quote_daily", return_value=fake):
            rv = self.client.get(
                "/api/hk/quotes?symbol=00700.HK&start=2025-09-29&end=2025-09-30"
            )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()["ts_code"], "00700.HK")


if __name__ == "__main__":
    unittest.main()
