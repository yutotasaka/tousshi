"""
銘柄選定スクリーニング ＆ 買い時・売り時判定エンジン（無料・yfinanceのみ）

- check_criteria: PER・配当利回り・増配傾向・連続増収・ROE などの選定基準を✅❌判定
- timing_judgment: 過去平均PERとの乖離を軸に、テクニカル・ニュース・決算接近を
  加味して「買い増しゾーン／中立／売り検討」を判定
"""
import numpy as np
import pandas as pd
import yfinance as yf

from tools.market_data import get_price_history
from tools.technical_analysis import run_technical_analysis
from tools.news_feed import get_stock_news


def _num(v):
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# ────────────────────────────────────────────────────────────────────
# 業種別の標準PER目安（yfinanceのsector名がキー）
# 業種によって「安い」の基準は大きく異なるため、絶対値と併用して判定する。
# ────────────────────────────────────────────────────────────────────
SECTOR_PER_BENCHMARK = {
    "Technology": 25.0,
    "Communication Services": 18.0,
    "Consumer Cyclical": 18.0,
    "Consumer Defensive": 20.0,
    "Healthcare": 20.0,
    "Industrials": 17.0,
    "Financial Services": 11.0,
    "Energy": 10.0,
    "Utilities": 15.0,
    "Basic Materials": 12.0,
    "Real Estate": 15.0,
}

SECTOR_JP = {
    "Technology": "テクノロジー",
    "Communication Services": "通信",
    "Consumer Cyclical": "一般消費財",
    "Consumer Defensive": "生活必需品",
    "Healthcare": "ヘルスケア",
    "Industrials": "資本財・工業",
    "Financial Services": "金融",
    "Energy": "エネルギー",
    "Utilities": "公益",
    "Basic Materials": "素材",
    "Real Estate": "不動産",
}


def sector_per_context(info: dict) -> dict:
    """銘柄の業種と、その業種の標準PER目安を返す。"""
    sector = info.get("sector")
    bench = SECTOR_PER_BENCHMARK.get(sector)
    return {
        "sector": sector,
        "sector_jp": SECTOR_JP.get(sector, sector or "不明"),
        "benchmark_per": bench,
    }


# ────────────────────────────────────────────────────────────────────
# 配当の増配ストリーク（配当履歴は長期間取れる）
# ────────────────────────────────────────────────────────────────────
def dividend_streak(ticker) -> dict:
    """年間配当の連続増配年数と10年トレンドを返す。"""
    try:
        div = ticker.dividends
        if div is None or len(div) == 0:
            return {"streak_years": 0, "trend": "配当なし", "annual": []}
        annual = div.groupby(div.index.year).sum()
        # 進行中の年は未確定なので除外（直近が今年なら落とす）
        current_year = pd.Timestamp.now().year
        if len(annual) > 0 and annual.index[-1] == current_year:
            annual = annual.iloc[:-1]
        if len(annual) < 2:
            return {"streak_years": 0, "trend": "履歴が短い", "annual": []}

        vals = annual.values
        years = list(annual.index)
        # 連続増配（前年比で増えた年が何年続いているか）
        streak = 0
        for i in range(len(vals) - 1, 0, -1):
            if vals[i] > vals[i - 1]:
                streak += 1
            else:
                break
        # 10年トレンド
        lookback = min(10, len(vals) - 1)
        past = vals[-lookback - 1]
        now = vals[-1]
        cagr = ((now / past) ** (1 / lookback) - 1) * 100 if past > 0 else None
        cut_years = sum(1 for i in range(len(vals) - lookback, len(vals)) if vals[i] < vals[i - 1])

        if streak >= 5:
            trend = f"{streak}年連続増配（優良）"
        elif streak >= 2:
            trend = f"{streak}年連続増配"
        elif cut_years == 0 and cagr and cagr > 0:
            trend = "増配基調（減配なし）"
        elif cut_years > 0:
            trend = f"過去{lookback}年で減配{cut_years}回あり"
        else:
            trend = "横ばい"

        return {
            "streak_years": streak,
            "cagr_10y_pct": round(cagr, 1) if cagr is not None else None,
            "cut_years_in_10y": cut_years,
            "trend": trend,
            "annual": [{"year": int(y), "dividend": round(float(v), 2)} for y, v in zip(years[-11:], vals[-11:])],
        }
    except Exception as e:
        return {"streak_years": 0, "trend": f"取得エラー: {e}", "annual": []}


