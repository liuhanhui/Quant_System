"""策略基类。"""
from __future__ import annotations
from dataclasses import dataclass
from engine.event import Direction, Order


@dataclass
class Signal:
    direction: Direction
    volume: int
    reason: str = ""


class StrategyBase:
    """所有策略需实现 on_tick(tick_row, context) -> Signal | None。
    context 提供 cash / position(symbol) / sellable(symbol)。
    """
    def on_tick(self, tick_row, context) -> Signal | None:
        raise NotImplementedError

    @staticmethod
    def full_position(context, price: float, fee_rate: float = 0.001) -> int:
        """按可用资金满仓估算整手股数。"""
        vol = int(context.cash * (1 - fee_rate) // (price * 100)) * 100
        return max(vol, 0)
