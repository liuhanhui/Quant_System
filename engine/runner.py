"""回测编排：CLI 与网页看板共用。"""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd

from data.loader import load_csv, synthetic_gbm_ticks
from data.tushare_source import fetch_tushare_bars, to_ts_code
from engine.broker import Broker
from engine.backtest import BacktestEngine
from strategy.double_ma import DoubleMATickStrategy
from strategy.bollinger import BollingerStrategy
from analysis.performance import performance_report

STRATEGY_META = [
    {
        "key": "dma",
        "name": "双均线",
        "desc": "快慢均线金叉买入、死叉卖出",
        "params": [
            {"name": "fast", "label": "快线窗口", "default": 30, "min": 2, "max": 500, "step": 1},
            {"name": "slow", "label": "慢线窗口", "default": 150, "min": 5, "max": 2000, "step": 1},
        ],
    },
    {
        "key": "boll",
        "name": "布林带",
        "desc": "触及下轨买入、触及上轨卖出",
        "params": [
            {"name": "window", "label": "窗口", "default": 200, "min": 10, "max": 2000, "step": 1},
            {"name": "num_std", "label": "标准差倍数", "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1},
        ],
    },
]


def list_strategies() -> list[dict[str, Any]]:
    return STRATEGY_META


def _build_strategy(key: str, params: dict | None):
    p = params or {}
    if key == "dma":
        return DoubleMATickStrategy(fast=int(p.get("fast", 30)), slow=int(p.get("slow", 150)))
    if key == "boll":
        return BollingerStrategy(window=int(p.get("window", 200)),
                                 num_std=float(p.get("num_std", 2.0)))
    raise ValueError(f"未知策略: {key}")


def execute_backtest(
    strategy_key: str,
    *,
    symbol: str = "SIM000001",
    cash: float = 1_000_000,
    csv_path: str | None = None,
    ticks: pd.DataFrame | None = None,
    days: int = 5,
    seed: int = 42,
    params: dict | None = None,
    slippage: float = 0.0002,
    source: str = "synthetic",
    start: str | None = None,
    end: str | None = None,
    freq: str = "1min",
    token: str | None = None,
    fetch_bars=None,
) -> dict[str, Any]:
    """跑完回测，返回引擎原始结果 + 元数据。"""
    strategy = _build_strategy(strategy_key, params)
    if ticks is not None:
        df = ticks.copy()
    elif csv_path:
        df = load_csv(csv_path, symbol=symbol)
    elif source == "tushare":
        if not start or not end:
            raise ValueError("Tushare 回测需要提供 start / end")
        symbol = to_ts_code(symbol)
        pull = fetch_bars or fetch_tushare_bars
        df = pull(symbol=symbol, start=start, end=end, freq=freq, token=token)
    else:
        df = synthetic_gbm_ticks(symbol=symbol, days=int(days), seed=int(seed))
    if df.empty:
        raise ValueError("没有可用的 tick 数据")

    broker = Broker(cash=float(cash), slippage=float(slippage))
    engine = BacktestEngine(df, broker, strategy, symbol)
    result = engine.run()
    result["strategy"] = strategy_key
    result["symbol"] = symbol
    result["cash"] = float(cash)
    result["ticks"] = df
    result["params"] = params or {}
    result["data_note"] = getattr(df, "attrs", {}).get("note", "")
    result["data_freq"] = getattr(df, "attrs", {}).get("freq", "")
    return result


def _direction_name(value) -> str:
    return value.name if hasattr(value, "name") else str(value)


def _downsample(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    n = len(df)
    if n <= max_points:
        return df
    idx = np.unique(np.linspace(0, n - 1, max_points).astype(int))
    return df.iloc[idx]


def _raw_metrics(equity_curve: pd.DataFrame, fills: pd.DataFrame) -> dict[str, Any]:
    nav = equity_curve.set_index("datetime")["equity"]
    total_ret = float(nav.iloc[-1] / nav.iloc[0] - 1) if len(nav) else 0.0
    cummax = nav.cummax()
    dd = nav / cummax - 1
    n_trades = 0 if fills is None or fills.empty else len(fills) // 2
    win_rate = None
    if n_trades > 0 and "direction" in fills.columns:
        buys = fills[fills["direction"].apply(lambda d: _direction_name(d) == "BUY")]
        sells = fills[fills["direction"].apply(lambda d: _direction_name(d) == "SELL")]
        m = min(len(buys), len(sells))
        if m > 0:
            pnl = sells["price"].iloc[:m].values - buys["price"].iloc[:m].values
            win_rate = float((pnl > 0).mean())
    return {
        "total_return": total_ret,
        "max_drawdown": float(dd.min()) if len(dd) else 0.0,
        "final_equity": float(nav.iloc[-1]) if len(nav) else 0.0,
        "n_trades": n_trades,
        "win_rate": win_rate,
    }


def dashboard_payload(raw: dict[str, Any], max_points: int = 800) -> dict[str, Any]:
    """把回测结果压成前端可直接渲染的 JSON。"""
    curve = raw["equity_curve"].copy()
    ticks = raw["ticks"][["datetime", "price"]].copy()
    curve = curve.merge(ticks, on="datetime", how="left")
    nav = curve["equity"]
    curve["drawdown"] = nav / nav.cummax() - 1
    sampled = _downsample(curve, max_points)

    fills = raw["fills"]
    fill_rows = []
    if fills is not None and not fills.empty:
        for rec in fills.to_dict(orient="records"):
            fill_rows.append({
                "timestamp": pd.Timestamp(rec["timestamp"]).isoformat(),
                "symbol": rec["symbol"],
                "direction": _direction_name(rec["direction"]),
                "volume": int(rec["volume"]),
                "price": float(rec["price"]),
                "commission": float(rec["commission"]),
            })

    report = performance_report(raw["equity_curve"], fills if fills is not None else pd.DataFrame())
    return {
        "strategy": raw["strategy"],
        "symbol": raw["symbol"],
        "cash": raw["cash"],
        "params": raw.get("params") or {},
        "tick_count": int(len(raw["ticks"])),
        "report": report,
        "metrics": _raw_metrics(raw["equity_curve"], fills),
        "equity": [
            {
                "t": pd.Timestamp(row.datetime).isoformat(),
                "equity": float(row.equity),
                "drawdown": float(row.drawdown),
                "price": float(row.price) if pd.notna(row.price) else None,
            }
            for row in sampled.itertuples(index=False)
        ],
        "fills": fill_rows,
        "data_note": raw.get("data_note") or "",
        "data_freq": raw.get("data_freq") or "",
    }
