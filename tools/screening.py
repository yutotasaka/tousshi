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
from tools.technical_analysis import run_technical_analysis, sell_signal_analysis
from tools.fundamentals import get_earnings_calendar
from tools.news_feed import get_stock_news
from tools.market_environment import get_macro_environment, assess_macro_impact


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
    min_dividend_yield: float = 3.0,
    min_roe: float = 10.0,
    min_dividend_streak: int = 3,
    max_de_ratio: float = 100.0,
    min_op_margin: float = 8.0,
    max_payout_ratio: float = 60.0,
    min_rev_growth: float = 3.0,
    min_earnings_growth: float = 0.0,
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

    # 5. 配当性向（低め＝無理なく配当を払えている＝増配余力がある）
    payout = _num(info.get("payoutRatio"))
    payout_pct = payout * 100 if payout is not None else None
    add("配当性向", payout_pct is not None and 0 < payout_pct <= max_payout_ratio if payout_pct is not None else None,
        f"{payout_pct:.0f}%" if payout_pct is not None else "取得不可", f"{max_payout_ratio:.0f}%以下",
        "利益のうち配当に回す割合。低いほど減配リスクが小さく増配余力が大きい")

    # 6. ROE
    roe = _num(info.get("returnOnEquity"))
    roe_pct = roe * 100 if roe is not None else None
    add("ROE（自己資本利益率）", roe_pct is not None and roe_pct >= min_roe if roe_pct is not None else None,
        f"{roe_pct:.1f}%" if roe_pct is not None else "取得不可", f"{min_roe:.0f}%以上",
        "株主のお金でどれだけ効率よく稼ぐか")

    # 7. 業績（増益）
    eg = _num(info.get("earningsGrowth"))
    eg_pct = eg * 100 if eg is not None else None
    add("業績（利益成長）", eg_pct is not None and eg_pct >= min_earnings_growth if eg_pct is not None else None,
        f"前年比{eg_pct:+.1f}%" if eg_pct is not None else "取得不可", f"前年比{min_earnings_growth:+.0f}%以上",
        "利益が伸びているか（減益なら減配・株価下落リスク）")

    # 8. 成長性（増収率）
    rg = _num(info.get("revenueGrowth"))
    rg_pct = rg * 100 if rg is not None else None
    add("成長性（増収率）", rg_pct is not None and rg_pct >= min_rev_growth if rg_pct is not None else None,
        f"前年比{rg_pct:+.1f}%" if rg_pct is not None else "取得不可", f"前年比{min_rev_growth:+.0f}%以上",
        "売上が伸びているか（成長の源泉）")

    # 9. 財務健全性（D/Eレシオ）
    de = _num(info.get("debtToEquity"))
    add("財務健全性（負債比率D/E）", de is not None and de <= max_de_ratio if de is not None else None,
        f"{de:.0f}%" if de is not None else "取得不可", f"{max_de_ratio:.0f}%以下",
        "借金が重すぎないか")

    # 10. 財務健全性（流動比率）
    cr = _num(info.get("currentRatio"))
    add("財務健全性（流動比率）", cr is not None and cr >= 1.2 if cr is not None else None,
        f"{cr:.2f}" if cr is not None else "取得不可", "1.2以上",
        "短期の支払い能力（1未満は資金繰りに注意）")

    # 11. 営業利益率
    opm = _num(info.get("operatingMargins"))
    opm_pct = opm * 100 if opm is not None else None
    add("営業利益率", opm_pct is not None and opm_pct >= min_op_margin if opm_pct is not None else None,
        f"{opm_pct:.1f}%" if opm_pct is not None else "取得不可", f"{min_op_margin:.0f}%以上",
        "本業でしっかり稼げているか")

    # 12. アナリスト・レーティング評価
    rec = (info.get("recommendationKey") or "").lower()
    n_analysts = info.get("numberOfAnalystOpinions") or 0
    tgt = _num(info.get("targetMeanPrice"))
    price_now = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    rec_jp = {
        "strong_buy": "強気買い", "buy": "買い", "hold": "中立",
        "underperform": "弱気", "sell": "売り",
    }.get(rec, rec or "評価なし")
    upside = None
    if tgt and price_now:
        upside = (tgt - price_now) / price_now * 100
    if n_analysts >= 3 and rec:
        rating_ok = rec in ("strong_buy", "buy") and (upside is None or upside > 0)
        actual = f"{rec_jp}（{n_analysts}名）"
        if upside is not None:
            actual += f"／目標株価まで{upside:+.0f}%"
        add("アナリスト評価", rating_ok, actual,
            "買い推奨 かつ 目標株価に上値余地",
            "プロのアナリストの評価と目標株価との差")
    else:
        add("アナリスト評価", None,
            f"カバレッジ僅少（{n_analysts}名）" if rec else "評価なし",
            "買い推奨 かつ 目標株価に上値余地",
            "アナリストが少ない銘柄は情報が限られる点に注意")

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

    # ── 妥当PERの算出（3要素ブレンド） ──
    # ① 過去平均PER（その銘柄自身の歴史）
    # ② 業種標準PER（セクターによって適正水準は違う）
    # ③ 成長力PER（利益成長率が高い銘柄ほど高いPERが正当化される）
    hist_per = _historical_avg_per(t, current_price)
    avg_per = hist_per.get("avg_per")
    factors = []
    score = 0  # +が買い方向、-が売り方向

    sec = sector_per_context(info)
    result["sector_jp"] = sec.get("sector_jp")
    bench = sec.get("benchmark_per")

    # 成長力PER：利益成長率%をそのままPER目安に（PEG=1相当）。8〜28倍にクランプ
    eg = _num(info.get("earningsGrowth"))
    rg = _num(info.get("revenueGrowth"))
    growth_pct = (eg * 100) if eg is not None else ((rg * 100) if rg is not None else None)
    growth_per = None
    if growth_pct is not None:
        growth_per = max(8.0, min(28.0, growth_pct)) if growth_pct > 0 else 8.0

    # ブレンド（利用可能な要素だけで加重平均）
    components = []
    if avg_per:
        components.append(("過去平均", avg_per, 0.5))
    if bench:
        components.append(("業種標準", bench, 0.3))
    if growth_per:
        components.append(("成長力", growth_per, 0.2))

    fair_per = None
    if components:
        wsum = sum(w for _, _, w in components)
        fair_per = round(sum(v * w for _, v, w in components) / wsum, 1)
        result["fair_per"] = fair_per
        result["fair_per_components"] = {name: v for name, v, _ in components}
        result["avg_per"] = avg_per
        result["per_years_used"] = hist_per.get("years_used")
        result["sector_benchmark_per"] = bench
        result["growth_per"] = growth_per
        comp_txt = "・".join(f"{n}{v:.0f}倍" for n, v, _ in components)
        factors.append(f"妥当PER {fair_per}倍（{comp_txt} のブレンド）")

    if fair_per and cur_per and eps and eps > 0:
        deviation = (cur_per - fair_per) / fair_per * 100
        fair_price = fair_per * eps
        result.update({
            "deviation_pct": round(deviation, 1),
            "fair_price": round(fair_price, 1),
            "buy_zone_price": round(fair_price * 0.85, 1),   # 妥当PER-15%
            "sell_zone_price": round(fair_price * 1.20, 1),  # 妥当PER+20%
        })
        if deviation <= -20:
            score += 3
            factors.append(f"現在PER {cur_per:.1f}倍は妥当PERより{-deviation:.0f}%低い → 大きく割安")
        elif deviation <= -5:
            score += 2
            factors.append(f"現在PERは妥当PERより{-deviation:.0f}%低い → やや割安")
        elif deviation >= 25:
            score -= 3
            factors.append(f"現在PER {cur_per:.1f}倍は妥当PERより{deviation:.0f}%高い → 割高圏")
        elif deviation >= 10:
            score -= 2
            factors.append(f"現在PERは妥当PERより{deviation:.0f}%高い → やや割高")
        else:
            factors.append("現在PERは妥当PER並み → 価格は適正水準")
    else:
        factors.append("妥当PERを算出できず（赤字またはデータ不足）→ テクニカル中心で判定")

    # 参考：個別の視点も表示
    if cur_per and avg_per:
        d1 = (cur_per - avg_per) / avg_per * 100
        factors.append(f"　└ 自社の過去平均{avg_per}倍と比べて {d1:+.0f}%")
    if cur_per and bench:
        d2 = (cur_per - bench) / bench * 100
        result["sector_relative_pct"] = round(d2, 1)
        factors.append(f"　└ {sec['sector_jp']}の業種標準{bench:.0f}倍と比べて {d2:+.0f}%")
    if cur_per and growth_per:
        factors.append(f"　└ 利益成長率から見た目安{growth_per:.0f}倍と比べて {(cur_per-growth_per)/growth_per*100:+.0f}%")

    # ── テクニカル ──
    hist = get_price_history(symbol, "6mo")
    ta = {}
    if "data" in hist and hist["data"]:
        try:
            ta = run_technical_analysis(hist["data"])
        except Exception:
            ta = {}
    if ta and "error" not in ta:
        # トレンドは必ず明示する
        if ta.get("trend") == "UPTREND":
            result["trend"] = "上昇トレンド"
            factors.append("📈 テクニカル：上昇トレンド（株価が20日移動平均の上）")
        else:
            result["trend"] = "下降トレンド"
            factors.append("📉 テクニカル：下降トレンド（株価が20日移動平均の下）→ 買うなら分割で（落ちるナイフに注意）")
        rsi = _num(ta.get("rsi14"))
        if rsi is not None:
            result["rsi"] = round(rsi, 0)
            if rsi < 35:
                score += 1
                factors.append(f"RSI {rsi:.0f}：売られすぎ（短期反発しやすい水準）")
            elif rsi > 70:
                score -= 1
                factors.append(f"RSI {rsi:.0f}：買われすぎ（短期調整しやすい水準）")
        result["support"] = ta.get("support_20d")
        result["resistance"] = ta.get("resistance_20d")
    else:
        result["trend"] = "判定不可"
        factors.append("テクニカル：価格データを取得できずトレンド判定不可")

    # ── 売りシグナル専用分析（25日線・MACDデッドクロス・RSI・出来高） ──
    sell = {}
    if "data" in hist and hist["data"]:
        try:
            sell = sell_signal_analysis(hist["data"])
        except Exception:
            sell = {}
    if sell and "error" not in sell:
        result["sell_signal"] = sell
        ss = sell.get("sell_score", 0)
        # 売りシグナルスコアを総合スコアに反映（強いほど売り方向＝マイナス）
        if ss >= 60:
            score -= 3
        elif ss >= 35:
            score -= 2
        elif ss >= 15:
            score -= 1
        if sell.get("sell_signals"):
            factors.append(f"【売りシグナル分析】{sell.get('level','')}（売り度 {ss}/100）")
            for s in sell["sell_signals"]:
                factors.append(f"　└ {s}")

    # ── アナリスト・レーティング ──
    rec = (info.get("recommendationKey") or "").lower()
    n_analysts = info.get("numberOfAnalystOpinions") or 0
    tgt = _num(info.get("targetMeanPrice"))
    if n_analysts >= 3 and rec:
        rec_jp = {"strong_buy": "強気買い", "buy": "買い", "hold": "中立",
                  "underperform": "弱気", "sell": "売り"}.get(rec, rec)
        upside_txt = ""
        if tgt and current_price:
            up = (tgt - current_price) / current_price * 100
            upside_txt = f"、目標株価 {tgt:,.0f}（{up:+.0f}%）"
            result["analyst_target"] = round(tgt, 1)
            result["analyst_upside_pct"] = round(up, 1)
            if up > 15:
                score += 1
            elif up < -5:
                score -= 1
        result["analyst_rating"] = rec_jp
        result["analyst_count"] = n_analysts
        if rec in ("strong_buy", "buy"):
            factors.append(f"🏦 アナリスト評価：{rec_jp}（{n_analysts}名{upside_txt}）")
        elif rec in ("sell", "underperform"):
            score -= 1
            factors.append(f"🏦 アナリスト評価：{rec_jp}（{n_analysts}名{upside_txt}）→ プロは弱気")
        else:
            factors.append(f"🏦 アナリスト評価：{rec_jp}（{n_analysts}名{upside_txt}）")

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

    # ── 決算：接近＋業績動向 ──
    eg_pct = (eg * 100) if eg is not None else None
    if eg_pct is not None:
        if eg_pct < -10:
            score -= 2
            factors.append(f"📉 決算：直近の利益成長が {eg_pct:+.0f}%（減益）→ 売り材料")
        elif eg_pct < 0:
            score -= 1
            factors.append(f"📉 決算：直近の利益成長が {eg_pct:+.0f}%（小幅減益）")
    try:
        ecal = get_earnings_calendar(symbol)
        if isinstance(ecal, dict) and "error" not in ecal:
            # 過去サプライズ：連続で下回っていれば売り材料
            sp = ecal.get("past_surprises", [])
            valid = [s for s in sp if _num(s.get("surprise_pct")) is not None]
            if valid:
                recent = valid[-1]
                rsp = _num(recent.get("surprise_pct"))
                if rsp is not None and rsp < 0:
                    score -= 1
                    factors.append(f"📉 決算：直近決算は予想を{abs(rsp):.0f}%下回った（ネガティブサプライズ）")
                misses = sum(1 for s in valid if _num(s.get("surprise_pct")) < 0)
                if len(valid) >= 2 and misses == len(valid):
                    score -= 1
                    factors.append(f"📉 決算：直近{len(valid)}回連続で予想未達 → 業績モメンタム悪化")
            # 決算接近
            if ecal.get("next_earnings_dates"):
                ed = ecal["next_earnings_dates"][0]
                result["next_earnings"] = str(ed)
                try:
                    days = (pd.Timestamp(ed) - pd.Timestamp.now()).days
                    if 0 <= days <= 14:
                        factors.append(f"⚠️ {days}日後に決算発表 → 結果次第で急変。保有分は決算跨ぎの是非を検討")
                except Exception:
                    pass
    except Exception:
        pass

    # ── マクロ環境（金利・為替・政治）の影響 ──
    try:
        macro = get_macro_environment()
        macro_info = dict(info)
        macro_info["_symbol"] = symbol
        mi = assess_macro_impact(macro_info, macro)
        score += mi["score"]
        result["macro_score"] = mi["score"]
        result["macro_env"] = {
            "rate_10y": macro.get("rate_10y"),
            "rate_trend": macro.get("rate_trend"),
            "usdjpy": macro.get("usdjpy"),
            "yen_trend": macro.get("yen_trend"),
            "political_risk": macro.get("political_risk"),
            "vix": macro.get("vix"),
        }
        if mi["factors"]:
            factors.append(f"【マクロ環境の影響】（調整 {mi['score']:+d}）")
            for f in mi["factors"]:
                factors.append(f"　└ {f}")
    except Exception:
        pass

    # ── 総合判定（売りシグナル分析を優先的に反映） ──
    sell_score = result.get("sell_signal", {}).get("sell_score", 0)

    # テクニカルの売り圧力が非常に強い場合は割安でも売り警戒を優先
    if sell_score >= 60 and score > -3:
        verdict = "🔴 売り検討ゾーン（テクニカル悪化）"
        advice = "割安でもテクニカルの売りサインが多数。戻り売り・一部利確を検討"
    elif score >= 3:
        verdict = "🟢 買い増しゾーン"
        advice = "割安圏。分割して買い下がるのに適した水準"
    elif score >= 1:
        verdict = "🟡 押し目買い検討"
        advice = "やや割安。急がず指値で拾う水準"
    elif score <= -3:
        verdict = "🔴 売り検討ゾーン"
        advice = "割高＋テクニカル悪化。利益確定や一部売却を検討する水準"
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
