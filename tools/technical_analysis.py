import json
import numpy as np
import pandas as pd


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def run_technical_analysis(ohlcv_data: list[dict]) -> dict:
    """
    Compute technical indicators from OHLCV data (list of dicts with date/open/high/low/close/volume).
    Returns a summary dict with indicators and signals for institutional analysis.
    """
    if not ohlcv_data or len(ohlcv_data) < 20:
        return {"error": "Need at least 20 bars of data"}

    df = pd.DataFrame(ohlcv_data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Moving averages
    ma5 = _ema(close, 5)
    ma20 = _ema(close, 20)
    ma50 = _ema(close, 50) if len(df) >= 50 else None
    ma200 = _ema(close, 200) if len(df) >= 200 else None

    # RSI
    rsi14 = _rsi(close, 14)

    # MACD
    macd_line = _ema(close, 12) - _ema(close, 26)
    signal_line = _ema(macd_line, 9)
    histogram = macd_line - signal_line

    # Bollinger Bands (20, 2)
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # ATR (14)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr14 = tr.ewm(span=14, adjust=False).mean()

    # Volume analysis
    vol_ma20 = volume.rolling(20).mean()

    # Support / Resistance: 20-day high/low
    resistance = high.rolling(20).max().iloc[-1]
    support = low.rolling(20).min().iloc[-1]

    last = close.iloc[-1]

    def _r(v, decimals=2):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), decimals)

    last_ma50 = _r(ma50.iloc[-1]) if ma50 is not None else None
    last_ma200 = _r(ma200.iloc[-1]) if ma200 is not None else None

    # Trend strength
    trend = "UPTREND" if last > _r(ma20.iloc[-1], 4) else "DOWNTREND"
    if ma50 is not None:
        golden_cross = ma20.iloc[-1] > ma50.iloc[-1] and ma20.iloc[-2] <= ma50.iloc[-2]
        death_cross = ma20.iloc[-1] < ma50.iloc[-1] and ma20.iloc[-2] >= ma50.iloc[-2]
    else:
        golden_cross = death_cross = False

    # BB position
    bb_u = bb_upper.iloc[-1]
    bb_l = bb_lower.iloc[-1]
    bb_pct = (last - bb_l) / (bb_u - bb_l) * 100 if (bb_u - bb_l) != 0 else 50

    # Volume surge
    vol_ratio = float(volume.iloc[-1]) / float(vol_ma20.iloc[-1]) if vol_ma20.iloc[-1] > 0 else 1.0

    signals = []
    rsi_val = float(rsi14.iloc[-1])
    if rsi_val > 70:
        signals.append("RSI過買い(>70): 短期過熱注意")
    elif rsi_val < 30:
        signals.append("RSI過売り(<30): 短期反発の可能性")
    if histogram.iloc[-1] > 0 and histogram.iloc[-2] <= 0:
        signals.append("MACDゴールデンクロス: 上昇モメンタム転換")
    elif histogram.iloc[-1] < 0 and histogram.iloc[-2] >= 0:
        signals.append("MACDデッドクロス: 下落モメンタム転換")
    if golden_cross:
        signals.append("MA20/50ゴールデンクロス: 中期強気転換")
    if death_cross:
        signals.append("MA20/50デッドクロス: 中期弱気転換")
    if bb_pct > 90:
        signals.append("ボリンジャーバンド上限付近: 短期調整リスク")
    elif bb_pct < 10:
        signals.append("ボリンジャーバンド下限付近: バウンス候補")
    if vol_ratio > 2.0:
        signals.append(f"出来高急増(平均比{vol_ratio:.1f}倍): 機関投資家の参入可能性")

    return {
        "last_price": _r(last, 4),
        "moving_averages": {
            "ema5": _r(ma5.iloc[-1], 4),
            "ema20": _r(ma20.iloc[-1], 4),
            "ema50": last_ma50,
            "ema200": last_ma200,
        },
        "rsi14": _r(rsi14.iloc[-1]),
        "macd": {
            "macd_line": _r(macd_line.iloc[-1], 4),
            "signal_line": _r(signal_line.iloc[-1], 4),
            "histogram": _r(histogram.iloc[-1], 4),
        },
        "bollinger_bands": {
            "upper": _r(bb_upper.iloc[-1], 4),
            "middle": _r(bb_mid.iloc[-1], 4),
            "lower": _r(bb_lower.iloc[-1], 4),
            "pct_b": _r(bb_pct),
        },
        "atr14": _r(atr14.iloc[-1], 4),
        "volume_ratio_vs_ma20": _r(vol_ratio),
        "support_20d": _r(support, 4),
        "resistance_20d": _r(resistance, 4),
        "trend": trend,
        "signals": signals,
        "bars_analyzed": len(df),
    }


TECHNICAL_ANALYSIS_TOOL = {
    "name": "run_technical_analysis",
    "description": (
        "Compute technical indicators (RSI, MACD, Bollinger Bands, EMA, ATR, volume analysis, "
        "support/resistance) from OHLCV data fetched by get_price_history. "
        "Use this after fetching price history to get quantitative signals."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ohlcv_data": {
                "type": "array",
                "description": "Array of OHLCV records from get_price_history (the 'data' field)",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "open": {"type": "number"},
                        "high": {"type": "number"},
                        "low": {"type": "number"},
                        "close": {"type": "number"},
                        "volume": {"type": "number"},
                    },
                },
            }
        },
        "required": ["ohlcv_data"],
    },
}


def dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "run_technical_analysis":
        result = run_technical_analysis(tool_input["ohlcv_data"])
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)
