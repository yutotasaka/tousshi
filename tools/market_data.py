import json
from datetime import datetime
import yfinance as yf
import pandas as pd


def get_market_snapshot(symbols: list[str]) -> dict:
    """Fetch current price, change, volume for a list of symbols."""
    results = {}
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            info = ticker.fast_info
            hist = ticker.history(period="2d", auto_adjust=True)
            if len(hist) >= 2:
                prev_close = hist["Close"].iloc[-2]
                last_close = hist["Close"].iloc[-1]
                change_pct = (last_close - prev_close) / prev_close * 100
                volume = hist["Volume"].iloc[-1]
                results[sym] = {
                    "price": round(float(last_close), 4),
                    "prev_close": round(float(prev_close), 4),
                    "change_pct": round(float(change_pct), 2),
                    "volume": int(volume),
                    "date": hist.index[-1].strftime("%Y-%m-%d"),
                }
            else:
                results[sym] = {"error": "insufficient data"}
        except Exception as e:
            results[sym] = {"error": str(e)}
    return results


def get_price_history(symbol: str, period: str = "3mo") -> dict:
    """Fetch OHLCV history for a symbol. period: 1mo, 3mo, 6mo, 1y, 2y."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, auto_adjust=True)
        if hist.empty:
            return {"error": f"No data for {symbol}"}
        records = []
        for date, row in hist.iterrows():
            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            })
        return {"symbol": symbol, "period": period, "data": records}
    except Exception as e:
        return {"error": str(e)}


# Tool definitions for Claude API
MARKET_SNAPSHOT_TOOL = {
    "name": "get_market_snapshot",
    "description": (
        "Get current market prices, daily change %, and volume for a list of tickers. "
        "Use this to quickly survey market conditions across indices, sectors, bonds, FX, crypto, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of Yahoo Finance ticker symbols (e.g. ['^GSPC', 'AAPL', 'TLT'])",
            }
        },
        "required": ["symbols"],
    },
}

PRICE_HISTORY_TOOL = {
    "name": "get_price_history",
    "description": (
        "Get OHLCV price history for a single ticker. "
        "Use this before running technical analysis to obtain raw candlestick data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Yahoo Finance ticker symbol"},
            "period": {
                "type": "string",
                "enum": ["1mo", "3mo", "6mo", "1y", "2y"],
                "description": "Lookback period",
            },
        },
        "required": ["symbol"],
    },
}


def dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_market_snapshot":
        result = get_market_snapshot(tool_input["symbols"])
    elif tool_name == "get_price_history":
        result = get_price_history(tool_input["symbol"], tool_input.get("period", "3mo"))
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)
