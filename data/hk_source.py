"""港股行情：优先 Tushare hk_basic / hk_daily，没权限则 Yahoo / Stooq。"""
from __future__ import annotations
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from data.tushare_source import (
    _make_client,
    _permission_denied,
    _ymd,
    resolve_token,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "cache", "hk")

HK_ALIASES = {
    "腾讯": "00700.HK", "腾讯控股": "00700.HK", "tencent": "00700.HK",
    "阿里": "09988.HK", "阿里巴巴": "09988.HK", "alibaba": "09988.HK",
    "美团": "03690.HK", "meituan": "03690.HK",
    "小米": "01810.HK", "xiaomi": "01810.HK",
    "比亚迪股份": "01211.HK",
    "汇丰": "00005.HK", "hsbc": "00005.HK",
    "友邦": "01299.HK",
}


def to_hk_symbol(symbol: str) -> str:
    code = str(symbol).strip().upper()
    if not code:
        raise ValueError("股票代码为空")
    if code.endswith(".HK"):
        code = code[:-3]
    digits = "".join(ch for ch in code if ch.isdigit())
    if not digits or len(digits) > 5:
        raise ValueError(f"无法识别港股代码: {symbol}")
    return f"{digits.zfill(5)}.HK"


def _looks_like_hk_code(query: str) -> bool:
    q = str(query).strip().upper().replace(".HK", "")
    return q.isdigit() and 1 <= len(q) <= 5


def _yahoo_symbol(ts_code: str) -> str:
    num = ts_code.split(".", 1)[0].lstrip("0") or "0"
    if len(num) < 4:
        num = num.zfill(4)
    return f"{num}.HK"


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 QuantDesk/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def _hk_basic_path() -> str:
    return os.path.join(CACHE_DIR, "_hk_basic.csv")


def load_hk_basic(token: str | None = None, client=None) -> pd.DataFrame:
    path = _hk_basic_path()
    cols = ["ts_code", "name", "enname", "market"]
    live = client is None
    if live and os.path.isfile(path) and time.time() - os.path.getmtime(path) < 24 * 3600:
        return pd.read_csv(path)
    if live:
        resolved = resolve_token(token)
        if not resolved:
            if os.path.isfile(path):
                return pd.read_csv(path)
            return pd.DataFrame(columns=cols)
        client = _make_client(resolved)
    try:
        raw = client.hk_basic()
    except Exception as exc:
        if os.path.isfile(path):
            return pd.read_csv(path)
        if _permission_denied(exc):
            return pd.DataFrame(columns=cols)
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


def _hit_dict(ts_code: str, name: str = "", enname: str = "", market: str = "HK") -> dict:
    return {
        "ts_code": ts_code,
        "symbol": ts_code,
        "name": name or ts_code,
        "enname": enname,
        "market": market or "HK",
    }


def search_hk_stocks(
    query: str,
    token: str | None = None,
    client=None,
    limit: int = 20,
    http_get=None,
) -> list[dict]:
    q = str(query or "").strip()
    if not q:
        return []
    df = load_hk_basic(token=token, client=client)
    out: list[dict] = []
    seen: set[str] = set()

    def add(item: dict) -> None:
        code = item["ts_code"]
        if code in seen:
            return
        seen.add(code)
        out.append(item)

    alias = HK_ALIASES.get(q) or HK_ALIASES.get(q.lower())
    if alias:
        add(_hit_dict(alias, name=q))

    if df is not None and not df.empty:
        name = df["name"].astype(str)
        enname = df["enname"].astype(str)
        code = df["ts_code"].astype(str).str.upper()
        upper = q.upper()
        mask = (
            name.str.contains(q, regex=False)
            | enname.str.contains(q, case=False, regex=False)
            | code.str.contains(upper, regex=False)
        )
        for _, row in df.loc[mask].head(limit).iterrows():
            try:
                ts_code = to_hk_symbol(str(row["ts_code"]))
            except ValueError:
                ts_code = str(row["ts_code"]).upper()
            add(_hit_dict(
                ts_code,
                name=str(row.get("name") or ""),
                enname=str(row.get("enname") or ""),
                market=str(row.get("market") or "HK"),
            ))

    if not out and http_get is not None:
        try:
            url = (
                "https://query2.finance.yahoo.com/v1/finance/search?"
                + urllib.parse.urlencode({"q": q, "quotesCount": 12, "newsCount": 0})
            )
            payload = json.loads(http_get(url).decode("utf-8"))
            for row in payload.get("quotes") or []:
                sym = str(row.get("symbol") or "").upper()
                if not sym.endswith(".HK"):
                    continue
                add(_hit_dict(
                    to_hk_symbol(sym),
                    name=str(row.get("shortname") or row.get("longname") or sym),
                    enname=str(row.get("longname") or ""),
                ))
        except Exception:
            pass

    if not out and _looks_like_hk_code(q):
        add(_hit_dict(to_hk_symbol(q), name=q))
    return out[:limit]


def _resolve_hk_name(ts_code: str, token: str | None = None, client=None) -> str:
    try:
        listed = load_hk_basic(token=token, client=client)
    except Exception:
        listed = None
    if listed is not None and not listed.empty:
        hit = listed[listed["ts_code"].astype(str).str.upper() == ts_code]
        if not hit.empty:
            name = str(hit.iloc[0].get("name") or "")
            enname = str(hit.iloc[0].get("enname") or "")
            if name and name not in {"None", "nan"}:
                return name
            if enname and enname not in {"None", "nan"}:
                return enname
    for key, val in HK_ALIASES.items():
        if val == ts_code and not key.isascii():
            return key
    return ts_code


