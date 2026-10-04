"""Tushare Pro 行情适配。

Pro 没有历史逐笔。优先 stk_mins 分钟线；没有权限时自动降级到 daily 日线。
映射成本框架的 datetime/symbol/price/volume。
Token 只从参数、环境变量 TUSHARE_TOKEN、或项目根目录 .env 读取。
"""
from __future__ import annotations
import json
import os
import time
from datetime import datetime, timedelta

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "cache", "tushare")


def to_ts_code(symbol: str) -> str:
    code = str(symbol).strip().upper()
    if not code:
        raise ValueError("股票代码为空")
    if "." in code:
        num, exch = code.split(".", 1)
        return f"{num}.{exch}"
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    raise ValueError(f"无法识别交易所: {symbol}")


def _read_project_env_token() -> str:
    path = os.path.join(ROOT, ".env")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            if key.strip() == "TUSHARE_TOKEN":
                return val.strip().strip('"').strip("'")
    return ""


def resolve_token(explicit: str | None = None) -> str:
    token = (explicit or "").strip() or os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        token = _read_project_env_token()
    return token


def _start_ts(value: str) -> str:
    text = str(value).strip()
    if len(text) <= 10:
        return f"{text} 09:00:00"
    return text


def _end_ts(value: str) -> str:
    text = str(value).strip()
    if len(text) <= 10:
        return f"{text} 19:00:00"
    return text


def _ymd(value: str) -> str:
    return str(value).strip().replace("-", "")[:8]


def _is_daily_freq(freq: str) -> bool:
    return str(freq or "").upper() in {"D", "DAY", "DAILY"}


def _permission_denied(exc: BaseException) -> bool:
    text = str(exc)
    return "没有接口" in text or "访问权限" in text or ("权限" in text and "频次" not in text)


def _rate_limited(exc: BaseException) -> bool:
    text = str(exc)
    return "频率" in text or "频次" in text


def _cache_path(ts_code: str, freq: str, start: str, end: str) -> str:
    name = f"{ts_code}_{freq}_{_ymd(start)}_{_ymd(end)}.csv"
    return os.path.join(CACHE_DIR, name)


def _read_cache(ts_code: str, freq: str, start: str, end: str) -> pd.DataFrame | None:
    path = _cache_path(ts_code, freq, start, end)
    if not os.path.isfile(path):
        return None
    out = pd.read_csv(path, parse_dates=["datetime"])
    if out.empty:
        return None
    out.attrs["freq"] = freq
    out.attrs["note"] = f"Tushare {freq} 本地缓存"
    return out


def _quota_path() -> str:
    return os.path.join(CACHE_DIR, "_stk_mins_quota.json")


def _quota_window_sec(exc: BaseException | None = None) -> int:
    text = str(exc) if exc else ""
    if "天" in text:
        return 24 * 3600
    if "小时" in text:
        return 3600
    try:
        with open(_quota_path(), encoding="utf-8") as fh:
            return int(json.load(fh).get("window", 3600))
    except Exception:
        return 3600


def _quota_remaining_sec() -> int:
    path = _quota_path()
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        last = float(data.get("t", 0))
        window = int(data.get("window", 3600))
    except Exception:
        return 0
    # 按天限频：Tushare 是自然日重置，不是滚动 24 小时
    if window >= 20 * 3600:
        last_day = datetime.fromtimestamp(last).date()
        now = datetime.now()
        if now.date() > last_day:
            return 0
        nxt = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        return max(int((nxt - now).total_seconds()), 0)
    return max(int(window - (time.time() - last)), 0)


def _mark_quota(window: int = 3600) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_quota_path(), "w", encoding="utf-8") as fh:
        json.dump({"t": time.time(), "window": int(window)}, fh)


def _write_cache(ts_code: str, freq: str, start: str, end: str, df: pd.DataFrame) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_csv(_cache_path(ts_code, freq, start, end), index=False)


