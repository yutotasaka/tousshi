import json
import numpy as np
import pandas as pd
import yfinance as yf


def _safe(v, decimals=2):
    """Convert to a JSON-safe rounded float, or None."""
    try:
        if v is None:
            return None
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def _pct_change(current, previous):
    if current is None or previous in (None, 0):
        return None
    try:
        return round((float(current) - float(previous)) / abs(float(previous)) * 100, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def get_earnings_history(symbol: str) -> dict:
    """Quarterly & annual revenue / net income / EPS with YoY & QoQ growth."""
    try:
        ticker = yf.Ticker(symbol)

        result = {"symbol": symbol.upper()}

        # Quarterly income statement
        q = ticker.quarterly_income_stmt
        if q is not None and not q.empty:
            quarters = []
            cols = list(q.columns)[:8]  # up to 8 quarters
            for i, col in enumerate(cols):
                rev = q[col].get("Total Revenue")
                ni = q[col].get("Net Income")
                eps = q[col].get("Diluted EPS")
                entry = {
                    "quarter_end": col.strftime("%Y-%m-%d"),
                    "revenue": _safe(rev, 0),
                    "net_income": _safe(ni, 0),
                    "diluted_eps": _safe(eps, 2),
                }
                quarters.append(entry)
            # growth rates
            for i, entry in enumerate(quarters):
                # QoQ (vs next in list = previous quarter)
                if i + 1 < len(quarters):
                    entry["revenue_qoq_pct"] = _pct_change(entry["revenue"], quarters[i + 1]["revenue"])
                # YoY (4 quarters back)
                if i + 4 < len(quarters):
                    entry["revenue_yoy_pct"] = _pct_change(entry["revenue"], quarters[i + 4]["revenue"])
                    entry["eps_yoy_pct"] = _pct_change(entry["diluted_eps"], quarters[i + 4]["diluted_eps"])
            result["quarterly"] = quarters

        # Annual income statement
        a = ticker.income_stmt
        if a is not None and not a.empty:
            years = []
            cols = list(a.columns)[:4]
            for col in cols:
                years.append({
                    "fiscal_year_end": col.strftime("%Y-%m-%d"),
                    "revenue": _safe(a[col].get("Total Revenue"), 0),
                    "net_income": _safe(a[col].get("Net Income"), 0),
                    "diluted_eps": _safe(a[col].get("Diluted EPS"), 2),
                    "operating_income": _safe(a[col].get("Operating Income"), 0),
                    "gross_profit": _safe(a[col].get("Gross Profit"), 0),
                })
            for i, entry in enumerate(years):
                if i + 1 < len(years):
                    entry["revenue_yoy_pct"] = _pct_change(entry["revenue"], years[i + 1]["revenue"])
                    entry["net_income_yoy_pct"] = _pct_change(entry["net_income"], years[i + 1]["net_income"])
            result["annual"] = years

        if "quarterly" not in result and "annual" not in result:
            return {"error": f"No earnings data for {symbol}"}
        return result
    except Exception as e:
        return {"error": str(e)}


def get_earnings_calendar(symbol: str) -> dict:
    """Next earnings date and analyst EPS/revenue estimates."""
    try:
        ticker = yf.Ticker(symbol)
        result = {"symbol": symbol.upper()}

        cal = ticker.calendar
        if isinstance(cal, dict) and cal:
            dates = cal.get("Earnings Date")
            if dates:
                result["next_earnings_dates"] = [
                    d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d) for d in dates
                ]
            result["eps_estimate_avg"] = _safe(cal.get("Earnings Average"), 2)
            result["eps_estimate_high"] = _safe(cal.get("Earnings High"), 2)
            result["eps_estimate_low"] = _safe(cal.get("Earnings Low"), 2)
            result["revenue_estimate_avg"] = _safe(cal.get("Revenue Average"), 0)
            result["revenue_estimate_high"] = _safe(cal.get("Revenue High"), 0)
            result["revenue_estimate_low"] = _safe(cal.get("Revenue Low"), 0)
            if cal.get("Ex-Dividend Date"):
                d = cal["Ex-Dividend Date"]
                result["ex_dividend_date"] = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)

        # Past earnings vs estimates (surprise history)
        try:
            eh = ticker.earnings_history
            if eh is not None and not eh.empty:
                surprises = []
                for idx, row in eh.tail(4).iterrows():
                    surprises.append({
                        "quarter": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                        "eps_estimate": _safe(row.get("epsEstimate"), 2),
                        "eps_actual": _safe(row.get("epsActual"), 2),
                        "surprise_pct": _safe(row.get("surprisePercent"), 1),
                    })
                result["past_surprises"] = surprises
        except Exception:
            pass

        if len(result) <= 1:
            return {"error": f"No calendar data for {symbol}"}
        return result
    except Exception as e:
        return {"error": str(e)}


