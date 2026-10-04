"""演示入口：合成 tick 数据 + 双均线/布林带策略 + 绩效报告。

用法：
    python main.py                    # 双均线演示
    python main.py --strategy boll    # 布林带演示
    python main.py --csv your_ticks.csv --symbol 600519   # 本地 CSV
    python main.py --source tushare --symbol 600519 --start 2024-09-01 --end 2025-09-26
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.runner import execute_backtest
from analysis.performance import performance_report, plot_results

STRATEGIES = ("dma", "boll")


def run(strategy_key: str, csv_path: str | None, symbol: str,
        source: str = "synthetic", start: str | None = None, end: str | None = None,
        freq: str = "1min"):
    if source == "synthetic" and not csv_path:
        print("[提示] 未提供 CSV / Tushare，使用合成数据演示。")
    result = execute_backtest(
        strategy_key, symbol=symbol, csv_path=csv_path,
        source=source, start=start, end=end, freq=freq,
    )

    report = performance_report(result["equity_curve"], result["fills"])
    print(f"\n===== 策略: {strategy_key} | 标的: {symbol} =====")
    for k, v in report.items():
        print(f"{k:>12}: {v}")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{strategy_key}_{symbol}_nav.png")
    plot_results(result["equity_curve"],
                 f"{strategy_key} on {symbol} (tick backtest)", out)
    print(f"净值图已保存: {out}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="dma", choices=list(STRATEGIES))
    ap.add_argument("--csv", default=None)
    ap.add_argument("--symbol", default="SIM000001")
    ap.add_argument("--source", default="synthetic", choices=("synthetic", "tushare"))
    ap.add_argument("--start", default=None, help="Tushare 开始日期 YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="Tushare 结束日期 YYYY-MM-DD")
    ap.add_argument("--freq", default="1min", help="Tushare 频度：1min/5min，或 D 日线")
    args = ap.parse_args()
    if args.csv:
        args.source = "synthetic"
    run(args.strategy, args.csv, args.symbol, args.source, args.start, args.end, args.freq)