def _read_any_cache(ts_code: str, freq: str, start: str, end: str) -> pd.DataFrame | None:
    exact = _read_cache(ts_code, freq, start, end)
    if exact is not None:
        return exact
    if not os.path.isdir(CACHE_DIR):
        return None
    prefix = f"{ts_code}_{freq}_"
    hits = []
    for name in os.listdir(CACHE_DIR):
        if name.startswith(prefix) and name.endswith(".csv"):
            path = os.path.join(CACHE_DIR, name)
            try:
                df = pd.read_csv(path, parse_dates=["datetime"])
            except Exception:
                continue
            if df.empty:
                continue
            hits.append((os.path.getmtime(path), df, name))
    if not hits:
        return None
    hits.sort(key=lambda x: x[0], reverse=True)
    out = hits[0][1]
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    sliced = out[(out["datetime"] >= lo) & (out["datetime"] < hi)]
    if not sliced.empty:
        out = sliced.reset_index(drop=True)
    out.attrs["freq"] = freq
    out.attrs["note"] = f"Tushare {freq} 本地缓存（限频复用）"
    return out


def normalize_tushare_bars(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["datetime", "symbol", "price", "volume"])
    df = raw.copy()
    if "trade_time" in df.columns:
        time_col = "trade_time"
    elif "trade_date" in df.columns:
        time_col = "trade_date"
    else:
        time_col = "datetime"
    price_col = "close" if "close" in df.columns else "price"
    vol_col = "vol" if "vol" in df.columns else "volume"
    sym_col = "ts_code" if "ts_code" in df.columns else "symbol"
    out = pd.DataFrame({
        "datetime": pd.to_datetime(df[time_col]),
        "symbol": df[sym_col].astype(str),
        "price": pd.to_numeric(df[price_col], errors="coerce"),
        "volume": pd.to_numeric(df[vol_col], errors="coerce").fillna(0).astype(int),
    })
    out = out.dropna(subset=["datetime", "price"])
    return out.sort_values("datetime").reset_index(drop=True)


def _make_client(token: str):
    try:
        import tushare as ts
    except ImportError as exc:
        raise ImportError("请先安装 tushare：pip install tushare") from exc
    return ts.pro_api(token)


def fetch_tushare_mins(
    symbol: str,
    start: str,
    end: str,
    freq: str = "1min",
    token: str | None = None,
    client=None,
) -> pd.DataFrame:
    ts_code = to_ts_code(symbol)
    freq = freq or "1min"
    live = client is None
    cached = _read_any_cache(ts_code, freq, start, end)
    if live and cached is not None and _read_cache(ts_code, freq, start, end) is not None:
        return cached
    if live:
        wait = _quota_remaining_sec()
        if wait > 0:
            if cached is not None:
                cached.attrs["note"] = f"Tushare {freq} 本地缓存（额度冷却中，约 {wait // 60 + 1} 分钟后可再拉）"
                return cached
            hours, mins = wait // 3600, (wait % 3600) // 60
            raise ValueError(
                f"Tushare 分钟线额度冷却中，大约 {hours} 小时 {mins} 分钟后才能再请求。"
                "成功拉过的区间会进本地缓存，之后可离线回测。"
            )
        resolved = resolve_token(token)
        if not resolved:
            raise ValueError("未配置 TUSHARE_TOKEN。请在项目根目录 .env 写入 TUSHARE_TOKEN=你的token")
        client = _make_client(resolved)

    try:
        raw = client.stk_mins(
            ts_code=ts_code,
            freq=freq,
            start_date=_start_ts(start),
            end_date=_end_ts(end),
        )
        if live:
            _mark_quota(3600)
    except Exception as exc:
        if _rate_limited(exc):
            if live:
                _mark_quota(_quota_window_sec(exc))
            cached = _read_any_cache(ts_code, freq, start, end)
            if cached is not None:
                return cached
            raise ValueError(
                f"Tushare 分钟线额度用完（{exc}）。"
                "本地还没有这段缓存。额度恢复后再拉一次，成功后可离线回测。"
            ) from exc
        raise
    out = normalize_tushare_bars(raw)
    if out.empty:
        raise ValueError(
            f"Tushare 未返回 {ts_code} {freq} 数据。"
            "请确认分钟线权限、代码和日期区间（end 当天需带 19:00:00 才会包含当日）。"
        )
    out.attrs["freq"] = freq
    out.attrs["note"] = f"Tushare 分钟线 {freq}（收盘价）"
    if live:
        _write_cache(ts_code, freq, start, end, out)
    return out