def get_balance_sheet_summary(symbol: str) -> dict:
    """Key balance sheet & cash flow items: cash, debt, equity, FCF."""
    try:
        ticker = yf.Ticker(symbol)
        result = {"symbol": symbol.upper()}

        bs = ticker.quarterly_balance_sheet
        if bs is not None and not bs.empty:
            col = bs.columns[0]
            result["as_of"] = col.strftime("%Y-%m-%d")
            result["cash_and_equivalents"] = _safe(bs[col].get("Cash And Cash Equivalents"), 0)
            result["total_debt"] = _safe(bs[col].get("Total Debt"), 0)
            result["total_assets"] = _safe(bs[col].get("Total Assets"), 0)
            result["total_liabilities"] = _safe(bs[col].get("Total Liabilities Net Minority Interest"), 0)
            result["stockholders_equity"] = _safe(bs[col].get("Stockholders Equity"), 0)
            cash = result["cash_and_equivalents"]
            debt = result["total_debt"]
            if cash is not None and debt is not None:
                result["net_cash"] = round(cash - debt, 0)

        cf = ticker.quarterly_cashflow
        if cf is not None and not cf.empty:
            # trailing 4 quarters
            cols = list(cf.columns)[:4]
            fcf_sum = 0.0
            ocf_sum = 0.0
            has_fcf = False
            for col in cols:
                fcf = cf[col].get("Free Cash Flow")
                ocf = cf[col].get("Operating Cash Flow")
                if fcf is not None and not pd.isna(fcf):
                    fcf_sum += float(fcf)
                    has_fcf = True
                if ocf is not None and not pd.isna(ocf):
                    ocf_sum += float(ocf)
            if has_fcf:
                result["free_cash_flow_ttm"] = round(fcf_sum, 0)
                result["operating_cash_flow_ttm"] = round(ocf_sum, 0)

        if len(result) <= 1:
            return {"error": f"No balance sheet data for {symbol}"}
        return result
    except Exception as e:
        return {"error": str(e)}


def get_valuation_metrics(symbol: str) -> dict:
    """Standard valuation & quality metrics: PER, PEG, PBR, ROE, ROA, margins, dividend."""
    try:
        info = yf.Ticker(symbol).info
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
            # info can still be valid without those keys; only fail if clearly empty
            if len(info) < 5:
                return {"error": f"No data for {symbol}"}

        trailing_pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        peg = info.get("pegRatio") or info.get("trailingPegRatio")

        result = {
            "symbol": symbol.upper(),
            "name": info.get("shortName"),
            "sector": info.get("sector"),
            "market_cap": info.get("marketCap"),
            "valuation": {
                "trailing_pe": _safe(trailing_pe),
                "forward_pe": _safe(forward_pe),
                "peg_ratio": _safe(peg),
                "price_to_book": _safe(info.get("priceToBook")),
                "price_to_sales_ttm": _safe(info.get("priceToSalesTrailing12Months")),
                "ev_to_ebitda": _safe(info.get("enterpriseToEbitda")),
                "ev_to_revenue": _safe(info.get("enterpriseToRevenue")),
            },
            "profitability": {
                "roe_pct": _safe(info.get("returnOnEquity", 0) * 100 if info.get("returnOnEquity") is not None else None),
                "roa_pct": _safe(info.get("returnOnAssets", 0) * 100 if info.get("returnOnAssets") is not None else None),
                "gross_margin_pct": _safe(info.get("grossMargins", 0) * 100 if info.get("grossMargins") is not None else None),
                "operating_margin_pct": _safe(info.get("operatingMargins", 0) * 100 if info.get("operatingMargins") is not None else None),
                "net_margin_pct": _safe(info.get("profitMargins", 0) * 100 if info.get("profitMargins") is not None else None),
            },
            "growth": {
                "revenue_growth_yoy_pct": _safe(info.get("revenueGrowth", 0) * 100 if info.get("revenueGrowth") is not None else None),
                "earnings_growth_yoy_pct": _safe(info.get("earningsGrowth", 0) * 100 if info.get("earningsGrowth") is not None else None),
                "earnings_quarterly_growth_pct": _safe(info.get("earningsQuarterlyGrowth", 0) * 100 if info.get("earningsQuarterlyGrowth") is not None else None),
            },
            "financial_health": {
                "debt_to_equity": _safe(info.get("debtToEquity")),
                "current_ratio": _safe(info.get("currentRatio")),
                "quick_ratio": _safe(info.get("quickRatio")),
            },
            "dividend": {
                "dividend_yield_pct": _safe(info.get("dividendYield")),
                "payout_ratio_pct": _safe(info.get("payoutRatio", 0) * 100 if info.get("payoutRatio") is not None else None),
            },
            "beta": _safe(info.get("beta")),
        }
        return result
    except Exception as e:
        return {"error": str(e)}


