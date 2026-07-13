import json
import numpy as np
import pandas as pd
import yfinance as yf


def _safe(v, decimals=2):
    try:
        if v is None:
            return None
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def compare_growth_trends(symbols: list[str]) -> dict:
    """
    Compare revenue/earnings growth and demand signals across a group of related
    companies (e.g. a supply chain: chip designer -> foundry -> equipment makers).
    Rising revenue across the chain confirms end-product demand.
    """
    results = []
    for sym in symbols:
        sym = sym.upper()
        try:
            ticker = yf.Ticker(sym)
            info = ticker.info

            entry = {
                "symbol": sym,
                "name": info.get("shortName", sym),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "revenue_growth_yoy_pct": _safe(
                    info.get("revenueGrowth", 0) * 100 if info.get("revenueGrowth") is not None else None, 1),
                "earnings_growth_yoy_pct": _safe(
                    info.get("earningsGrowth", 0) * 100 if info.get("earningsGrowth") is not None else None, 1),
                "gross_margin_pct": _safe(
                    info.get("grossMargins", 0) * 100 if info.get("grossMargins") is not None else None, 1),
                "forward_pe": _safe(info.get("forwardPE")),
                "recommendation": info.get("recommendationKey"),
            }

            # Quarterly revenue trend (last 6 quarters) to see acceleration/deceleration
            q = ticker.quarterly_income_stmt
            if q is not None and not q.empty:
                revs = []
                for col in list(q.columns)[:6]:
                    rev = q[col].get("Total Revenue")
                    if rev is not None and not pd.isna(rev):
                        revs.append({
                            "quarter": col.strftime("%Y-%m"),
                            "revenue": round(float(rev), 0),
                        })
                # QoQ growth sequence — is growth accelerating?
                qoq = []
                for i in range(len(revs) - 1):
                    cur, prv = revs[i]["revenue"], revs[i + 1]["revenue"]
                    if prv:
                        qoq.append(round((cur - prv) / abs(prv) * 100, 1))
                entry["quarterly_revenue"] = revs
                entry["revenue_qoq_growth_sequence_pct"] = qoq
                if len(qoq) >= 2:
                    entry["growth_accelerating"] = qoq[0] > qoq[1]

            # 3-month relative price performance (market's read on demand)
            hist = ticker.history(period="3mo", auto_adjust=True)
            if len(hist) > 1:
                perf = (float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[0])) / float(hist["Close"].iloc[0]) * 100
                entry["price_perf_3mo_pct"] = round(perf, 1)

            results.append(entry)
        except Exception as e:
            results.append({"symbol": sym, "error": str(e)})

    # Chain-level summary
    growths = [r["revenue_growth_yoy_pct"] for r in results
               if isinstance(r.get("revenue_growth_yoy_pct"), (int, float))]
    summary = {
        "num_companies": len(results),
        "avg_revenue_growth_yoy_pct": round(float(np.mean(growths)), 1) if growths else None,
        "companies_growing": sum(1 for g in growths if g > 0),
        "companies_shrinking": sum(1 for g in growths if g <= 0),
    }

    return {"companies": results, "chain_summary": summary}


COMPARE_GROWTH_TOOL = {
    "name": "compare_growth_trends",
    "description": (
        "Compare revenue growth, earnings growth, quarterly revenue trends (with QoQ acceleration "
        "detection), margins, and 3-month price performance across a group of related companies. "
        "Designed for supply-chain analysis: pass the tickers of companies along a product's "
        "manufacturing chain (e.g. for AI chips: NVDA, TSM, ASML, AMAT, LRCX, MU, SK hynix ADR) "
        "to verify whether end-product demand is genuinely growing through the whole chain. "
        "Also useful for peer comparison within a sector. "
        "First identify the relevant supply-chain tickers yourself (use web_search if needed), "
        "then call this tool with that list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tickers of related companies (supply chain or peer group), 2-10 symbols",
            }
        },
        "required": ["symbols"],
    },
}


def dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "compare_growth_trends":
        result = compare_growth_trends(tool_input["symbols"])
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)