def fetch_tushare_daily(
    symbol: str,
    start: str,
    end: str,
    token: str | None = None,
    client=None,
) -> pd.DataFrame:
    ts_code = to_ts_code(symbol)
    if client is None:
        resolved = resolve_token(token)
        if not resolved:
            raise ValueError("未配置 TUSHARE_TOKEN。请在项目根目录 .env 写入 TUSHARE_TOKEN=你的token")
        client = _make_client(resolved)
    try:
        raw = client.daily(ts_code=ts_code, start_date=_ymd(start), end_date=_ymd(end))
    except Exception as exc:
        if _permission_denied(exc):
            raise ValueError(
                "当前 Tushare token 没有日线 daily 权限。"
                "请到 https://tushare.pro/document/1?doc_id=108 查看积分；日线通常需要约 120 积分。"
            ) from exc
        raise
    out = normalize_tushare_bars(raw)
    if out.empty:
        raise ValueError(f"Tushare 未返回 {ts_code} 日线，请检查代码和日期。")
    out.attrs["freq"] = "D"
    out.attrs["note"] = "Tushare 日线（收盘价）"
    return out


def fetch_tushare_bars(
    symbol: str,
    start: str,
    end: str,
    freq: str = "1min",
    token: str | None = None,
    client=None,
) -> pd.DataFrame:
    """按权限取数：分钟走 stk_mins，日线走 daily；一边没权限则试另一边。"""
    freq = freq or "1min"
    if _is_daily_freq(freq):
        try:
            return fetch_tushare_daily(symbol, start, end, token=token, client=client)
        except Exception as exc:
            if not _permission_denied(exc):
                raise
            mins = fetch_tushare_mins(symbol, start, end, freq="1min", token=token, client=client)
            mins.attrs["note"] = "无 daily 权限，已自动改用 1 分钟线（收盘价）"
            return mins
    try:
        return fetch_tushare_mins(symbol, start, end, freq=freq, token=token, client=client)
    except Exception as exc:
        if not _permission_denied(exc):
            raise
        try:
            daily = fetch_tushare_daily(symbol, start, end, token=token, client=client)
        except Exception as daily_exc:
            if _permission_denied(daily_exc):
                raise ValueError(
                    "当前 Tushare token 没有行情权限：分钟线 stk_mins 和日线 daily 都不能用。"
                    "请到 https://tushare.pro/document/1?doc_id=108 查看积分与权限。"
                ) from daily_exc
            raise
        daily.attrs["note"] = "无 stk_mins 权限，已自动改用日线（收盘价）"
        return daily


def _stock_basic_path() -> str:
    return os.path.join(CACHE_DIR, "_stock_basic.csv")


def load_stock_basic(token: str | None = None, client=None) -> pd.DataFrame:
    path = _stock_basic_path()
    cols = ["ts_code", "symbol", "name", "industry", "market"]
    live = client is None
    if live and os.path.isfile(path) and time.time() - os.path.getmtime(path) < 24 * 3600:
        return pd.read_csv(path)
    if live:
        resolved = resolve_token(token)
        if not resolved:
            if os.path.isfile(path):
                return pd.read_csv(path)
            raise ValueError("未配置 TUSHARE_TOKEN。请在项目根目录 .env 写入 TUSHARE_TOKEN=你的token")
        client = _make_client(resolved)
    try:
        raw = client.stock_basic(exchange="", list_status="L", fields=",".join(cols))
    except Exception as exc:
        if os.path.isfile(path):
            return pd.read_csv(path)
        if _permission_denied(exc):
            raise ValueError("当前 token 没有股票列表权限，请直接输入 6 位代码（如 688256）。") from exc
        raise
    if raw is None or raw.empty:
        if os.path.isfile(path):
            return pd.read_csv(path)
        return pd.DataFrame(columns=cols)
    df = raw.copy()
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    df = df[cols]
    if live:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(path, index=False)
    return df


def _looks_like_code(query: str) -> bool:
    q = str(query).strip().upper()
    if "." in q:
        num = q.split(".", 1)[0]
        return num.isdigit() and len(num) == 6
    return q.isdigit() and len(q) == 6


