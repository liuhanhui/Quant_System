"""绩效分析：净值曲线 -> 指标 + 图表。"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def max_drawdown(nav: pd.Series) -> tuple[float, pd.Timestamp, pd.Timestamp]:
    cummax = nav.cummax()
    dd = nav / cummax - 1
    trough = dd.idxmin()
    peak = nav.loc[:trough].idxmax()
    return float(dd.min()), peak, trough


def performance_report(equity_curve: pd.DataFrame, fills: pd.DataFrame,
                       periods_per_year: float = 252 * 4 * 900) -> dict:
    """periods_per_year 按 tick 频率折算（演示：每日 4h、每 3s 一个 tick）。"""
    nav = equity_curve.set_index("datetime")["equity"]
    ret = nav.pct_change().dropna()
    total_ret = nav.iloc[-1] / nav.iloc[0] - 1
    ann_ret = (1 + total_ret) ** (periods_per_year / len(ret)) - 1 if len(ret) > 0 else 0.0
    ann_vol = ret.std() * np.sqrt(periods_per_year) if len(ret) > 1 else 0.0
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    mdd, peak, trough = max_drawdown(nav)
    n_trades = len(fills) // 2          # 买入+卖出记为一次完整交易
    win_rate = np.nan
    if n_trades > 0:
        buys = fills[fills["direction"].apply(lambda d: d.name == "BUY")].reset_index(drop=True)
        sells = fills[fills["direction"].apply(lambda d: d.name == "SELL")].reset_index(drop=True)
        m = min(len(buys), len(sells))
        if m > 0:
            pnl = sells["price"].iloc[:m].values - buys["price"].iloc[:m].values
            win_rate = float((pnl > 0).mean())
    return {
        "总收益率": f"{total_ret:.2%}",
        "年化收益率": f"{ann_ret:.2%}",
        "年化波动率": f"{ann_vol:.2%}",
        "夏普比率": f"{sharpe:.2f}",
        "最大回撤": f"{mdd:.2%}",
        "回撤区间": f"{peak.date()} ~ {trough.date()}",
        "交易次数(完整)": n_trades,
        "胜率": f"{win_rate:.2%}" if not np.isnan(win_rate) else "N/A",
        "期末净值": f"{nav.iloc[-1]:,.2f}",
    }


def plot_results(equity_curve: pd.DataFrame, title: str, save_path: str):
    nav = equity_curve.set_index("datetime")["equity"]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]})
    axes[0].plot(nav.index, nav.values, lw=1, color="#2563eb")
    axes[0].set_title(title)
    axes[0].set_ylabel("Equity")
    axes[0].grid(alpha=0.3)
    dd = nav / nav.cummax() - 1
    axes[1].fill_between(dd.index, dd.values, 0, color="#dc2626", alpha=0.5)
    axes[1].set_ylabel("Drawdown")
    axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.close()
