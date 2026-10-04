# A 股 Tick 级量化回测系统

面向**研究用途**的事件驱动回测框架，A 股规则已内置：T+1、整手（100 股）、
涨跌停、佣金/印花税/过户费、滑点。

## 目录结构
```
quant_system/
├── data/loader.py          数据层：CSV / akshare(可选) / 合成数据
├── data/tushare_source.py  Tushare Pro 分钟线适配
├── engine/event.py         订单与成交定义
├── engine/broker.py        模拟券商：撮合、A股规则、费用
├── engine/backtest.py      事件驱动回测引擎
├── strategy/base.py        策略基类与信号
├── strategy/double_ma.py   双均线（tick滚动窗口）
├── strategy/bollinger.py   布林带均值回归
├── analysis/performance.py 绩效指标与净值/回撤图
├── engine/runner.py        CLI / 看板共用回测编排
├── web/app.py              网页看板
├── main.py                 命令行演示入口
└── results/                输出
```

## 快速开始
```bash
pip install -r requirements.txt
python main.py                 # 合成数据 + 双均线
python main.py --strategy boll # 布林带
python web/app.py              # 网页看板 http://127.0.0.1:8765
```

打开浏览器访问 `http://127.0.0.1:8765/`：左侧改策略/参数，右侧看指标、净值、回撤和成交明细。不上传 CSV 时用合成行情，页面加载后会自动跑一笔双均线演示。

## 接入 Tushare Pro（日线 / 分钟线）
Tushare Pro **没有历史逐笔**。默认用 `daily` 日线收盘价；若账号有 `stk_mins` 权限可选分钟线，没有权限时会自动降级到日线。

1. 复制 `.env.example` 为 `.env`，写入 `TUSHARE_TOKEN=你的token`
2. 运行（日线，普通 Pro 即可）：

```bash
python main.py --source tushare --symbol 600519 --start 2024-09-01 --end 2025-09-26
```

分钟线需单独开通 [权限](https://tushare.pro/document/1?doc_id=108)。`--freq 1min` 若报没权限，系统会改用日线。

## 接入真实 tick 数据
CSV 需包含列：`datetime, symbol, price, volume`（可扩展 bid1/ask1）。
分笔数据获取途径：
- Tushare Pro `stk_mins`：历史分钟线（本系统已接）
- `data.loader.fetch_akshare_ticks()`：腾讯接口，仅近期数据，限频
- 交易所 Level-2 / 米筐 / 聚宽 / Wind：商用级历史分笔

加载示例：
```python
from data.loader import load_csv
df = load_csv("ticks_600519.csv", symbol="600519")
```

## 编写自己的策略
继承 `StrategyBase`，实现 `on_tick(tick_row, context)` 返回 `Signal` 或 `None`。
context 提供：`cash`、`position(symbol)`、`sellable(symbol)`。
信号以**下一 tick 价格±滑点**成交（市价单近似）。

## 已知简化与局限（重要）
1. **成交价近似**：真实盘口需 bid1/ask1 撮合与队列位置模型，本框架用滑点近似
2. **信号延迟一拍**：有意为之，避免未来函数
3. **涨停买不进/跌停卖不出**：用当日首 tick 价 ±limit_pct 近似判断
4. **未建模**：集合竞价、部分成交、分红送转、停牌
5. 回测业绩高度依赖滑点/手续费假设，实盘前务必做参数敏感性分析

## 下一步路线
1. 接入真实 tick 数据，对比合成数据结论
2. 增加交易成本敏感性分析（滑点 ×2 / ×5）
3. 引入 walk-forward 样本外验证
4. 多标的并行回测 + 向量化加速（numpy/polars）