def search_stocks(
    query: str,
    token: str | None = None,
    client=None,
    limit: int = 20,
) -> list[dict]:
    q = str(query or "").strip()
    if not q:
        return []
    df = load_stock_basic(token=token, client=client)
    out: list[dict] = []
    if df is not None and not df.empty:
        name = df["name"].astype(str)
        code = df["ts_code"].astype(str).str.upper()
        sym = df["symbol"].astype(str)
        upper = q.upper()
        mask = (
            name.str.contains(q, regex=False)
            | code.str.contains(upper, regex=False)
            | sym.str.contains(q, regex=False)
        )
        for _, row in df.loc[mask].head(limit).iterrows():
            out.append({
                "ts_code": str(row["ts_code"]),
                "symbol": str(row.get("symbol") or ""),
                "name": str(row.get("name") or ""),
                "industry": str(row.get("industry") or ""),
                "market": str(row.get("market") or ""),
            })
    if not out and _looks_like_code(q):
        ts_code = to_ts_code(q)
        out.append({
            "ts_code": ts_code,
            "symbol": ts_code.split(".", 1)[0],
            "name": q,
            "industry": "",
            "market": "",
        })
    return out


def _resolve_name(ts_code: str, token: str | None = None, client=None) -> str:
    try:
        listed = load_stock_basic(token=token, client=client)
    except Exception:
        return ts_code
    if listed is None or listed.empty:
        return ts_code
    hit = listed[listed["ts_code"].astype(str) == ts_code]
    if hit.empty:
        return ts_code
    return str(hit.iloc[0]["name"])


def fetch_quote_daily(
    symbol: str,
    start: str,
    end: str,
    token: str | None = None,
    client=None,
) -> dict:
    """日线 OHLC，给行情页画 K 线。"""
    q = str(symbol).strip()
    if _looks_like_code(q):
        ts_code = to_ts_code(q)
    else:
        hits = search_stocks(q, token=token, client=client, limit=1)
        if not hits:
            raise ValueError(f"找不到公司：{q}。请改用 6 位代码，例如 688256。")
        ts_code = hits[0]["ts_code"]
    live = client is None
    cache_path = _cache_path(ts_code, "Dohlc", start, end)
    if live and os.path.isfile(cache_path):
        raw = pd.read_csv(cache_path)
    else:
        if live:
            resolved = resolve_token(token)
            if not resolved:
                raise ValueError("未配置 TUSHARE_TOKEN。请在项目根目录 .env 写入 TUSHARE_TOKEN=你的token")
            client = _make_client(resolved)
        try:
            raw = client.daily(ts_code=ts_code, start_date=_ymd(start), end_date=_ymd(end))
        except Exception as exc:
            if _permission_denied(exc):
                raise ValueError(
                    "当前 Tushare token 没有日线 daily 权限。"
                    "请到 https://tushare.pro/document/1?doc_id=108 查看积分。"
                ) from exc
            raise
        if raw is None or raw.empty:
            raise ValueError(f"Tushare 未返回 {ts_code} 日线，请检查代码和日期。")
        if live:
            os.makedirs(CACHE_DIR, exist_ok=True)
            raw.to_csv(cache_path, index=False)

    df = raw.copy()
    df["trade_date"] = pd.to_datetime(
        df["trade_date"].astype(str).str.replace("-", "", regex=False).str[:8],
        format="%Y%m%d",
    )
    df = df.sort_values("trade_date").reset_index(drop=True)
    bars = []
    for _, row in df.iterrows():
        close = float(row["close"])
        prev = bars[-1]["close"] if bars else None
        pct = row["pct_chg"] if "pct_chg" in df.columns else None
        if pct is None or (isinstance(pct, float) and pd.isna(pct)):
            pct = None if prev in (None, 0) else (close / prev - 1) * 100
        else:
            pct = float(pct)
        bars.append({
            "date": pd.Timestamp(row["trade_date"]).strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": close,
            "vol": float(row["vol"] if "vol" in df.columns else 0),
            "amount": float(row["amount"] if "amount" in df.columns else 0),
            "pct_chg": pct,
        })
    first = bars[0]["close"]
    last = bars[-1]["close"]
    return {
        "ts_code": ts_code,
        "name": _resolve_name(ts_code, token=token, client=client),
        "note": "Tushare 日线（未复权）",
        "start": bars[0]["date"],
        "end": bars[-1]["date"],
        "bars": bars,
        "stats": {
            "first_close": first,
            "last_close": last,
            "change_pct": (last / first - 1) if first else 0.0,
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
            "bars": len(bars),
        },
    }
