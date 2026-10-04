"""美股搜索与日 K（不打真实网络）。"""
from __future__ import annotations
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd

from data.us_source import fetch_us_quote_daily, search_us_stocks, to_us_symbol


class UsSourceTests(unittest.TestCase):
    def test_to_us_symbol(self):
        self.assertEqual(to_us_symbol("aapl"), "AAPL")
        self.assertEqual(to_us_symbol("BRK.B"), "BRK-B")
        self.assertEqual(to_us_symbol("brk-b"), "BRK-B")

    def test_search_by_name_or_ticker(self):
        class Listed:
            def us_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["AAPL", "TSLA", "NVDA"],
                    "name": ["苹果", "特斯拉", "英伟达"],
                    "enname": ["Apple Inc.", "Tesla, Inc.", "NVIDIA Corporation"],
                    "classify": ["EQ", "EQ", "EQ"],
                })

        hits = search_us_stocks("苹果", client=Listed())
        self.assertEqual(hits[0]["ts_code"], "AAPL")
        by_code = search_us_stocks("tsla", client=Listed())
        self.assertEqual(by_code[0]["name"], "特斯拉")

    def test_unknown_ticker_still_returned(self):
        class Listed:
            def us_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["AAPL"],
                    "name": ["苹果"],
                    "enname": ["Apple Inc."],
                    "classify": ["EQ"],
                })

        hits = search_us_stocks("MSFT", client=Listed())
        self.assertEqual(hits[0]["ts_code"], "MSFT")

    def test_fetch_quote_keeps_ohlc(self):
        class Daily:
            def us_daily(self, **kwargs):
                self.kwargs = kwargs
                return pd.DataFrame({
                    "ts_code": ["AAPL", "AAPL"],
                    "trade_date": ["20250929", "20250930"],
                    "open": [250.0, 252.0],
                    "high": [255.0, 254.0],
                    "low": [248.0, 250.0],
                    "close": [253.0, 251.0],
                    "vol": [4.5e7, 3.8e7],
                    "amount": [1.1e10, 9.5e9],
                    "pct_change": [1.2, -0.79],
                })

            def us_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["AAPL"],
                    "name": ["苹果"],
                    "enname": ["Apple Inc."],
                    "classify": ["EQ"],
                })

        payload = fetch_us_quote_daily(
            "AAPL", start="2025-09-29", end="2025-09-30", client=Daily(),
        )
        self.assertEqual(payload["ts_code"], "AAPL")
        self.assertEqual(payload["name"], "苹果")
        self.assertEqual(payload["market"], "US")
        self.assertEqual(len(payload["bars"]), 2)
        self.assertEqual(payload["bars"][0]["open"], 250.0)
        self.assertEqual(payload["stats"]["high"], 255.0)
        self.assertAlmostEqual(payload["stats"]["change_pct"], 251.0 / 253.0 - 1, places=6)

    def test_fetch_falls_back_when_tushare_denied(self):
        class Denied:
            def us_daily(self, **kwargs):
                raise RuntimeError("抱歉，您没有接口(us_daily)访问权限")

            def us_basic(self, **kwargs):
                raise RuntimeError("抱歉，您没有接口(us_basic)访问权限")

        def http_get(url: str) -> bytes:
            if "chart" in url and "AAPL" in url:
                return json.dumps({
                    "chart": {"result": [{
                        "meta": {"symbol": "AAPL", "shortName": "Apple Inc."},
                        "timestamp": [1759104000, 1759190400],
                        "indicators": {"quote": [{
                            "open": [250.0, 252.0],
                            "high": [255.0, 254.0],
                            "low": [248.0, 250.0],
                            "close": [253.0, 251.0],
                            "volume": [45000000, 38000000],
                        }]},
                    }]},
                }).encode("utf-8")
            raise AssertionError(url)

        payload = fetch_us_quote_daily(
            "AAPL", start="2025-09-29", end="2025-09-30",
            client=Denied(), http_get=http_get,
        )
        self.assertEqual(payload["ts_code"], "AAPL")
        self.assertEqual(len(payload["bars"]), 2)
        self.assertIn("Yahoo", payload["note"])

    def test_search_survives_us_basic_error(self):
        class Boom:
            def us_basic(self, **kwargs):
                raise RuntimeError("抱歉，您每分钟接口(us_basic)频次超过限制")

        hits = search_us_stocks("AAPL", client=Boom())
        self.assertEqual(hits[0]["ts_code"], "AAPL")


if __name__ == "__main__":
    unittest.main()