# ── Tool definitions ─────────────────────────────────────────────────────────

EARNINGS_HISTORY_TOOL = {
    "name": "get_earnings_history",
    "description": (
        "Get quarterly and annual earnings history (revenue, net income, diluted EPS) "
        "with YoY/QoQ growth rates for a stock. Use this to analyze fundamental earnings trends."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker symbol (e.g. NVDA)"},
        },
        "required": ["symbol"],
    },
}

EARNINGS_CALENDAR_TOOL = {
    "name": "get_earnings_calendar",
    "description": (
        "Get the next earnings announcement date, analyst EPS/revenue estimates for the upcoming "
        "quarter, and past earnings surprise history (actual vs estimate). "
        "Use this to identify upcoming catalysts and how the company has beaten/missed consensus."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker symbol (e.g. NVDA)"},
        },
        "required": ["symbol"],
    },
}

BALANCE_SHEET_TOOL = {
    "name": "get_balance_sheet_summary",
    "description": (
        "Get key balance sheet items (cash, total debt, net cash, equity) and trailing-12-month "
        "free cash flow / operating cash flow. Use this to assess financial strength."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker symbol (e.g. NVDA)"},
        },
        "required": ["symbol"],
    },
}

VALUATION_METRICS_TOOL = {
    "name": "get_valuation_metrics",
    "description": (
        "Get standard valuation and quality metrics: trailing/forward PER, PEG, PBR, P/S, "
        "EV/EBITDA, ROE, ROA, gross/operating/net margins, revenue & earnings growth, "
        "debt-to-equity, current ratio, dividend yield, beta. "
        "Use this for fundamental valuation comparison."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Ticker symbol (e.g. NVDA)"},
        },
        "required": ["symbol"],
    },
}


def get_short_interest(symbol: str) -> dict:
    """空売り情報：空売り比率、浮動株に対する空売り比率、前月比の増減。"""
    try:
        info = yf.Ticker(symbol).info or {}
        shares_short = info.get("sharesShort")
        shares_short_prior = info.get("sharesShortPriorMonth")
        change = None
        if shares_short and shares_short_prior:
            change = _pct_change(shares_short, shares_short_prior)
        return {
            "symbol": symbol.upper(),
            "short_ratio_days": _safe(info.get("shortRatio")),  # 日数（買い戻しにかかる日数）
            "short_pct_of_float": _safe(
                info.get("shortPercentOfFloat", 0) * 100 if info.get("shortPercentOfFloat") is not None else None, 2),
            "shares_short": shares_short,
            "shares_short_prior_month": shares_short_prior,
            "shares_short_change_pct": change,  # 前月比：プラス=空売り増加(弱気)
        }
    except Exception as e:
        return {"error": str(e)}


SHORT_INTEREST_TOOL = {
    "name": "get_short_interest",
    "description": (
        "Get short interest data: short ratio (days to cover), short % of float, "
        "and month-over-month change in shares short. Rising short interest signals "
        "growing bearish/institutional short positioning; very high short % can also "
        "mean short-squeeze potential."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"symbol": {"type": "string"}},
        "required": ["symbol"],
    },
}


def dispatch(tool_name: str, tool_input: dict) -> str:
    sym = tool_input.get("symbol", "")
    if tool_name == "get_earnings_history":
        result = get_earnings_history(sym)
    elif tool_name == "get_earnings_calendar":
        result = get_earnings_calendar(sym)
    elif tool_name == "get_balance_sheet_summary":
        result = get_balance_sheet_summary(sym)
    elif tool_name == "get_valuation_metrics":
        result = get_valuation_metrics(sym)
    elif tool_name == "get_short_interest":
        result = get_short_interest(sym)
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)
