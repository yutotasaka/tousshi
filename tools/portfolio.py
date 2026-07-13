import json
import yfinance as yf
import pandas as pd
import numpy as np


def normalize_symbol(symbol: str) -> str:
    """'7203' -> '7203.T' (Tokyo). Leave US/other tickers as-is."""
    s = symbol.strip().upper()
    if s.isdigit() and len(s) == 4:
        return f"{s}.T"
    return s


def get_usdjpy_rate() -> float:
    """Current USD/JPY rate; fallback to 150.0 if unavailable. Cached in Streamlit if available."""
    try:
        import streamlit as st
        if not hasattr(get_usdjpy_rate, "_cached"):
            get_usdjpy_rate._cached = st.cache_data(ttl=300)(_fetch_usdjpy_rate)
        return get_usdjpy_rate._cached()
    except Exception:
        return _fetch_usdjpy_rate()


def _fetch_usdjpy_rate() -> float:
    try:
        hist = yf.Ticker("USDJPY=X").history(period="2d", auto_adjust=True)
        if len(hist) >= 1:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return 150.0


def _detect_currency(info: dict, symbol: str) -> str:
    cur = (info or {}).get("currency")
    if cur:
        return cur.upper()
    return "JPY" if symbol.endswith(".T") else "USD"


def get_portfolio_snapshot(holdings: list[dict]) -> dict:
    """
    holdings: [{"symbol": "7203.T", "shares": 100, "avg_cost": 2500.0}, ...]
    avg_cost is in the security's native currency (JPY for .T, USD for US stocks).
    All portfolio totals are reported in JPY. USD positions are converted at the
    current USDJPY rate.
    """
    usdjpy = get_usdjpy_rate()
    results = []
    total_value_jpy = 0.0
    total_cost_jpy = 0.0

    for h in holdings:
        sym = normalize_symbol(h["symbol"])
        try:
            shares = float(h["shares"])
            avg_cost = float(h["avg_cost"])
        except (TypeError, ValueError):
            results.append({"symbol": sym, "error": "株数または取得単価が数値ではありません"})
            continue

        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="5d", auto_adjust=True)
            try:
                info = ticker.info or {}
            except Exception:
                info = {}

            if hist is None or hist.empty:
                results.append({
                    "symbol": sym,
                    "error": f"{sym} の価格データを取得できません（ティッカーを確認してください）",
                    "shares": shares,
                    "avg_cost": avg_cost,
                })
                continue

            current_price = float(hist["Close"].iloc[-1])
            prev_price = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
            day_change_pct = (current_price - prev_price) / prev_price * 100 if prev_price else 0.0

            currency = _detect_currency(info, sym)
            fx = usdjpy if currency == "USD" else 1.0

            # 取得時の為替レート（PayPay証券などの「取得為替レート」）が指定されていれば
            # 取得金額の円換算に使う。未指定なら現在レートを使う。
            cost_fx = fx
            if currency == "USD":
                try:
                    if h.get("fx_at_cost"):
                        cost_fx = float(h["fx_at_cost"])
                except (TypeError, ValueError):
                    cost_fx = fx

            cost_basis = avg_cost * shares
            market_value = current_price * shares
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else 0.0

            cost_basis_jpy = cost_basis * cost_fx
            market_value_jpy = market_value * fx
            total_value_jpy += market_value_jpy
            total_cost_jpy += cost_basis_jpy

            # Analyst data (may be missing for many JP stocks)
            target_mean = info.get("targetMeanPrice")
            recommendation = info.get("recommendationKey", "N/A")
            num_analysts = info.get("numberOfAnalystOpinions", 0)
            upside = None
            if target_mean and current_price:
                try:
                    upside = (float(target_mean) - current_price) / current_price * 100
                except (TypeError, ValueError):
                    upside = None

            def _f(v, d=2):
                try:
                    f = float(v)
                    if np.isnan(f) or np.isinf(f):
                        return None
                    return round(f, d)
                except (TypeError, ValueError):
                    return None

            results.append({
                "symbol": sym,
                "name": info.get("shortName", sym),
                "currency": currency,
                "shares": shares,
                "avg_cost": round(avg_cost, 2),
                "current_price": round(current_price, 2),
                "day_change_pct": round(day_change_pct, 2),
                "cost_basis": round(cost_basis, 2),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                "cost_basis_jpy": round(cost_basis_jpy, 0),
                "market_value_jpy": round(market_value_jpy, 0),
                "unrealized_pnl_jpy": round(market_value_jpy - cost_basis_jpy, 0),
                "analyst": {
                    "recommendation": recommendation,
                    "target_mean": _f(target_mean),
                    "target_high": _f(info.get("targetHighPrice")),
                    "target_low": _f(info.get("targetLowPrice")),
                    "upside_pct": _f(upside, 1),
                    "num_analysts": num_analysts,
                },
                "sector": info.get("sector", "N/A"),
                "beta": _f(info.get("beta")),
                "pe_ratio": _f(info.get("trailingPE")),
                "market_cap": info.get("marketCap"),
            })
        except Exception as e:
            results.append({
                "symbol": sym,
                "error": str(e),
                "shares": shares,
                "avg_cost": avg_cost,
            })

    total_pnl_jpy = total_value_jpy - total_cost_jpy
    total_pnl_pct = (total_pnl_jpy / total_cost_jpy * 100) if total_cost_jpy else 0.0

    for r in results:
        if "market_value_jpy" in r:
            r["allocation_pct"] = round(r["market_value_jpy"] / total_value_jpy * 100, 1) if total_value_jpy else 0.0

    return {
        "base_currency": "JPY",
        "usdjpy_rate": round(usdjpy, 2),
        "holdings": results,
        "summary": {
            "total_cost_jpy": round(total_cost_jpy, 0),
            "total_value_jpy": round(total_value_jpy, 0),
            "total_pnl_jpy": round(total_pnl_jpy, 0),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "num_positions": len(holdings),
        },
    }