# ────────────────────────────────────────────────────────────────────
# 連続増収（yfinanceは年次4期まで。取れる範囲で判定）
# ────────────────────────────────────────────────────────────────────
def revenue_streak(ticker) -> dict:
    try:
        a = ticker.income_stmt
        if a is None or a.empty:
            return {"streak": 0, "available_years": 0, "detail": "データなし"}
        cols = sorted(a.columns)  # 古い→新しい
        revs = []
        for c in cols:
            r = _num(a[c].get("Total Revenue"))
            if r is not None:
                revs.append((c.year, r))
        if len(revs) < 2:
            return {"streak": 0, "available_years": len(revs), "detail": "履歴が短い"}
        streak = 0
        for i in range(len(revs) - 1, 0, -1):
            if revs[i][1] > revs[i - 1][1]:
                streak += 1
            else:
                break
        all_up = streak == len(revs) - 1
        return {
            "streak": streak,
            "available_years": len(revs),
            "all_available_up": all_up,
            "detail": f"取得できた{len(revs)}期中、直近{streak}期連続増収" + ("（全期間増収）" if all_up else ""),
            "revenues": [{"year": y, "revenue": r} for y, r in revs],
        }
    except Exception as e:
        return {"streak": 0, "available_years": 0, "detail": f"取得エラー: {e}"}


# ────────────────────────────────────────────────────────────────────
# 選定基準チェック
# ────────────────────────────────────────────────────────────────────
def check_criteria(
    symbol: str,
    max_per: float = 10.0,
    min_dividend_yield: float = 2.5,
    min_roe: float = 10.0,
    min_dividend_streak: int = 3,
    max_de_ratio: float = 100.0,
    min_op_margin: float = 8.0,
) -> dict:
    """選定基準を1つずつ✅❌判定。"""
    t = yf.Ticker(symbol)
    try:
        info = t.info or {}
    except Exception:
        info = {}

    checks = []

    def add(name, passed, actual, threshold, note=""):
        checks.append({
            "name": name,
            "pass": bool(passed) if passed is not None else None,
            "actual": actual,
            "threshold": threshold,
            "note": note,
        })

    # 1. PER（絶対値）
    per = _num(info.get("trailingPE"))
    add("PER（絶対値）", per is not None and per <= max_per if per is not None else None,
        f"{per:.1f}倍" if per is not None else "取得不可", f"{max_per:.0f}倍以下",
        "利益に対して株価が安いか（業種を問わない絶対基準）")

    # 1b. PER（業種相対）— 業種によって「安い」の基準は違う
    sec = sector_per_context(info)
    bench = sec.get("benchmark_per")
    if per is not None and bench:
        rel = per / bench
        rel_pass = rel <= 0.8  # 業種標準の8割以下なら業種内で割安
        add(f"PER（業種相対：{sec['sector_jp']}）", rel_pass,
            f"{per:.1f}倍（業種標準 {bench:.0f}倍の{rel*100:.0f}%）",
            f"業種標準の80%以下",
            f"{sec['sector_jp']}セクターの標準と比べて安いか")
    else:
        add("PER（業種相対）", None,
            "業種情報なし" if per is not None else "取得不可", "業種標準の80%以下",
            "業種によってPERの適正水準は異なる")

    # 2. 配当利回り
    dy = _num(info.get("dividendYield"))
    add("配当利回り", dy is not None and dy >= min_dividend_yield if dy is not None else None,
        f"{dy:.2f}%" if dy is not None else "配当なし/取得不可", f"{min_dividend_yield:.1f}%以上",
        "持っているだけでもらえる利回り")

    # 3. 増配傾向
    ds = dividend_streak(t)
    streak_ok = ds["streak_years"] >= min_dividend_streak or (
        ds.get("cut_years_in_10y") == 0 and (ds.get("cagr_10y_pct") or 0) > 0)
    add("増配傾向", streak_ok, ds["trend"], f"{min_dividend_streak}年以上連続増配 or 10年減配なし",
        "配当を増やし続けている会社は株主重視")

    # 4. 連続増収
    rs = revenue_streak(t)
    rev_ok = rs.get("all_available_up", False) if rs["available_years"] >= 3 else None
    add("連続増収", rev_ok, rs["detail"],
        "取得可能な全期間で増収（※データは最大4期。10期連続の完全確認は不可）",
        "売上が伸び続けているか")

    # 5. ROE
    roe = _num(info.get("returnOnEquity"))
    roe_pct = roe * 100 if roe is not None else None
    add("ROE（自己資本利益率）", roe_pct is not None and roe_pct >= min_roe if roe_pct is not None else None,
        f"{roe_pct:.1f}%" if roe_pct is not None else "取得不可", f"{min_roe:.0f}%以上",
        "株主のお金でどれだけ効率よく稼ぐか")

    # 6. 財務（D/Eレシオ）
    de = _num(info.get("debtToEquity"))
    add("負債比率（D/E）", de is not None and de <= max_de_ratio if de is not None else None,
        f"{de:.0f}%" if de is not None else "取得不可", f"{max_de_ratio:.0f}%以下",
        "借金が重すぎないか")

    # 7. 営業利益率
    opm = _num(info.get("operatingMargins"))
    opm_pct = opm * 100 if opm is not None else None
    add("営業利益率", opm_pct is not None and opm_pct >= min_op_margin if opm_pct is not None else None,
        f"{opm_pct:.1f}%" if opm_pct is not None else "取得不可", f"{min_op_margin:.0f}%以上",
        "本業でしっかり稼げているか")

    passed = sum(1 for c in checks if c["pass"] is True)
    total = sum(1 for c in checks if c["pass"] is not None)

    if total < 4:
        grade = "判定不可（データ不足）"
    elif passed == total:
        grade = "S（全基準クリア）"
    elif passed >= total - 1:
        grade = "A（ほぼクリア）"
    elif passed >= total * 0.6:
        grade = "B（一部クリア）"
    else:
        grade = "C（基準未達が多い）"

    return {
        "symbol": symbol.upper(),
        "name": info.get("shortName", symbol),
        "checks": checks,
        "passed": passed,
        "total": total,
        "grade": grade,
        "dividend_history": ds.get("annual", []),
    }


