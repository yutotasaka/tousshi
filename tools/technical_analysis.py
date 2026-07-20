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


def sell_signal_analysis(ohlcv_data: list[dict]) -> dict:
    """
    売り局面の精度を高める専用分析。
    25日移動平均（日本で一般的）、MACDデッドクロス、RSI、出来高を重視して
    「売りシグナル」を検出し、売り度合いスコア（0〜100、高いほど売り推奨）を返す。
    """
    if not ohlcv_data or len(ohlcv_data) < 26:
        return {"error": "26本以上のデータが必要です"}

    df = pd.DataFrame(ohlcv_data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    def _r(v, d=2):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), d)

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    # 25日移動平均（単純移動平均・日本で一般的）
    sma25 = close.rolling(25).mean()
    sma25_now = float(sma25.iloc[-1])
    sma25_prev = float(sma25.iloc[-2])
    # 乖離率
    disparity25 = (last - sma25_now) / sma25_now * 100 if sma25_now else 0.0
    # 25日線の傾き（下向きか）
    sma25_slope_down = sma25_now < sma25_prev
    # 25日線を上から下に割り込んだか
    broke_below_sma25 = prev >= sma25_prev and last < sma25_now

    # MACD
    macd_line = _ema(close, 12) - _ema(close, 26)
    signal_line = _ema(macd_line, 9)
    hist = macd_line - signal_line
    macd_dead_cross = hist.iloc[-1] < 0 and hist.iloc[-2] >= 0
    macd_below_zero = macd_line.iloc[-1] < 0

    # RSI
    rsi = _rsi(close, 14)
    rsi_now = float(rsi.iloc[-1])
    rsi_prev = float(rsi.iloc[-2])
    rsi_falling_from_high = rsi_prev >= 70 and rsi_now < 70  # 過熱からの反落

    # 出来高
    vol_ma20 = volume.rolling(20).mean()
    vol_ratio = float(volume.iloc[-1]) / float(vol_ma20.iloc[-1]) if vol_ma20.iloc[-1] > 0 else 1.0
    down_day = last < prev
    high_vol_down = down_day and vol_ratio > 1.5  # 出来高を伴った下落＝売り圧力本物

    # ── 売りシグナル収集とスコアリング ──
    sell_signals = []
    score = 0  # 0〜100（高いほど売り）

    if broke_below_sma25:
        score += 25
        sell_signals.append(f"25日移動平均を割り込み（{sma25_now:,.0f}円を下抜け）→ 中期トレンド転換の初動")
    elif last < sma25_now:
        score += 12
        sell_signals.append(f"25日移動平均を下回って推移（乖離{disparity25:+.1f}%）")
    if sma25_slope_down:
        score += 10
        sell_signals.append("25日移動平均が下向き → 下降基調")

    if macd_dead_cross:
        score += 25
        sell_signals.append("MACDデッドクロス発生 → 下落モメンタムへ転換（強い売りサイン）")
    elif macd_below_zero and hist.iloc[-1] < 0:
        score += 12
        sell_signals.append("MACDがゼロ以下かつ下向き → 弱気継続")

    if rsi_now > 75:
        score += 15
        sell_signals.append(f"RSI {rsi_now:.0f}：過熱（利益確定売りが出やすい）")
    elif rsi_falling_from_high:
        score += 18
        sell_signals.append(f"RSIが過熱圏(70+)から反落 {rsi_prev:.0f}→{rsi_now:.0f} → 天井のサイン")

    if high_vol_down:
        score += 20
        sell_signals.append(f"出来高を伴う下落（平均比{vol_ratio:.1f}倍）→ 機関の売り本格化の可能性")
    elif disparity25 > 15:
        score += 10
        sell_signals.append(f"25日線から+{disparity25:.0f}%上方乖離 → 短期的な過熱・調整リスク")

    score = min(100, score)

    if score >= 60:
        level = "🔴 強い売りシグナル"
        summary = "複数の売りサインが重複。利益確定・一部売却を検討する局面"
    elif score >= 35:
        level = "🟠 売り警戒"
        summary = "売りサインが出始めている。新規買いは控え、保有分は要監視"
    elif score >= 15:
        level = "🟡 やや注意"
        summary = "軽微な弱含みサイン。トレンド継続なら保有でも可"
    else:
        level = "🟢 売りサイン乏しい"
        summary = "テクニカル上の売り圧力は限定的"

    return {
        "sell_score": score,
        "level": level,
        "summary": summary,
        "sell_signals": sell_signals,
        "detail": {
            "sma25": _r(sma25_now),
            "disparity25_pct": _r(disparity25),
            "sma25_slope_down": sma25_slope_down,
            "broke_below_sma25": broke_below_sma25,
            "macd_dead_cross": macd_dead_cross,
            "macd_below_zero": macd_below_zero,
            "rsi14": _r(rsi_now),
            "rsi_falling_from_overbought": rsi_falling_from_high,
            "volume_ratio": _r(vol_ratio),
            "high_volume_down_day": high_vol_down,
        },
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
