"""事件驱动回测引擎：逐 tick 推进。

流程：每个 tick -> 记录当日开盘价 -> 撮合上一信号产生的挂单
      -> 策略 on_tick 产生新信号 -> 记净值
A 股无做空（研究简化），信号为开仓/平仓（全进全出）。
"""
from __future__ import annotations
import pandas as pd
from .broker import Broker
from .event import Direction, Order


class Context:
    """暴露给策略的只读上下文。"""
    def __init__(self, broker: Broker):
        self.broker = broker

    @property
    def cash(self) -> float:
        return self.broker.cash

    def position(self, symbol: str) -> int:
        pos = self.broker.positions.get(symbol)
        return pos.total if pos else 0

    def sellable(self, symbol: str) -> int:
        pos = self.broker.positions.get(symbol)
        return pos.sellable if pos else 0


class BacktestEngine:
    def __init__(self, ticks: pd.DataFrame, broker: Broker, strategy, symbol: str):
        self.df = ticks.sort_values("datetime").reset_index(drop=True)
        self.broker = broker
        self.strategy = strategy
        self.symbol = symbol
        self.context = Context(broker)
        self.pending: Order | None = None
        self.equity_curve: list[tuple[pd.Timestamp, float]] = []

    def run(self) -> dict:
        current_date, day_open = None, None
        for _, row in self.df.iterrows():
            ts = row["datetime"]
            date = ts.normalize()
            if date != current_date:            # 日切：T+1 解锁 + 记录开盘价
                current_date = date
                day_open = float(row["price"])
                self.broker.on_new_day(date, {self.symbol: day_open})

            price = float(row["price"])
            if self.pending is not None:        # 上一信号在下一 tick 成交
                self.broker.execute(self.pending, price)
                self.pending = None

            signal = self.strategy.on_tick(row, self.context)
            if signal is not None:
                self.pending = Order(ts, self.symbol, signal.direction,
                                     signal.volume, signal.reason)

            eq = self.broker.equity({self.symbol: price})
            self.equity_curve.append((ts, eq))

        # 期末强平（估值用）
        final_price = float(self.df.iloc[-1]["price"])
        pos = self.broker.positions.get(self.symbol)
        if pos and pos.total > 0:
            self.broker.cash += pos.total * final_price
            pos.total = 0
        final_eq = self.broker.equity({self.symbol: final_price})

        curve = pd.DataFrame(self.equity_curve, columns=["datetime", "equity"])
        return {
            "equity_curve": curve,
            "final_equity": final_eq,
            "fills": pd.DataFrame([f.__dict__ for f in self.broker.fills]),
        }
