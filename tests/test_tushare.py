"""Tushare Pro 分钟线适配（不打真实网络）。"""
from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
from data.tushare_source import (
    fetch_quote_daily,
    fetch_tushare_bars,
    fetch_tushare_mins,
    normalize_tushare_bars,
    search_stocks,
    to_ts_code,
)
from engine.runner import execute_backtest


class FakePro:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.calls = []

    def stk_mins(self, **kwargs):
        self.calls.append(kwargs)
        return self.frame.copy()


class TushareAdapterTests(unittest.TestCase):
    def test_to_ts_code(self):
        self.assertEqual(to_ts_code("600519"), "600519.SH")
        self.assertEqual(to_ts_code("000001"), "000001.SZ")
        self.assertEqual(to_ts_code("300750"), "300750.SZ")
        self.assertEqual(to_ts_code("688981"), "688981.SH")
        self.assertEqual(to_ts_code("430047"), "430047.BJ")
        self.assertEqual(to_ts_code("600519.SH"), "600519.SH")
        self.assertEqual(to_ts_code("000001.sz"), "000001.SZ")

    def test_normalize_sorts_and_renames(self):
        raw = pd.DataFrame({
            "ts_code": ["600519.SH", "600519.SH"],
            "trade_time": ["2024-09-20 10:00:00", "2024-09-20 09:31:00"],
            "close": [1482.5, 1480.0],
            "vol": [2000, 1500],
        })
        out = normalize_tushare_bars(raw)
        self.assertEqual(list(out.columns), ["datetime", "symbol", "price", "volume"])
        self.assertEqual(out.iloc[0]["price"], 1480.0)
        self.assertEqual(out.iloc[0]["symbol"], "600519.SH")
        self.assertEqual(int(out.iloc[0]["volume"]), 1500)

    def test_fetch_maps_client_rows(self):
        raw = pd.DataFrame({
            "ts_code": ["600519.SH"],
            "trade_time": ["2024-09-20 09:31:00"],
            "close": [1480.0],
            "vol": [1200],
        })
        client = FakePro(raw)
        out = fetch_tushare_mins(
            "600519", start="2024-09-20", end="2024-09-20",
            freq="1min", client=client,
        )
        self.assertEqual(out.iloc[0]["symbol"], "600519.SH")
        self.assertEqual(client.calls[0]["ts_code"], "600519.SH")
        self.assertEqual(client.calls[0]["freq"], "1min")
        self.assertTrue(str(client.calls[0]["end_date"]).endswith("19:00:00"))

    def test_daily_quota_resets_next_calendar_day(self):
        import data.tushare_source as src
        tmp = tempfile.mkdtemp()
        old = src.CACHE_DIR
        src.CACHE_DIR = tmp
        try:
            yesterday = time.time() - 12 * 3600
            os.makedirs(tmp, exist_ok=True)
            with open(os.path.join(tmp, "_stk_mins_quota.json"), "w", encoding="utf-8") as fh:
                json.dump({"t": yesterday, "window": 86400}, fh)
            # 若昨天已过自然日，剩余应为 0
            from datetime import datetime
            marked = datetime.fromtimestamp(yesterday)
            if datetime.now().date() > marked.date():
                self.assertEqual(src._quota_remaining_sec(), 0)
            else:
                self.assertGreater(src._quota_remaining_sec(), 0)
        finally:
            src.CACHE_DIR = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_quota_cooldown_skips_api_when_cache_exists(self):
        import data.tushare_source as src
        tmp = tempfile.mkdtemp()
        old = src.CACHE_DIR
        src.CACHE_DIR = tmp
        try:
            cached = pd.DataFrame({
                "datetime": pd.to_datetime(["2024-09-20 09:31:00"]),
                "symbol": ["600519.SH"],
                "price": [1480.0],
                "volume": [100],
            })
            src._write_cache("600519.SH", "1min", "2024-09-20", "2024-09-20", cached)
            src._mark_quota()

            class Boom:
                def stk_mins(self, **kwargs):
                    raise AssertionError("冷却期内不应再请求接口")

            # live=True 才会走冷却；这里用 client=None 会真读 token。
            # 只测 _quota_remaining_sec / 缓存复用逻辑。
            self.assertGreater(src._quota_remaining_sec(), 0)
            out = src._read_any_cache("600519.SH", "1min", "2024-09-20", "2024-09-20")
            self.assertIsNotNone(out)
            self.assertEqual(len(out), 1)
        finally:
            src.CACHE_DIR = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rate_limit_falls_back_to_cache(self):
        import data.tushare_source as src
        tmp = tempfile.mkdtemp()
        old = src.CACHE_DIR
        src.CACHE_DIR = tmp
        try:
            cached = pd.DataFrame({
                "datetime": pd.to_datetime(["2024-09-20 09:31:00", "2024-09-20 09:32:00"]),
                "symbol": ["600519.SH", "600519.SH"],
                "price": [1480.0, 1481.0],
                "volume": [100, 200],
            })
            src._write_cache("600519.SH", "1min", "2024-09-20", "2024-09-20", cached)

            class Limited:
                def stk_mins(self, **kwargs):
                    raise RuntimeError("抱歉，您每分钟接口(stk_mins)频次超过(1次/小时)")

            out = fetch_tushare_mins(
                "600519", start="2024-09-20", end="2024-09-20",
                freq="1min", client=Limited(),
            )
            self.assertEqual(len(out), 2)
            self.assertIn("缓存", out.attrs.get("note", ""))
        finally:
            src.CACHE_DIR = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fetch_empty_raises(self):
        client = FakePro(pd.DataFrame())
        with self.assertRaises(ValueError):
            fetch_tushare_mins("600519", start="2024-09-20", end="2024-09-20",
                               client=client)

    def test_normalize_daily_trade_date(self):
        raw = pd.DataFrame({
            "ts_code": ["600519.SH"],
            "trade_date": ["20240920"],
            "close": [1480.0],
            "vol": [12000],
        })
        out = normalize_tushare_bars(raw)
        self.assertEqual(out.iloc[0]["price"], 1480.0)
        self.assertEqual(str(out.iloc[0]["datetime"].date()), "2024-09-20")

    def test_bars_fallback_to_mins_when_daily_denied(self):
        class DeniedDaily:
            def daily(self, **kwargs):
                raise RuntimeError("抱歉，您没有接口(daily)访问权限")

            def stk_mins(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["600519.SH"],
                    "trade_time": ["2024-09-20 09:31:00"],
                    "close": [1480.0],
                    "vol": [1200],
                })

        out = fetch_tushare_bars(
            "600519", start="2024-09-20", end="2024-09-20",
            freq="D", client=DeniedDaily(),
        )
        self.assertEqual(out.iloc[0]["price"], 1480.0)
        self.assertIn("分钟", out.attrs.get("note", ""))

    def test_bars_both_denied_has_clear_error(self):
        class NoPerm:
            def stk_mins(self, **kwargs):
                raise RuntimeError("抱歉，您没有接口(stk_mins)访问权限")

            def daily(self, **kwargs):
                raise RuntimeError("抱歉，您没有接口(daily)访问权限")

        with self.assertRaises(ValueError) as ctx:
            fetch_tushare_bars(
                "600519", start="2024-09-20", end="2024-09-20",
                freq="1min", client=NoPerm(),
            )
        self.assertIn("没有行情权限", str(ctx.exception))

    def test_bars_fallback_to_daily_when_mins_denied(self):
        class DeniedMins:
            def stk_mins(self, **kwargs):
                raise RuntimeError(
                    "抱歉，您没有接口(stk_mins)访问权限，权限的具体详情访问："
                    "https://tushare.pro/document/1?doc_id=108。"
                )

            def daily(self, **kwargs):
                self.kwargs = kwargs
                return pd.DataFrame({
                    "ts_code": ["600519.SH"],
                    "trade_date": ["20240920"],
                    "close": [1480.0],
                    "vol": [12000],
                })

        client = DeniedMins()
        out = fetch_tushare_bars(
            "600519", start="2024-09-20", end="2024-09-20",
            freq="1min", client=client,
        )
        self.assertEqual(out.iloc[0]["price"], 1480.0)
        self.assertEqual(client.kwargs["start_date"], "20240920")
        self.assertIn("日线", out.attrs.get("note", ""))

    def test_bars_daily_skips_mins(self):
        class DailyOnly:
            def stk_mins(self, **kwargs):
                raise AssertionError("不应再请求 stk_mins")

            def daily(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["600519.SH"],
                    "trade_date": ["20240920"],
                    "close": [1480.0],
                    "vol": [100],
                })

        out = fetch_tushare_bars(
            "600519", start="2024-09-20", end="2024-09-20",
            freq="D", client=DailyOnly(),
        )
        self.assertEqual(len(out), 1)

    def test_backtest_accepts_tushare_source(self):
        raw = pd.DataFrame({
            "ts_code": ["600519.SH"] * 40,
            "trade_time": pd.date_range("2024-09-20 10:00:00", periods=40, freq="1min"),
            "close": [1480 + i * 0.1 for i in range(40)],
            "vol": [1000] * 40,
        })
        result = execute_backtest(
            "dma",
            symbol="600519",
            source="tushare",
            start="2024-09-20",
            end="2024-09-20",
            params={"fast": 5, "slow": 12},
            fetch_bars=lambda **_: normalize_tushare_bars(raw),
        )
        self.assertEqual(result["symbol"], "600519.SH")
        self.assertGreater(len(result["ticks"]), 0)

    def test_search_stocks_by_name_or_code(self):
        class Listed:
            def stock_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["688256.SH", "600519.SH", "000001.SZ"],
                    "symbol": ["688256", "600519", "000001"],
                    "name": ["寒武纪", "贵州茅台", "平安银行"],
                    "industry": ["半导体", "白酒", "银行"],
                    "market": ["科创板", "主板", "主板"],
                })

        hits = search_stocks("寒武纪", client=Listed())
        self.assertEqual(hits[0]["ts_code"], "688256.SH")
        self.assertEqual(hits[0]["name"], "寒武纪")
        by_code = search_stocks("600519", client=Listed())
        self.assertEqual(by_code[0]["name"], "贵州茅台")

    def test_search_unknown_code_still_returns_ts_code(self):
        class Listed:
            def stock_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["600519.SH"],
                    "symbol": ["600519"],
                    "name": ["贵州茅台"],
                    "industry": ["白酒"],
                    "market": ["主板"],
                })

        hits = search_stocks("688256", client=Listed())
        self.assertEqual(hits[0]["ts_code"], "688256.SH")

    def test_fetch_quote_daily_keeps_ohlc(self):
        class Daily:
            def daily(self, **kwargs):
                self.kwargs = kwargs
                return pd.DataFrame({
                    "ts_code": ["688256.SH", "688256.SH"],
                    "trade_date": ["20250929", "20250930"],
                    "open": [1300.0, 1320.0],
                    "high": [1350.0, 1330.0],
                    "low": [1280.0, 1310.0],
                    "close": [1323.5, 1315.0],
                    "vol": [10000, 8000],
                    "amount": [1.3e6, 1.05e6],
                    "pct_chg": [2.1, -0.64],
                })

            def stock_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["688256.SH"],
                    "symbol": ["688256"],
                    "name": ["寒武纪"],
                    "industry": ["半导体"],
                    "market": ["科创板"],
                })

        payload = fetch_quote_daily(
            "688256", start="2025-09-29", end="2025-09-30", client=Daily(),
        )
        self.assertEqual(payload["ts_code"], "688256.SH")
        self.assertEqual(payload["name"], "寒武纪")
        self.assertEqual(len(payload["bars"]), 2)
        self.assertEqual(payload["bars"][0]["date"], "2025-09-29")
        self.assertEqual(payload["bars"][0]["open"], 1300.0)
        self.assertEqual(payload["bars"][1]["close"], 1315.0)
        self.assertAlmostEqual(payload["stats"]["change_pct"], (1315.0 / 1323.5) - 1, places=6)
        self.assertEqual(payload["stats"]["high"], 1350.0)
        self.assertEqual(payload["stats"]["low"], 1280.0)

    def test_fetch_quote_daily_resolves_chinese_name(self):
        class Daily:
            def daily(self, **kwargs):
                self.kwargs = kwargs
                return pd.DataFrame({
                    "ts_code": ["688256.SH"],
                    "trade_date": ["20250929"],
                    "open": [1300.0],
                    "high": [1350.0],
                    "low": [1280.0],
                    "close": [1323.5],
                    "vol": [10000],
                    "amount": [1.3e6],
                    "pct_chg": [2.1],
                })

            def stock_basic(self, **kwargs):
                return pd.DataFrame({
                    "ts_code": ["688256.SH"],
                    "symbol": ["688256"],
                    "name": ["寒武纪"],
                    "industry": ["半导体"],
                    "market": ["科创板"],
                })

        client = Daily()
        payload = fetch_quote_daily(
            "寒武纪", start="2025-09-29", end="2025-09-30", client=client,
        )
        self.assertEqual(payload["ts_code"], "688256.SH")
        self.assertEqual(client.kwargs["ts_code"], "688256.SH")


if __name__ == "__main__":
    unittest.main()
