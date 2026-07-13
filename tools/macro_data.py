import json
import numpy as np
import yfinance as yf

# Curated macro universe
FX_PAIRS = {
    "USDJPY=X": "ドル円",
    "EURUSD=X": "ユーロドル",
    "GBPUSD=X": "ポンドドル",
    "AUDUSD=X": "豪ドル米ドル",
    "USDCNY=X": "ドル人民元",
    "USDKRW=X": "ドルウォン",
    "USDMXN=X": "ドルペソ",
    "DX-Y.NYB": "ドル指数(DXY)",
}

RATES = {
    "^IRX": "米3ヶ月金利",
    "^FVX": "米5年金利",
    "^TNX": "米10年金利",
    "^TYX": "米30年金利",
}

GLOBAL_INDICES = {
    "^GSPC": "S&P500(米)",
    "^N225": "日経225(日)",
    "^GDAXI": "DAX(独)",
    "^FTSE": "FTSE100(英)",
    "^FCHI": "CAC40(仏)",
    "000001.SS": "上海総合(中)",
    "^HSI": "ハンセン(香港)",
    "^KS11": "KOSPI(韓)",
    "^NSEI": "NIFTY50(印)",
    "^BVSP": "ボベスパ(伯)",
}

COMMODITIES = {
    "CL=F": "WTI原油",
    "BZ=F": "ブレント原油",
    "GC=F": "金",
    "SI=F": "銀",
    "HG=F": "銅",
    "NG=F": "天然ガス",
    "ZW=F": "小麦",
}


def _fetch_group(symbols_map: dict) -> list[dict]:
    out = []
    for sym, label in symbols_map.items():
        try:
            hist = yf.Ticker(sym).history(period="5d", auto_adjust=True)
            if len(hist) >= 2:
                last = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
                week_ago = float(hist["Close"].iloc[0])
                out.append({
                    "symbol": sym,
                    "label": label,
                    "price": round(last, 4),
                    "change_1d_pct": round((last - prev) / prev * 100, 2) if prev else None,
                    "change_5d_pct": round((last - week_ago) / week_ago * 100, 2) if week_ago else None,
                })
            else:
                out.append({"symbol": sym, "label": label, "error": "insufficient data"})
        except Exception as e:
            out.append({"symbol": sym, "label": label, "error": str(e)})
    return out


def get_global_macro_snapshot(categories: list[str] | None = None) -> dict:
    """
    Fetch FX pairs, US treasury yields, global equity indices, and commodities.
    categories: subset of ["fx", "rates", "indices", "commodities"]; None = all.
    """
    cats = categories or ["fx", "rates", "indices", "commodities"]
    result = {}
    if "fx" in cats:
        result["fx"] = _fetch_group(FX_PAIRS)
    if "rates" in cats:
        result["us_treasury_yields"] = _fetch_group(RATES)
    if "indices" in cats:
        result["global_indices"] = _fetch_group(GLOBAL_INDICES)
    if "commodities" in cats:
        result["commodities"] = _fetch_group(COMMODITIES)
    return result


GLOBAL_MACRO_TOOL = {
    "name": "get_global_macro_snapshot",
    "description": (
        "Get a global macro snapshot: major FX pairs (USDJPY, EURUSD, USDCNY, DXY etc.), "
        "US treasury yields (3M/5Y/10Y/30Y), global equity indices (US, Japan, Germany, UK, "
        "China, Hong Kong, Korea, India, Brazil), and commodities (oil, gold, copper, wheat). "
        "Includes 1-day and 5-day changes. Use this to assess global risk sentiment, "
        "currency trends, and cross-country capital flows. "
        "Optionally filter with categories: fx, rates, indices, commodities."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": ["fx", "rates", "indices", "commodities"]},
                "description": "Subset of categories to fetch. Omit for all.",
            }
        },
    },
}


def dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_global_macro_snapshot":
        result = get_global_macro_snapshot(tool_input.get("categories"))
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)
