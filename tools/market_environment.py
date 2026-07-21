"""
マクロ環境（金利・為替・政治/地政学）を評価し、個別銘柄への影響を
セクター・市場（日本株/米国株）に応じて算出する（無料・yfinanceのみ）。
"""
import numpy as np
import yfinance as yf

from tools.news_feed import get_stock_news


def _num(v):
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _series_change(symbol: str, period: str = "1mo"):
    """指定期間の始値→現在の変化（水準の差と%）。"""
    try:
        h = yf.Ticker(symbol).history(period=period, auto_adjust=True)
        if h is None or h.empty or len(h) < 2:
            return None
        first = float(h["Close"].iloc[0])
        last = float(h["Close"].iloc[-1])
        return {"last": last, "first": first, "diff": last - first,
                "pct": (last - first) / first * 100 if first else 0.0}
    except Exception:
        return None


def get_macro_environment() -> dict:
    """金利・為替・政治リスクの現況を評価してまとめる。"""
    env = {}

    # ── 米10年金利 ──
    tnx = _series_change("^TNX", "1mo")
    if tnx:
        env["rate_10y"] = round(tnx["last"], 2)
        env["rate_change_1m"] = round(tnx["diff"], 2)  # %ポイント
        if tnx["diff"] > 0.15:
            env["rate_trend"] = "上昇"
        elif tnx["diff"] < -0.15:
            env["rate_trend"] = "低下"
        else:
            env["rate_trend"] = "横ばい"

    # ── ドル円 ──
    fx = _series_change("USDJPY=X", "1mo")
    if fx:
        env["usdjpy"] = round(fx["last"], 2)
        env["usdjpy_change_1m_pct"] = round(fx["pct"], 1)
        if fx["pct"] > 1.5:
            env["yen_trend"] = "円安"   # ドル高＝円安
        elif fx["pct"] < -1.5:
            env["yen_trend"] = "円高"
        else:
            env["yen_trend"] = "横ばい"

    # ── VIX（リスク環境） ──
    vix = _series_change("^VIX", "1mo")
    if vix:
        env["vix"] = round(vix["last"], 1)
        env["vix_trend"] = "上昇（警戒）" if vix["diff"] > 2 else ("低下（安心）" if vix["diff"] < -2 else "横ばい")

    # ── 政治・地政学リスク（マクロニュースから推定） ──
    pol_neg, pol_total = 0, 0
    headlines = []
    for proxy in ["SPY", "^GSPC", "DX-Y.NYB"]:
        try:
            nf = get_stock_news(proxy, 8)
            for a in nf.get("articles", []):
                topic = a.get("topic_jp", "")
                if topic in ("【政治・地政学】", "【金利・中銀】"):
                    pol_total += 1
                    if a.get("sentiment") == "悪材料":
                        pol_neg += 1
                    if len(headlines) < 6:
                        headlines.append(a)
        except Exception:
            continue
    env["political_negative_count"] = pol_neg
    env["political_headline_count"] = pol_total
    if pol_neg >= 3:
        env["political_risk"] = "高（悪材料が目立つ）"
    elif pol_neg >= 1:
        env["political_risk"] = "中"
    else:
        env["political_risk"] = "低"
    env["political_headlines"] = headlines

    # ── 総合レジーム ──
    notes = []
    if env.get("rate_trend") == "上昇":
        notes.append("金利上昇（グロース・不動産に逆風、銀行に追い風）")
    elif env.get("rate_trend") == "低下":
        notes.append("金利低下（グロース・不動産に追い風、銀行に逆風）")
    if env.get("yen_trend") == "円安":
        notes.append("円安（日本の輸出企業に追い風、輸入企業に逆風）")
    elif env.get("yen_trend") == "円高":
        notes.append("円高（日本の輸出企業に逆風）")
    if env.get("political_risk", "").startswith("高"):
        notes.append("政治・地政学リスク高（全体的にリスクオフ）")
    env["summary_notes"] = notes

    return env


# セクター別の金利感応度（+1=金利上昇が追い風 / -1=逆風）
RATE_SENSITIVITY = {
    "Financial Services": +1,
    "Technology": -1,
    "Real Estate": -1,
    "Utilities": -1,
    "Communication Services": -1,
    "Consumer Cyclical": -1,
}

# 日本株の円安感応度（+1=円安が追い風＝輸出/海外売上多い / -1=逆風＝輸入依存）
JP_YEN_WEAK_SENSITIVITY = {
    "Consumer Cyclical": +1,   # 自動車など
    "Technology": +1,
    "Industrials": +1,
    "Basic Materials": +1,
    "Consumer Defensive": -1,  # 食品など輸入依存
    "Utilities": -1,           # エネルギー輸入
}


def assess_macro_impact(info: dict, macro: dict) -> dict:
    """
    個別銘柄について、マクロ環境（金利・為替・政治）の影響を評価。
    戻り値: {"score": 合計調整点(-3〜+3), "factors": [説明...]}
    """
    sector = info.get("sector")
    symbol = (info.get("symbol") or "")
    is_jp = str(info.get("_symbol", "")).endswith(".T")
    score = 0
    factors = []

    # ── 金利の影響 ──
    rt = macro.get("rate_trend")
    sens = RATE_SENSITIVITY.get(sector, 0)
    if rt == "上昇" and sens != 0:
        score += sens
        if sens > 0:
            factors.append(f"🏦 金利上昇（10年 {macro.get('rate_10y','')}%）→ {sector}は追い風（利ザヤ改善）")
        else:
            factors.append(f"🏦 金利上昇（10年 {macro.get('rate_10y','')}%）→ {sector}は逆風（割高株・調達コスト増）")
    elif rt == "低下" and sens != 0:
        score -= sens
        if sens > 0:
            factors.append(f"🏦 金利低下 → {sector}（金融）は逆風（利ザヤ縮小）")
        else:
            factors.append(f"🏦 金利低下 → {sector}は追い風（割高株・不動産に有利）")

    # ── 為替の影響 ──
    yt = macro.get("yen_trend")
    if is_jp:
        ysens = JP_YEN_WEAK_SENSITIVITY.get(sector, 0)
        if yt == "円安" and ysens != 0:
            score += ysens
            if ysens > 0:
                factors.append(f"💴 円安（{macro.get('usdjpy','')}円）→ {sector}は追い風（輸出・海外売上の押し上げ）")
            else:
                factors.append(f"💴 円安 → {sector}は逆風（輸入コスト増）")
        elif yt == "円高" and ysens != 0:
            score -= ysens
            if ysens > 0:
                factors.append(f"💴 円高 → {sector}は逆風（輸出採算の悪化）")
            else:
                factors.append(f"💴 円高 → {sector}は追い風（輸入コスト減）")
    else:
        # 米国株を円で保有する日本の投資家目線：円安=円換算の含み益、円高=目減り
        if yt == "円安":
            factors.append(f"💴 円安（{macro.get('usdjpy','')}円）→ 米国株は円換算で有利（為替差益）")
        elif yt == "円高":
            score -= 1
            factors.append(f"💴 円高 → 米国株は円換算で目減り（為替差損に注意）")

    # ── 政治・地政学リスク ──
    if macro.get("political_risk", "").startswith("高"):
        beta = _num(info.get("beta"))
        if beta is not None and beta > 1.3:
            score -= 1
            factors.append("🌍 政治・地政学リスク高＋高ベータ銘柄 → リスクオフ局面で下げやすい")
        else:
            factors.append("🌍 政治・地政学リスク高 → 全体的に神経質な地合い")

    # クランプ
    score = max(-3, min(3, score))
    return {"score": score, "factors": factors}
