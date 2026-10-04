"""港股搜索与日 K（不打真实网络）。"""
from __future__ import annotations
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd

from data.hk_source import fetch_hk_quote_daily, search_hk_stocks, to_hk_symbol


class HkSourceTests(unittest.TestCase):
    def test_to_hk_symbol(self):
        self.assertEqual(to_hk_symbol("700"), "00700.HK")
        self.assertEqual(to_hk_symbol("00700"), "00700.HK")
        self.assertEqual(to_hk_symbol("0700.HK"), "00700.HK")
        self.assertEqual(to_hk_symbol("9988.hk"), "09988.HK")

    def test_search_by_name_or_code(self):
        class Listed:
            def hk_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["00700.HK", "09988.HK", "03690.HK"],
                    "name": ["腾讯控股", "阿里巴巴-W", "美团-W"],
                    "enname": ["TENCENT", "ALIBABA", "MEITUAN"],
                    "market": ["主板", "主板", "主板"],
                })

        hits = search_hk_stocks("腾讯", client=Listed())
        self.assertEqual(hits[0]["ts_code"], "00700.HK")
        by_code = search_hk_stocks("9988", client=Listed())
        self.assertEqual(by_code[0]["name"], "阿里巴巴-W")

    def test_unknown_code_still_returned(self):
        class Listed:
            def hk_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["00700.HK"],
                    "name": ["腾讯控股"],
                    "enname": ["TENCENT"],
                    "market": ["主板"],
                })

        hits = search_hk_stocks("1810", client=Listed())
        self.assertEqual(hits[0]["ts_code"], "01810.HK")

    def test_fetch_quote_keeps_ohlc(self):
        class Daily:
            def hk_daily(self, **kwargs):
                self.kwargs = kwargs
                return pd.DataFrame({
                    "ts_code": ["00700.HK", "00700.HK"],
                    "trade_date": ["20250929", "20250930"],
                    "open": [500.0, 505.0],
                    "high": [510.0, 508.0],
                    "low": [495.0, 500.0],
                    "close": [508.0, 502.0],
                    "vol": [1.2e7, 1.0e7],
                    "amount": [6.0e9, 5.0e9],
                    "pct_chg": [1.1, -1.18],
                })

            def hk_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["00700.HK"],
                    "name": ["腾讯控股"],
                    "enname": ["TENCENT"],
                    "market": ["主板"],
                })

        client = Daily()
        payload = fetch_hk_quote_daily(
            "00700.HK", start="2025-09-29", end="2025-09-30", client=client,
        )
        self.assertEqual(payload["ts_code"], "00700.HK")
        self.assertEqual(payload["name"], "腾讯控股")
        self.assertEqual(payload["market"], "HK")
        self.assertEqual(len(payload["bars"]), 2)
        self.assertEqual(payload["bars"][0]["open"], 500.0)
        self.assertEqual(client.kwargs["ts_code"], "00700.HK")
        self.assertAlmostEqual(payload["stats"]["change_pct"], 502.0 / 508.0 - 1, places=6)

    def test_newest_first_rows_become_oldest_left(self):
        class Daily:
            def hk_daily(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["00700.HK", "00700.HK"],
                    "trade_date": ["20250930", "20250929"],
                    "open": [505.0, 500.0],
                    "high": [508.0, 510.0],
                    "low": [500.0, 495.0],
                    "close": [502.0, 508.0],
                    "vol": [1.0e7, 1.2e7],
                    "amount": [5.0e9, 6.0e9],
                    "pct_chg": [-1.18, 1.1],
                })

            def hk_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["00700.HK"],
                    "name": ["腾讯控股"],
                    "enname": ["TENCENT"],
                    "market": ["主板"],
                })

        payload = fetch_hk_quote_daily(
            "00700.HK", start="2025-09-29", end="2025-09-30", client=Daily(),
        )
        self.assertEqual([b["date"] for b in payload["bars"]], ["2025-09-29", "2025-09-30"])
        self.assertEqual(payload["start"], "2025-09-29")
        self.assertEqual(payload["end"], "2025-09-30")

    def test_cache_newest_first_is_still_chronological(self):
        import shutil
        import tempfile
        from data import hk_source

        tmp = tempfile.mkdtemp()
        old = hk_source.CACHE_DIR
        hk_source.CACHE_DIR = tmp
        try:
            os.makedirs(tmp, exist_ok=True)
            path = os.path.join(tmp, "00700.HK_Dohlc_20250929_20250930.csv")
            pd.DataFrame({
                "ts_code": ["00700.HK", "00700.HK"],
                "trade_date": ["20250930", "20250929"],
                "open": [505.0, 500.0],
                "high": [508.0, 510.0],
                "low": [500.0, 495.0],
                "close": [502.0, 508.0],
                "vol": [1.0e7, 1.2e7],
                "amount": [5.0e9, 6.0e9],
            }).to_csv(path, index=False)
            payload = fetch_hk_quote_daily(
                "00700.HK", start="2025-09-29", end="2025-09-30",
            )
            self.assertEqual(
                [b["date"] for b in payload["bars"]],
                ["2025-09-29", "2025-09-30"],
            )
        finally:
            hk_source.CACHE_DIR = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fetch_falls_back_when_tushare_denied(self):
        class Denied:
            def hk_daily(self, **kwargs):
                raise RuntimeError("抱歉，您没有接口(hk_daily)访问权限")

            def hk_basic(self, **kwargs):
                raise RuntimeError("抱歉，您没有接口(hk_basic)访问权限")

        def http_get(url: str) -> bytes:
            if "chart" in url and "0700.HK" in url:
                return json.dumps({
                    "chart": {"result": [{
                        "meta": {"symbol": "0700.HK", "shortName": "TENCENT"},
                        "timestamp": [1759104000, 1759190400],
                        "indicators": {"quote": [{
                            "open": [500.0, 505.0],
                            "high": [510.0, 508.0],
                            "low": [495.0, 500.0],
                            "close": [508.0, 502.0],
                            "volume": [12000000, 10000000],
                        }]},
                    }]},
                }).encode("utf-8")
            raise AssertionError(url)

        payload = fetch_hk_quote_daily(
            "700", start="2025-09-29", end="2025-09-30",
            client=Denied(), http_get=http_get,
        )
        self.assertEqual(payload["ts_code"], "00700.HK")
        self.assertEqual(len(payload["bars"]), 2)
        self.assertIn("Yahoo", payload["note"])


if __name__ == "__main__":
    unittest.main()
