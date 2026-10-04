"""事件与订单定义。"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd


class Direction(Enum):
    BUY = 1
    SELL = -1


@dataclass
class Order:
    """市价单：以发出后下一 tick 价格 ±滑点 成交（回测近似）。"""
    timestamp: pd.Timestamp
    symbol: str
    direction: Direction
    volume: int                 # 股数，必须为 100 的整数倍
    reason: str = ""


@dataclass
class Fill:
    timestamp: pd.Timestamp
    symbol: str
    direction: Direction
    volume: int
    price: float
    commission: float           # 佣金 + 印花税 + 过户费合计
