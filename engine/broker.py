"""模拟券商：撮合、费用、A 股交易规则。
- T+1：当日买入次一交易日方可卖出
- 整手：100 股整数倍
- 费用：佣金(万2.5, 最低5元, 双向) + 印花税(万5, 仅卖出, 2023-08-28 起)
        + 过户费(十万分之一, 双向, 沪市)
- 涨跌停：主板 ±10%（ST ±5%、科创/创业 ±20% 可通过 limit_pct 配置）
"""
from __future__ import annotations
import pandas as pd
from .event import Direction, Order, Fill


class Position:
    __slots__ = ("total", "today_buy", "batches")

    def __init__(self):
        self.total = 0          # 总持仓
        self.today_buy = 0      # 当日买入（T+1 锁定）
        self.batches = []       # [(trade_date, volume)] 先进先出

    @property
    def sellable(self) -> int:
        return self.total - self.today_buy


class Broker:
    def __init__(self, cash: float,
                 commission: float = 0.00025,
                 min_commission: float = 5.0,
                 stamp_tax: float = 0.0005,
                 transfer_fee: float = 0.00001,
                 slippage: float = 0.0002,
                 limit_pct: float = 0.10):
        self.cash = cash
        self.commission = commission
        self.min_commission = min_commission
        self.stamp_tax = stamp_tax
        self.transfer_fee = transfer_fee
        self.slippage = slippage
        self.limit_pct = limit_pct
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self._current_date = None
        self._day_open: dict[str, float] = {}

    # ---------------- 日切处理 ----------------
    def on_new_day(self, date, symbols_open: dict[str, float]):
        self._current_date = date
        for pos in self.positions.values():     # T+1 解锁
            pos.today_buy = 0
        self._day_open = symbols_open.copy()

    # ---------------- 费用 ----------------
    def _fees(self, amount: float, direction: Direction) -> float:
        c = max(amount * self.commission, self.min_commission)
        tax = amount * self.stamp_tax if direction == Direction.SELL else 0.0
        return c + tax + amount * self.transfer_fee

    # ---------------- 涨跌停判断 ----------------
    def _limit_blocked(self, symbol: str, price: float, direction: Direction) -> bool:
        open_p = self._day_open.get(symbol)
        if not open_p:
            return False
        up, dn = open_p * (1 + self.limit_pct), open_p * (1 - self.limit_pct)
        if direction == Direction.BUY and price >= up - 1e-9:
            return True                     # 涨停无法买入
        if direction == Direction.SELL and price <= dn + 1e-9:
            return True                     # 跌停无法卖出
        return False

    # ---------------- 撮合 ----------------
    def execute(self, order: Order, tick_price: float) -> Fill | None:
        if order.volume % 100 != 0 or order.volume <= 0:
            return None                     # 整手校验
        if self._limit_blocked(order.symbol, tick_price, order.direction):
            return None

        slip = self.slippage if order.direction == Direction.BUY else -self.slippage
        fill_price = round(tick_price * (1 + slip), 2)
        amount = fill_price * order.volume

        pos = self.positions.setdefault(order.symbol, Position())
        if order.direction == Direction.BUY:
            fee = self._fees(amount, Direction.BUY)
            if self.cash < amount + fee:    # 资金不足则放弃（也可改为部分成交）
                return None
            self.cash -= amount + fee
            pos.total += order.volume
            pos.today_buy += order.volume
            pos.batches.append((self._current_date, order.volume))
        else:
            if pos.sellable < order.volume:
                return None                 # T+1 或持仓不足
            fee = self._fees(amount, Direction.SELL)
            self.cash += amount - fee
            pos.total -= order.volume
            remaining = order.volume        # 先进先出扣减批次
            while remaining > 0:
                d, v = pos.batches[0]
                take = min(v, remaining)
                pos.batches[0] = (d, v - take)
                if pos.batches[0][1] == 0:
                    pos.batches.pop(0)
                remaining -= take

        fill = Fill(order.timestamp, order.symbol, order.direction,
                    order.volume, fill_price, fee)
        self.fills.append(fill)
        return fill

    # ---------------- 账户估值 ----------------
    def market_value(self, prices: dict[str, float]) -> float:
        return sum(pos.total * prices.get(sym, 0.0) for sym, pos in self.positions.items())

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + self.market_value(prices)
