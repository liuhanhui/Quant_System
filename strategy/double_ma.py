"""双均线策略（tick 滚动窗口版）。
经典均线系统的 tick 级近似：用最近 fast/slow 个 tick 的成交均价做快/慢线，
金叉买入、死叉卖出。窗口单位是 tick 数而非时间——tick 密度高的
时段均线反应更快，这是 tick 级策略的固有特征。
"""
from __future__ import annotations
from collections import deque
from .base import StrategyBase, Signal
from engine.event import Direction


class DoubleMATickStrategy(StrategyBase):
    def __init__(self, fast: int = 30, slow: int = 150):
        assert fast < slow
        self.fast, self.slow = fast, slow
        self.prices: deque[float] = deque(maxlen=slow)
        self.prev_fast = self.prev_slow = None

    def _mas(self):
        p = list(self.prices)
        return sum(p[-self.fast:]) / self.fast, sum(p) / self.slow

    def on_tick(self, tick_row, context) -> Signal | None:
        self.prices.append(float(tick_row["price"]))
        if len(self.prices) < self.slow:
            return None
        fast_ma, slow_ma = self._mas()
        signal = None
        if self.prev_fast is not None:
            golden = self.prev_fast <= self.prev_slow and fast_ma > slow_ma
            death = self.prev_fast >= self.prev_slow and fast_ma < slow_ma
            pos = context.position(tick_row["symbol"])
            if golden and pos == 0:
                vol = self.full_position(context, float(tick_row["price"]))
                if vol > 0:
                    signal = Signal(Direction.BUY, vol, "金叉")
            elif death and context.sellable(tick_row["symbol"]) > 0:
                signal = Signal(Direction.SELL, context.sellable(tick_row["symbol"]), "死叉")
        self.prev_fast, self.prev_slow = fast_ma, slow_ma
        return signal
