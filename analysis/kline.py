"""A 股日 K：涨红跌绿 + 成交量。"""
from __future__ import annotations
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Segoe UI"]
plt.rcParams["axes.unicode_minus"] = False


def plot_daily_kline(csv_path: str, title: str, save_path: str) -> None:
    df = pd.read_csv(csv_path)
    df["dt"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    df = df.sort_values("dt").reset_index(drop=True)
    x = mdates.date2num(df["dt"])
    width = 0.6

    fig, axes = plt.subplots(
        2, 1, figsize=(13, 7.2), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    ax, axv = axes
    for i, row in df.iterrows():
        up = row["close"] >= row["open"]
        color = "#dc2626" if up else "#16a34a"
        ax.vlines(x[i], row["low"], row["high"], color=color, lw=0.8)
        body_low = min(row["open"], row["close"])
        body_h = max(abs(row["close"] - row["open"]), 1.5)
        ax.add_patch(Rectangle(
            (x[i] - width / 2, body_low), width, body_h,
            facecolor=color, edgecolor=color, lw=0.4,
        ))
        axv.bar(x[i], row["vol"] / 10000, width=width, color=color, alpha=0.85)

    ax.set_title(title)
    ax.set_ylabel("价格（元）")
    ax.grid(alpha=0.25)
    axv.set_ylabel("成交量（万手）")
    axv.grid(alpha=0.25)
    axv.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axv.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(save_path, dpi=140)
    plt.close()


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv = os.path.join(root, "results", "688256_1y_daily.csv")
    out = os.path.join(root, "results", "688256_1y_kline.png")
    plot_daily_kline(csv, "寒武纪 688256.SH 近一年日K（Tushare 未复权）", out)
    print(out)