# ────────────────────────────────────────────────────────────────────
# 買い時・売り時判定（平均PERバンド方式）
# ────────────────────────────────────────────────────────────────────
def _historical_avg_per(ticker, current_price) -> dict:
    """過去の年次EPSと当時の平均株価から、過去平均PERを近似計算する。"""
    try:
        a = ticker.income_stmt
        if a is None or a.empty:
            return {}
        px = ticker.history(period="5y", auto_adjust=True)
        if px is None or px.empty:
            return {}
        pers = []
        for c in a.columns:
            eps = _num(a[c].get("Diluted EPS"))
            if eps is None or eps <= 0:
                continue
            # その決算期の年の平均株価
            year_px = px[px.index.year == c.year]["Close"]
            if len(year_px) < 10:
                continue
            avg_px = float(year_px.mean())
            pers.append(avg_px / eps)
        if not pers:
            return {}
        return {"avg_per": round(float(np.mean(pers)), 1), "years_used": len(pers)}
    except Exception:
        return {}


def timing_judgment(symbol: str) -> dict:
    """
    平均PERとの乖離を軸に買い時/売り時を判定。
    テクニカル（RSI・トレンド）、ニュース基調、決算接近も加味。
    """
    t = yf.Ticker(symbol)
    try:
        info = t.info or {}
    except Exception:
        info = {}

    current_price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    cur_per = _num(info.get("trailingPE"))
    eps = _num(info.get("trailingEps"))

    result = {
        "symbol": symbol.upper(),
        "current_price": current_price,
        "current_per": round(cur_per, 1) if cur_per else None,
    }

    # ── PERバンド ──
    hist_per = _historical_avg_per(t, current_price)
    avg_per = hist_per.get("avg_per")
    factors = []
    score = 0  # マイナス=買い方向、プラス=売り方向 ではなく、買い=+、売り=-で統一: +が買い時

    if avg_per and cur_per and eps and eps > 0:
        deviation = (cur_per - avg_per) / avg_per * 100
        fair_price = avg_per * eps
        result.update({
            "avg_per": avg_per,
            "per_years_used": hist_per.get("years_used"),
            "deviation_pct": round(deviation, 1),
            "fair_price": round(fair_price, 1),
            "buy_zone_price": round(fair_price * 0.85, 1),   # 平均PER-15%
            "sell_zone_price": round(fair_price * 1.20, 1),  # 平均PER+20%
        })
        if deviation <= -20:
            score += 3
            factors.append(f"PERが過去平均({avg_per}倍)より{-deviation:.0f}%低い → 歴史的に見て大きく割安")
        elif deviation <= -5:
            score += 2
            factors.append(f"PERが過去平均より{-deviation:.0f}%低い → やや割安")
        elif deviation >= 25:
            score -= 3
            factors.append(f"PERが過去平均({avg_per}倍)より{deviation:.0f}%高い → 歴史的に見て割高圏")
        elif deviation >= 10:
            score -= 2
            factors.append(f"PERが過去平均より{deviation:.0f}%高い → やや割高")
        else:
            factors.append(f"PERは過去平均({avg_per}倍)並み → 妥当な水準")
    else:
        factors.append("過去平均PERを計算できず（赤字またはデータ不足）→ テクニカル中心で判定")

    # ── 業種相対PER ──
    sec = sector_per_context(info)
    result["sector_jp"] = sec.get("sector_jp")
    bench = sec.get("benchmark_per")
    if cur_per and bench:
        rel = cur_per / bench
        result["sector_benchmark_per"] = bench
        result["sector_relative_pct"] = round((rel - 1) * 100, 1)
        if rel <= 0.7:
            score += 1
            factors.append(f"業種相対でも割安：{sec['sector_jp']}の標準PER {bench:.0f}倍に対し{cur_per:.1f}倍（{rel*100:.0f}%）")
        elif rel >= 1.4:
            score -= 1
            factors.append(f"業種相対で割高：{sec['sector_jp']}の標準PER {bench:.0f}倍に対し{cur_per:.1f}倍（{rel*100:.0f}%）")
        else:
            factors.append(f"業種内では標準的なPER水準（{sec['sector_jp']}標準 {bench:.0f}倍 vs {cur_per:.1f}倍）")

    # ── テクニカル ──
    hist = get_price_history(symbol, "6mo")
    ta = {}
    if "data" in hist and hist["data"]:
        try:
            ta = run_technical_analysis(hist["data"])
        except Exception:
            ta = {}
    if ta and "error" not in ta:
        rsi = _num(ta.get("rsi14"))
        if rsi is not None:
            if rsi < 35:
                score += 1
                factors.append(f"RSI {rsi:.0f}：売られすぎ（短期反発しやすい水準）")
            elif rsi > 70:
                score -= 1
                factors.append(f"RSI {rsi:.0f}：買われすぎ（短期調整しやすい水準）")
        if ta.get("trend") == "DOWNTREND":
            factors.append("下降トレンド中 → 買うなら分割で（落ちるナイフに注意）")
        result["support"] = ta.get("support_20d")
        result["resistance"] = ta.get("resistance_20d")

    # ── ニュース基調 ──
    news = get_stock_news(symbol, 8)
    if "error" not in news:
        tone = news.get("tone")
        result["news_tone"] = tone
        if tone == "ネガティブ優勢":
            factors.append("直近ニュースはネガティブ優勢 → 悪材料の内容を確認してから")
            score -= 1
        elif tone == "ポジティブ優勢":
            factors.append("直近ニュースはポジティブ優勢")
            score += 1
        result["news"] = news.get("articles", [])[:5]

    # ── 決算接近 ──
    try:
        cal = t.calendar
        if isinstance(cal, dict) and cal.get("Earnings Date"):
            ed = cal["Earnings Date"][0]
            ed_ts = pd.Timestamp(ed)
            days = (ed_ts - pd.Timestamp.now()).days
            result["next_earnings"] = str(ed)
            if 0 <= days <= 14:
                factors.append(f"⚠️ {days}日後に決算発表 → 結果次第で大きく動く。直前の新規買いはリスク高")
    except Exception:
        pass

    # ── 総合判定 ──
    if score >= 3:
        verdict = "🟢 買い増しゾーン"
        advice = "割安圏。分割して買い下がるのに適した水準"
    elif score >= 1:
        verdict = "🟡 押し目買い検討"
        advice = "やや割安。急がず指値で拾う水準"
    elif score <= -3:
        verdict = "🔴 売り検討ゾーン"
        advice = "割高圏。利益確定や一部売却を検討する水準"
    elif score <= -1:
        verdict = "🟠 高値警戒"
        advice = "やや割高。新規買いは控え、保有分は様子見"
    else:
        verdict = "⚪ 中立（ホールド）"
        advice = "割安でも割高でもない。保有継続・様子見が基本"

    result.update({
        "score": score,
        "verdict": verdict,
        "advice": advice,
        "factors": factors,
        "disclaimer": "過去データに基づく機械的判定です。投資判断はご自身の責任でお願いします。",
    })
    return result
