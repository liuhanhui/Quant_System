"""数据层：加载 tick 数据。
支持三种来源：
1. CSV 文件（本地存储的分笔数据）
2. akshare 在线获取（需要网络环境，可选依赖）
3. 合成数据生成器（用于无数据环境下的演示与单元测试）

CSV 格式要求列：datetime, symbol, price, volume [, bid1, ask1]
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Tick:
    timestamp: pd.Timestamp
    symbol: str
    price: float
    volume: int
    bid1: float = 0.0
    ask1: float = 0.0


def load_csv(path: str, symbol: str = "") -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime"])
    if symbol:
        df = df[df["symbol"] == symbol]
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def fetch_akshare_ticks(symbol: str, trade_date: str) -> pd.DataFrame:
    """通过 akshare 获取个股历史分笔（tick）数据。
    注意：免费接口通常只提供近期数据且频率受限，研究用途建议购买
    交易所 Level-2 或数据商（tushare pro / 米筐 / 聚宽）授权数据。
    """
    try:
        import akshare as ak
    except ImportError:
        raise ImportError("请先安装 akshare：pip install akshare")
    df = ak.stock_zh_a_tick_tx_js(symbol=symbol)  # 腾讯分笔接口
    df = df.rename(columns={"成交时间": "datetime", "成交价格": "price",
                            "成交手数": "volume", "股票代码": "symbol"})
    df["datetime"] = pd.to_datetime(trade_date + " " + df["datetime"].astype(str))
    return df[["datetime", "symbol", "price", "volume"]]


def synthetic_gbm_ticks(
    symbol: str = "SIM000001",
    start: str = "2026-09-21",
    days: int = 5,
    s0: float = 10.0,
    mu: float = 0.15,          # 年化漂移
    sigma: float = 0.30,       # 年化波动
    tick_interval_sec: int = 3,
    seed: int = 42,
) -> pd.DataFrame:
    """生成几何布朗运动驱动的合成 tick 序列，模拟 A 股交易时段。"""
    rng = np.random.default_rng(seed)
    rows = []
    dt_year = tick_interval_sec / (252 * 4 * 3600)   # 每日按 4 交易小时折算
    sessions = [(10, 0, 11, 30), (13, 0, 15, 0)]     # 剔除集合竞价，便于演示
    price = s0
    for d in range(days):
        day = pd.Timestamp(start) + pd.Timedelta(days=d)
        while day.weekday() >= 5:                    # 跳过周末
            day += pd.Timedelta(days=1)
        for h0, m0, h1, m1 in sessions:
            t = day.replace(hour=h0, minute=m0, second=0)
            end = day.replace(hour=h1, minute=m1, second=0)
            while t < end:
                z = rng.standard_normal()
                price *= np.exp((mu - 0.5 * sigma**2) * dt_year + sigma * np.sqrt(dt_year) * z)
                price = round(price, 2)
                vol = int(rng.integers(1, 200))
                rows.append((t, symbol, price, vol))
                t += timedelta(seconds=tick_interval_sec)
    return pd.DataFrame(rows, columns=["datetime", "symbol", "price", "volume"])
