"""布林带均值回归策略（tick 滚动窗口版）。
价格触及下轨且空仓 -> 买入；触及上轨且持仓 -> 卖出。
"""
from __future__ import annotations
from collections import deque
import math
from .base import StrategyBase, Signal
from engine.event import Direction


class BollingerStrategy(StrategyBase):
    def __init__(self, window: int = 200, num_std: float = 2.0):
        self.window, self.num_std = window, num_std
        self.prices: deque[float] = deque(maxlen=window)

    def on_tick(self, tick_row, context) -> Signal | None:
        price = float(tick_row["price"])
        self.prices.append(price)
        if len(self.prices) < self.window:
            return None
        p = list(self.prices)
        mean = sum(p) / self.window
        std = math.sqrt(sum((x - mean) ** 2 for x in p) / self.window)
        upper, lower = mean + self.num_std * std, mean - self.num_std * std
        pos, sellable = context.position(tick_row["symbol"]), context.sellable(tick_row["symbol"])
        if price <= lower and pos == 0:
            vol = self.full_position(context, price)
            if vol > 0:
                return Signal(Direction.BUY, vol, "触及下轨")
        if price >= upper and sellable > 0:
            return Signal(Direction.SELL, sellable, "触及上轨")
        return None