def _bars_from_ohlc(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, row in df.iterrows():
        close = row.get("close")
        if close is None or pd.isna(close):
            continue
        close = float(close)
        prev = out[-1]["close"] if out else None
        pct = None
        for col in ("pct_chg", "pct_change"):
            if col in df.columns and pd.notna(row.get(col)):
                pct = float(row[col])
                break
        if pct is None and prev not in (None, 0):
            pct = (close / prev - 1) * 100
        vol = row["vol"] if "vol" in df.columns else 0
        amount = row["amount"] if "amount" in df.columns else 0
        out.append({
            "date": pd.Timestamp(row["trade_date"]).strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": close,
            "vol": float(0 if pd.isna(vol) else vol),
            "amount": float(0 if pd.isna(amount) else amount),
            "pct_chg": pct,
        })
    return out


def _payload(ts_code: str, name: str, note: str, bars: list[dict]) -> dict:
    if not bars:
        raise ValueError(f"未返回 {ts_code} 日线，请检查代码和日期。")
    first = bars[0]["close"]
    last = bars[-1]["close"]
    return {
        "ts_code": ts_code,
        "name": name,
        "market": "HK",
        "note": note,
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


def _from_yahoo(ts_code: str, start: str, end: str, http_get) -> dict:
    start_dt = datetime.strptime(start[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    period1 = int(start_dt.timestamp())
    period2 = int(end_dt.timestamp()) + 86400
    ysym = _yahoo_symbol(ts_code)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}"
        f"?period1={period1}&period2={period2}&interval=1d"
    )
    payload = json.loads(http_get(url).decode("utf-8"))
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise ValueError("Yahoo 未返回行情")
    meta = result.get("meta") or {}
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for i, ts in enumerate(result.get("timestamp") or []):
        close = (quote.get("close") or [None])[i] if i < len(quote.get("close") or []) else None
        if close is None:
            continue
        rows.append({
            "trade_date": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"),
            "open": (quote.get("open") or [close])[i],
            "high": (quote.get("high") or [close])[i],
            "low": (quote.get("low") or [close])[i],
            "close": close,
            "vol": (quote.get("volume") or [0])[i] or 0,
            "amount": 0,
        })
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    name = str(meta.get("shortName") or meta.get("symbol") or ts_code)
    return _payload(ts_code, name, "Yahoo Finance 日线", _bars_from_ohlc(df))


def _from_stooq(ts_code: str, start: str, end: str, http_get) -> dict:
    d1 = start[:10].replace("-", "")
    d2 = end[:10].replace("-", "")
    ysym = _yahoo_symbol(ts_code).lower()
    url = f"https://stooq.com/q/d/l/?s={ysym}&d1={d1}&d2={d2}&i=d"
    text = http_get(url).decode("utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2 or "Date" not in lines[0]:
        raise ValueError("Stooq 未返回行情")
    df = pd.read_csv(StringIO("\n".join(lines)))
    df = df.rename(columns={
        "Date": "trade_date", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "vol",
    })
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["amount"] = 0
    df = df.sort_values("trade_date").reset_index(drop=True)
    return _payload(ts_code, ts_code, "Stooq 日线", _bars_from_ohlc(df))


def _cache_path(ts_code: str, start: str, end: str) -> str:
    return os.path.join(CACHE_DIR, f"{ts_code}_Dohlc_{_ymd(start)}_{_ymd(end)}.csv")


def fetch_hk_quote_daily(
    symbol: str,
    start: str,
    end: str,
    token: str | None = None,
    client=None,
    http_get=None,
) -> dict:
    q = str(symbol).strip()
    if _looks_like_hk_code(q):
        ts_code = to_hk_symbol(q)
    else:
        hits = search_hk_stocks(q, token=token, client=client, limit=1, http_get=http_get)
        if not hits:
            raise ValueError(f"找不到港股：{q}。请改用代码，例如 00700 或 0700.HK。")
        ts_code = hits[0]["ts_code"]

    getter = http_get or _http_get
    live = client is None
    cache_path = _cache_path(ts_code, start, end)
    if live and os.path.isfile(cache_path):
        raw = pd.read_csv(cache_path)
        raw["trade_date"] = pd.to_datetime(
            raw["trade_date"].astype(str).str.replace("-", "", regex=False).str[:8],
            format="%Y%m%d",
            errors="coerce",
        )
        if raw["trade_date"].isna().any():
            raw = pd.read_csv(cache_path, parse_dates=["trade_date"])
        name = _resolve_hk_name(ts_code, token=token, client=client)
        return _payload(ts_code, name, "港股日线（本地缓存）", _bars_from_ohlc(raw))

    tushare_err = None
    if live:
        resolved = resolve_token(token)
        if resolved:
            client = _make_client(resolved)
    if client is not None and hasattr(client, "hk_daily"):
        try:
            raw = client.hk_daily(ts_code=ts_code, start_date=_ymd(start), end_date=_ymd(end))
            if raw is not None and not raw.empty:
                if live:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    raw.to_csv(cache_path, index=False)
                df = raw.copy()
                df["trade_date"] = pd.to_datetime(
                    df["trade_date"].astype(str).str.replace("-", "", regex=False).str[:8],
                    format="%Y%m%d",
                )
                df = df.sort_values("trade_date").reset_index(drop=True)
                name = _resolve_hk_name(ts_code, token=token, client=client)
                return _payload(ts_code, name, "Tushare 港股日线（未复权）", _bars_from_ohlc(df))
        except Exception as exc:
            tushare_err = exc

    try:
        return _from_yahoo(ts_code, start, end, getter)
    except Exception as yahoo_exc:
        try:
            return _from_stooq(ts_code, start, end, getter)
        except Exception:
            reason = str(tushare_err or yahoo_exc)
            raise ValueError(
                f"无法获取 {ts_code} 港股日线（{reason}）。"
            ) from yahoo_exc