def get_portfolio_risk(holdings: list[dict]) -> dict:
    """Portfolio risk metrics vs relevant benchmarks (JPY-based weights)."""
    symbols = [normalize_symbol(h["symbol"]) for h in holdings]
    if not symbols:
        return {"error": "ポートフォリオが空です"}

    has_jp = any(s.endswith(".T") for s in symbols)
    benchmark = "^N225" if has_jp else "^GSPC"

    try:
        raw = yf.download(symbols + [benchmark], period="6mo", auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            return {"error": "価格データを取得できませんでした"}
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        if isinstance(closes, pd.Series):
            closes = closes.to_frame()
        returns = closes.pct_change().dropna(how="all")
    except Exception as e:
        return {"error": f"データ取得エラー: {e}"}

    usdjpy = get_usdjpy_rate()

    # JPY market values for weights
    total_value = 0.0
    values = {}
    for h in holdings:
        sym = normalize_symbol(h["symbol"])
        try:
            price = float(closes[sym].dropna().iloc[-1]) if sym in closes.columns else float(h["avg_cost"])
        except Exception:
            price = float(h["avg_cost"])
        fx = 1.0 if sym.endswith(".T") else usdjpy
        v = price * float(h["shares"]) * fx
        values[sym] = v
        total_value += v

    weights = {s: values.get(s, 0) / total_value for s in symbols} if total_value else {}

    portfolio_beta = 0.0
    betas = {}
    for sym in symbols:
        try:
            if sym in returns.columns and benchmark in returns.columns:
                pair = returns[[sym, benchmark]].dropna()
                if len(pair) < 20:
                    continue
                cov = pair[sym].cov(pair[benchmark])
                var = pair[benchmark].var()
                beta = cov / var if var else 1.0
                betas[sym] = round(float(beta), 2)
                portfolio_beta += weights.get(sym, 0) * float(beta)
        except Exception:
            continue

    top_sym = max(weights, key=weights.get) if weights else None
    top_weight = weights.get(top_sym, 0) * 100 if top_sym else 0

    try:
        port_cols = [s for s in symbols if s in returns.columns]
        corr = returns[port_cols].corr().round(2).to_dict() if port_cols else {}
    except Exception:
        corr = {}

    return {
        "benchmark": benchmark,
        "portfolio_beta": round(portfolio_beta, 2),
        "individual_betas": betas,
        "weights_pct": {s: round(w * 100, 1) for s, w in weights.items()},
        "top_concentration": {"symbol": top_sym, "weight_pct": round(top_weight, 1)},
        "correlation_matrix": corr,
        "usdjpy_rate": round(usdjpy, 2),
    }


PORTFOLIO_SNAPSHOT_TOOL = {
    "name": "get_portfolio_snapshot",
    "description": (
        "Get current P&L, market value, analyst ratings for each holding. "
        "Supports both Japanese stocks (.T suffix, JPY) and US stocks (USD). "
        "All portfolio totals are converted to JPY at the current USDJPY rate. "
        "Use this to analyze the user's positions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "holdings": {
                "type": "array",
                "description": "User's portfolio holdings. avg_cost is in the security's native currency.",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Ticker: '7203.T' for Toyota (JP), 'AAPL' for US"},
                        "shares": {"type": "number"},
                        "avg_cost": {"type": "number", "description": "Average cost per share in native currency (JPY for .T, USD for US)"},
                    },
                    "required": ["symbol", "shares", "avg_cost"],
                },
            }
        },
        "required": ["holdings"],
    },
}

PORTFOLIO_RISK_TOOL = {
    "name": "get_portfolio_risk",
    "description": (
        "Compute portfolio risk metrics: weighted beta (vs Nikkei 225 if JP stocks held, "
        "else S&P500), correlation matrix, concentration risk. Weights are JPY-based."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "holdings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "shares": {"type": "number"},
                        "avg_cost": {"type": "number"},
                    },
                    "required": ["symbol", "shares", "avg_cost"],
                },
            }
        },
        "required": ["holdings"],
    },
}


def dispatch(tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "get_portfolio_snapshot":
            result = get_portfolio_snapshot(tool_input["holdings"])
        elif tool_name == "get_portfolio_risk":
            result = get_portfolio_risk(tool_input["holdings"])
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        result = {"error": str(e)}
    return json.dumps(result, ensure_ascii=False)
