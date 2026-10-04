"""网页看板：包装回测服务。"""
from __future__ import annotations
import os
import sys
import tempfile
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from data.hk_source import fetch_hk_quote_daily, search_hk_stocks
from data.tushare_source import fetch_quote_daily, resolve_token, search_stocks
from data.us_source import fetch_us_quote_daily, search_us_stocks
from engine.runner import dashboard_payload, execute_backtest, list_strategies

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _form_or_json() -> dict:
    if request.files or request.form:
        data = {k: request.form.get(k) for k in request.form}
        return {k: v for k, v in data.items() if v is not None and v != ""}
    return request.get_json(silent=True) or {}


def _as_float(value, default):
    if value is None or value == "":
        return default
    return float(value)


def _as_int(value, default):
    if value is None or value == "":
        return default
    return int(float(value))


def create_app() -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")

    @app.get("/")
    def index():
        resp = send_from_directory(STATIC_DIR, "index.html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/api/strategies")
    def strategies():
        return jsonify({"strategies": list_strategies()})

    @app.get("/api/source")
    def source_status():
        return jsonify({
            "tushare_token": bool(resolve_token()),
            "note": "Tushare Pro：优先分钟线，无权限则自动改用日线。",
        })

    @app.get("/api/stocks")
    def stocks():
        q = (request.args.get("q") or "").strip()
        try:
            return jsonify({"stocks": search_stocks(q, token=request.args.get("token"))})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/quotes")
    def quotes():
        symbol = (request.args.get("symbol") or "").strip()
        if not symbol:
            return jsonify({"error": "请提供股票代码或名称"}), 400
        end = (request.args.get("end") or "").strip()
        start = (request.args.get("start") or "").strip()
        if not end:
            end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not start:
            start = (datetime.strptime(end[:10], "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
        try:
            return jsonify(fetch_quote_daily(
                symbol, start=start, end=end, token=request.args.get("token"),
            ))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/us/stocks")
    def us_stocks():
        q = (request.args.get("q") or "").strip()
        try:
            return jsonify({"stocks": search_us_stocks(q, token=request.args.get("token"))})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/us/quotes")
    def us_quotes():
        symbol = (request.args.get("symbol") or "").strip()
        if not symbol:
            return jsonify({"error": "请提供美股代码或名称"}), 400
        end = (request.args.get("end") or "").strip()
        start = (request.args.get("start") or "").strip()
        if not end:
            end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not start:
            start = (datetime.strptime(end[:10], "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
        try:
            return jsonify(fetch_us_quote_daily(
                symbol, start=start, end=end, token=request.args.get("token"),
            ))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/hk/stocks")
    def hk_stocks():
        q = (request.args.get("q") or "").strip()
        try:
            return jsonify({"stocks": search_hk_stocks(q, token=request.args.get("token"))})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/hk/quotes")
    def hk_quotes():
        symbol = (request.args.get("symbol") or "").strip()
        if not symbol:
            return jsonify({"error": "请提供港股代码或名称"}), 400
        end = (request.args.get("end") or "").strip()
        start = (request.args.get("start") or "").strip()
        if not end:
            end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if not start:
            start = (datetime.strptime(end[:10], "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
        try:
            return jsonify(fetch_hk_quote_daily(
                symbol, start=start, end=end, token=request.args.get("token"),
            ))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": str(exc)}), 500

    @app.post("/api/run")
    def run():
        payload = _form_or_json()
        strategy = str(payload.get("strategy") or "dma")
        source = str(payload.get("source") or "synthetic")
        symbol = str(payload.get("symbol") or ("600519" if source == "tushare" else "SIM000001"))
        params = {
            "fast": _as_int(payload.get("fast"), 30),
            "slow": _as_int(payload.get("slow"), 150),
            "window": _as_int(payload.get("window"), 200),
            "num_std": _as_float(payload.get("num_std"), 2.0),
        }
        tmp_path = None
        try:
            upload = request.files.get("file")
            if upload and upload.filename:
                suffix = os.path.splitext(upload.filename)[1] or ".csv"
                fd, tmp_path = tempfile.mkstemp(suffix=suffix)
                os.close(fd)
                upload.save(tmp_path)
                source = "csv"
            raw = execute_backtest(
                strategy,
                symbol=symbol,
                cash=_as_float(payload.get("cash"), 1_000_000),
                csv_path=tmp_path,
                days=_as_int(payload.get("days"), 5),
                seed=_as_int(payload.get("seed"), 42),
                params=params,
                slippage=_as_float(payload.get("slippage"), 0.0002),
                source=source,
                start=payload.get("start"),
                end=payload.get("end"),
                freq=str(payload.get("freq") or "1min"),
                token=payload.get("token"),
            )
            return jsonify(dashboard_payload(raw))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover - 兜底
            return jsonify({"error": str(exc)}), 500
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
