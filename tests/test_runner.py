"""回测服务：看板 API 所需的可序列化结果。"""
from __future__ import annotations
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
from engine.runner import dashboard_payload, execute_backtest, list_strategies


def _tiny_ticks(symbol="SIM000001", n=80, start_price=10.0):
    ts = pd.date_range("2026-09-21 10:00:00", periods=n, freq="3s")
    prices = [round(start_price + i * 0.01, 2) for i in range(n)]
    return pd.DataFrame({
        "datetime": ts,
        "symbol": symbol,
        "price": prices,
        "volume": [100] * n,
    })


class RunnerTests(unittest.TestCase):
    def test_list_strategies_has_dma_and_boll(self):
        keys = {s["key"] for s in list_strategies()}
        self.assertEqual(keys, {"dma", "boll"})

    def test_execute_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            execute_backtest("nope", ticks=_tiny_ticks())

    def test_dashboard_payload_is_json_serializable(self):
        raw = execute_backtest("dma", ticks=_tiny_ticks(), cash=1_000_000,
                               params={"fast": 5, "slow": 12})
        payload = dashboard_payload(raw, max_points=20)
        dumped = json.dumps(payload)
        self.assertIn("report", dumped)
        self.assertIn("equity", dumped)
        self.assertIn("fills", dumped)
        self.assertGreater(payload["tick_count"], 0)
        self.assertEqual(payload["strategy"], "dma")
        self.assertIn("总收益率", payload["report"])
        self.assertIn("total_return", payload["metrics"])
        self.assertLessEqual(len(payload["equity"]), 20)
        for pt in payload["equity"]:
            self.assertIn("t", pt)
            self.assertIn("equity", pt)
            self.assertIn("drawdown", pt)
            self.assertIn("price", pt)
        for fill in payload["fills"]:
            self.assertIn(fill["direction"], ("BUY", "SELL"))


if __name__ == "__main__":
    unittest.main()
