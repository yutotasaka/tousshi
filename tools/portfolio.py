import json
import yfinance as yf
import pandas as pd
import numpy as np


def get_portfolio_snapshot(holdings: list[dict]) -> dict:
    """
    holdings: [{"symbol": "AAPL", "shares": 100, "avg_cost": 150.0}, ...]
    Returns P&L, allocation, analyst ratings for each holding.
    """
    results = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        sym = h["symbol"].upper()
        shares = float(h["shares"])
        avg_cost = float(h["avg_cost"])

        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="2d", auto_adjust=True)
            info = ticker.info

            if len(hist) >= 1:
                current_price = float(hist["Close"].iloc[-1])
            else:
                current_price = avg_cost

            prev_price = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
            day_change_pct = (current_price - prev_price) / prev_price * 100 if prev_price else 0

            cost_basis = avg_cost * shares
            market_value = current_price * shares
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else 0

            total_value += market_value
            total_cost += cost_basis

            # Analyst data
            target_mean = info.get("targetMeanPrice")
            target_high = info.get("targetHighPrice")
            target_low = info.get("targetLowPrice")
            recommendation = info.get("recommendationKey", "N/A")
            num_analysts = info.get("numberOfAnalystOpinions", 0)
            upside = ((target_mean - current_price) / current_price * 100) if target_mean else None

            results.append({
                "symbol": sym,
                "name": info.get("shortName", sym),
                "shares": shares,
                "avg_cost": round(avg_cost, 2),
                "current_price": round(current_price, 2),
                "day_change_pct": round(day_change_pct, 2),
                "cost_basis": round(cost_basis, 2),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                "analyst": {
                    "recommendation": recommendation,
                    "target_mean": round(target_mean, 2) if target_mean else None,
                    "target_high": round(target_high, 2) if target_high else None,
                    "target_low": round(target_low, 2) if target_low else None,
                    "upside_pct": round(upside, 1) if upside is not None else None,
                    "num_analysts": num_analysts,
                },
                "sector": info.get("sector", "N/A"),
                "beta": info.get("beta"),
                "pe_ratio": info.get("trailingPE"),
                "market_cap": info.get("marketCap"),
            })
        except Exception as e:
            results.append({
                "symbol": sym,
                "error": str(e),
                "shares": shares,
                "avg_cost": avg_cost,
            })

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    # Allocation %
    for r in results:
        if "market_value" in r:
            r["allocation_pct"] = round(r["market_value"] / total_value * 100, 1) if total_value else 0

    return {
        "holdings": results,
        "summary": {
            "total_cost": round(total_cost, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "num_positions": len(holdings),
        },
    }


def get_portfolio_risk(holdings: list[dict]) -> dict:
    """Compute portfolio-level risk metrics: beta, correlation, concentration."""
    symbols = [h["symbol"].upper() for h in holdings]
    weights_map = {}

    # Get prices for correlation/beta
    try:
        raw = yf.download(symbols + ["^GSPC"], period="6mo", auto_adjust=True, progress=False)
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        returns = closes.pct_change().dropna()
    except Exception as e:
        return {"error": str(e)}

    # Compute market values for weights
    total_value = 0.0
    values = {}
    for h in holdings:
        sym = h["symbol"].upper()
        try:
            price = float(closes[sym].iloc[-1]) if sym in closes.columns else float(h["avg_cost"])
        except Exception:
            price = float(h["avg_cost"])
        v = price * float(h["shares"])
        values[sym] = v
        total_value += v

    weights = {s: values.get(s, 0) / total_value for s in symbols} if total_value else {}

    # Portfolio beta
    portfolio_beta = 0.0
    betas = {}
    for sym in symbols:
        if sym in returns.columns and "^GSPC" in returns.columns:
            cov = returns[sym].cov(returns["^GSPC"])
            var = returns["^GSPC"].var()
            beta = cov / var if var else 1.0
            betas[sym] = round(float(beta), 2)
            portfolio_beta += weights.get(sym, 0) * float(beta)

    # Concentration: top holding weight
    top_sym = max(weights, key=weights.get) if weights else None
    top_weight = weights.get(top_sym, 0) * 100 if top_sym else 0

    # Correlation matrix (exclude SPX)
    port_returns = returns[[s for s in symbols if s in returns.columns]]
    corr = port_returns.corr().round(2).to_dict() if not port_returns.empty else {}

    return {
        "portfolio_beta": round(portfolio_beta, 2),
        "individual_betas": betas,
        "weights_pct": {s: round(w * 100, 1) for s, w in weights.items()},
        "top_concentration": {"symbol": top_sym, "weight_pct": round(top_weight, 1)},
        "correlation_matrix": corr,
    }


PORTFOLIO_SNAPSHOT_TOOL = {
    "name": "get_portfolio_snapshot",
    "description": (
        "Get current P&L, market value, analyst ratings (target price, recommendation), "
        "sector, beta, PE ratio for each holding in the user's portfolio. "
        "Use this to analyze the user's specific positions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "holdings": {
                "type": "array",
                "description": "User's portfolio holdings",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "shares": {"type": "number"},
                        "avg_cost": {"type": "number", "description": "Average cost per share"},
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
        "Compute portfolio risk metrics: weighted beta, correlation matrix, concentration risk. "
        "Use this to assess overall portfolio risk from an institutional perspective."
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
    if tool_name == "get_portfolio_snapshot":
        result = get_portfolio_snapshot(tool_input["holdings"])
    elif tool_name == "get_portfolio_risk":
        result = get_portfolio_risk(tool_input["holdings"])
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)
