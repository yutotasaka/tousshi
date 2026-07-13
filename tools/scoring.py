"""
無料のルールベース総合評価エンジン。
テクニカル・ファンダメンタルズ・空売り需給・アナリスト・ニュースを統合し、
総合スコア／1ヶ月見通し／好材料・悪材料を算出する。

※これは機械的なスコアリングであり、将来を保証する予想ではありません。
  投資判断の補助として使ってください。
"""
import yfinance as yf

from tools.market_data import get_price_history
from tools.technical_analysis import run_technical_analysis
from tools.fundamentals import (
    get_valuation_metrics,
    get_earnings_calendar,
    get_short_interest,
    get_balance_sheet_summary,
)
from tools.news_feed import get_stock_news


def _num(v):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def evaluate_stock(symbol: str) -> dict:
    """銘柄を多面的に採点して総合評価を返す。"""
    positives: list[str] = []
    negatives: list[str] = []
    sub = {}  # サブスコア（-100〜+100の相対）

    # ── データ収集 ──
    hist = get_price_history(symbol, "6mo")
    ta = run_technical_analysis(hist["data"]) if "data" in hist and hist["data"] else {}
    val = get_valuation_metrics(symbol)
    short = get_short_interest(symbol)
    cal = get_earnings_calendar(symbol)
    news = get_stock_news(symbol, 10)
    bs = get_balance_sheet_summary(symbol)
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}

    # ══════════ 1. テクニカル ══════════
    tscore = 0
    if ta and "error" not in ta:
        if ta.get("trend") == "UPTREND":
            tscore += 25; positives.append("株価は上昇トレンド（20日EMA上）")
        else:
            tscore -= 25; negatives.append("株価は下降トレンド（20日EMA下）")

        rsi = _num(ta.get("rsi14"))
        if rsi is not None:
            if rsi > 70:
                tscore -= 15; negatives.append(f"RSI {rsi:.0f}：短期的に買われすぎ（過熱・調整リスク）")
            elif rsi < 30:
                tscore += 10; positives.append(f"RSI {rsi:.0f}：売られすぎ（反発余地）")
            elif 45 <= rsi <= 60:
                tscore += 5

        macd = ta.get("macd", {})
        hist_v = _num(macd.get("histogram"))
        if hist_v is not None:
            if hist_v > 0:
                tscore += 15; positives.append("MACDが上向き（モメンタム良好）")
            else:
                tscore -= 15; negatives.append("MACDが下向き（モメンタム弱い）")

        ma = ta.get("moving_averages", {})
        last = _num(ta.get("last_price"))
        ema50 = _num(ma.get("ema50"))
        if last and ema50:
            if last > ema50:
                tscore += 10; positives.append("50日移動平均を上回る（中期上昇基調）")
            else:
                tscore -= 10; negatives.append("50日移動平均を下回る（中期弱含み）")

        for sig in ta.get("signals", []):
            if "ゴールデンクロス" in sig:
                tscore += 10; positives.append(f"テクニカル：{sig}")
            elif "デッドクロス" in sig:
                tscore -= 10; negatives.append(f"テクニカル：{sig}")
    sub["technical"] = max(-100, min(100, tscore))

    # ══════════ 2. ファンダメンタルズ（バリュエーション・成長・収益性） ══════════
    fscore = 0
    if val and "error" not in val:
        v = val.get("valuation", {})
        g = val.get("growth", {})
        p = val.get("profitability", {})
        fh = val.get("financial_health", {})

        peg = _num(v.get("peg_ratio"))
        if peg is not None and peg > 0:
            if peg < 1:
                fscore += 20; positives.append(f"PEG {peg:.2f}：成長に対して割安")
            elif peg > 2.5:
                fscore -= 15; negatives.append(f"PEG {peg:.2f}：成長に対して割高")

        rev_g = _num(g.get("revenue_growth_yoy_pct"))
        if rev_g is not None:
            if rev_g > 15:
                fscore += 20; positives.append(f"売上成長 +{rev_g:.0f}%（高成長）")
            elif rev_g < 0:
                fscore -= 20; negatives.append(f"売上成長 {rev_g:.0f}%（減収）")
            elif rev_g > 5:
                fscore += 8

        roe = _num(p.get("roe_pct"))
        if roe is not None:
            if roe > 15:
                fscore += 15; positives.append(f"ROE {roe:.0f}%（高い資本効率）")
            elif roe < 5:
                fscore -= 10; negatives.append(f"ROE {roe:.0f}%（資本効率が低い）")

        opm = _num(p.get("operating_margin_pct"))
        if opm is not None:
            if opm > 20:
                fscore += 10; positives.append(f"営業利益率 {opm:.0f}%（高収益）")
            elif opm < 0:
                fscore -= 15; negatives.append(f"営業利益率 {opm:.0f}%（営業赤字）")

        de = _num(fh.get("debt_to_equity"))
        if de is not None and de > 200:
            fscore -= 10; negatives.append(f"D/Eレシオ {de:.0f}（負債が重い）")
    sub["fundamental"] = max(-100, min(100, fscore))

    # ══════════ 3. 需給（空売り） ══════════
    sscore = 0
    if short and "error" not in short:
        spf = _num(short.get("short_pct_of_float"))
        chg = _num(short.get("shares_short_change_pct"))
        if spf is not None:
            if spf > 15:
                sscore -= 10; negatives.append(f"空売り比率 {spf:.1f}%：弱気ポジション多い（ただし踏み上げ余地も）")
            elif spf > 8:
                sscore -= 5; negatives.append(f"空売り比率 {spf:.1f}%：やや弱気")
            elif spf < 3:
                sscore += 5; positives.append(f"空売り比率 {spf:.1f}%：売り圧力は限定的")
        if chg is not None:
            if chg > 10:
                sscore -= 10; negatives.append(f"空売り残高が前月比 +{chg:.0f}%（機関の弱気が増加）")
            elif chg < -10:
                sscore += 10; positives.append(f"空売り残高が前月比 {chg:.0f}%（弱気ポジション縮小＝買い戻し）")
    sub["supply_demand"] = max(-100, min(100, sscore))

    # ══════════ 4. アナリスト ══════════
    ascore = 0
    analyst = {}
    if val and "error" not in val:
        # get_valuation_metrics には目標株価が無いのでニュース/短期では別途。ここは簡易。
        pass
    # get_earnings_calendar のサプライズ実績を評価
    if cal and "error" not in cal:
        surprises = cal.get("past_surprises", [])
        beats = sum(1 for s in surprises if _num(s.get("surprise_pct")) is not None and _num(s.get("surprise_pct")) >= 0)
        total = len([s for s in surprises if _num(s.get("surprise_pct")) is not None])
        if total > 0:
            if beats == total and total >= 2:
                ascore += 15; positives.append(f"直近{total}回の決算すべて予想を上回る（好業績の継続）")
            elif beats == 0 and total >= 2:
                ascore -= 15; negatives.append(f"直近{total}回の決算すべて予想を下回る（業績鈍化）")
        if cal.get("next_earnings_dates"):
            analyst["next_earnings"] = cal["next_earnings_dates"][0]
            positives.append(f"次回決算 {cal['next_earnings_dates'][0]}（重要カタリスト）")
    sub["catalyst"] = max(-100, min(100, ascore))

    # ══════════ 5. ニュースセンチメント ══════════
    nscore = 0
    if news and "error" not in news:
        pos_n = news.get("positive_count", 0)
        neg_n = news.get("negative_count", 0)
        if pos_n > neg_n:
            nscore += 10
        elif neg_n > pos_n:
            nscore -= 10
    sub["news"] = max(-100, min(100, nscore))

    # ══════════ 6. 市場ポジション（52週・アナリスト・機関保有・ベータ・財務） ══════════
    mscore = 0

    # 52週高値・安値からの位置
    last_p = _num(ta.get("last_price")) if ta and "error" not in ta else _num(info.get("currentPrice"))
    hi52 = _num(info.get("fiftyTwoWeekHigh"))
    lo52 = _num(info.get("fiftyTwoWeekLow"))
    if last_p and hi52 and lo52 and hi52 > lo52:
        pos52 = (last_p - lo52) / (hi52 - lo52) * 100
        off_high = (hi52 - last_p) / hi52 * 100
        if pos52 > 90:
            mscore += 5; positives.append(f"52週高値圏（高値まで-{off_high:.1f}%）：強いモメンタム。ただし高値掴みに注意")
        elif pos52 < 15:
            mscore -= 5; negatives.append(f"52週安値圏：下落トレンドが長い（逆張り妙味はあるがナイフキャッチ注意）")

    # アナリスト目標株価との乖離・推奨
    tgt = _num(info.get("targetMeanPrice"))
    rec = (info.get("recommendationKey") or "").lower()
    n_analysts = info.get("numberOfAnalystOpinions") or 0
    if tgt and last_p and n_analysts >= 3:
        upside = (tgt - last_p) / last_p * 100
        if upside > 15:
            mscore += 15; positives.append(f"アナリスト目標株価まで +{upside:.0f}%の上値余地（{n_analysts}名の平均）")
        elif upside < -5:
            mscore -= 15; negatives.append(f"株価がアナリスト目標を {-upside:.0f}%超過（過熱の可能性）")
    if rec:
        if "strong_buy" in rec or rec == "buy":
            mscore += 10; positives.append(f"アナリスト推奨：買い（{rec}）")
        elif "sell" in rec or "underperform" in rec:
            mscore -= 10; negatives.append(f"アナリスト推奨：売り（{rec}）")

    # 機関投資家の保有比率
    inst = _num(info.get("heldPercentInstitutions"))
    if inst is not None:
        inst_pct = inst * 100
        if inst_pct > 70:
            mscore += 5; positives.append(f"機関投資家保有 {inst_pct:.0f}%：プロの資金が入っている")
        elif inst_pct < 20:
            mscore -= 3; negatives.append(f"機関投資家保有 {inst_pct:.0f}%：機関の関心が薄い（個人主導で値動き荒い可能性）")

    # ベータ（変動の激しさ）
    beta = _num(info.get("beta"))
    if beta is not None:
        if beta > 1.8:
            negatives.append(f"ベータ {beta:.1f}：市場の{beta:.1f}倍動く高ボラ銘柄（下落局面で大きく下がる）")
        elif beta < 0.7:
            positives.append(f"ベータ {beta:.1f}：値動きが穏やかで下落耐性がある")

    # 配当
    dy = _num(info.get("dividendYield"))
    if dy is not None and dy > 3:
        mscore += 5; positives.append(f"配当利回り {dy:.1f}%：下値支えになりやすい")

    # 財務健全性（ネットキャッシュ・FCF）
    fin_score = 0
    fin_notes = []
    if bs and "error" not in bs:
        net_cash = _num(bs.get("net_cash"))
        fcf = _num(bs.get("free_cash_flow_ttm"))
        if net_cash is not None:
            if net_cash > 0:
                fin_score += 1; fin_notes.append("実質無借金（現金＞負債）")
            else:
                fin_notes.append("負債が現金を上回る")
        if fcf is not None:
            if fcf > 0:
                fin_score += 1; fin_notes.append("フリーキャッシュフロー黒字（自力でお金を生む）")
            else:
                fin_score -= 1; fin_notes.append("FCF赤字（外部資金に依存するリスク）")
    de_ratio = None
    if val and "error" not in val:
        de_ratio = _num(val.get("financial_health", {}).get("debt_to_equity"))
        cr = _num(val.get("financial_health", {}).get("current_ratio"))
        if de_ratio is not None and de_ratio < 50:
            fin_score += 1; fin_notes.append("負債比率が低い")
        if cr is not None and cr > 1.5:
            fin_score += 1
        elif cr is not None and cr < 1.0:
            fin_score -= 1; fin_notes.append("流動比率1未満（短期の支払い能力に注意）")
    if fin_score >= 2:
        mscore += 10; positives.append("財務健全性：良好（" + "・".join(fin_notes[:2]) + "）")
    elif fin_score <= -1:
        mscore -= 10; negatives.append("財務健全性：注意（" + "・".join(fin_notes[:2]) + "）")
    sub["market_position"] = max(-100, min(100, mscore))

    # ══════════ 言葉の判定（良い/普通/悪い） ══════════
    def _verdict(score, good=20, bad=-20):
        if score >= good:
            return "良い 👍"
        if score <= bad:
            return "悪い 👎"
        return "普通 ➖"

    verdicts = {
        "テクニカル": {
            "judge": _verdict(sub.get("technical", 0)),
            "why": "トレンド方向・RSIの過熱度・MACDの勢いから判定。『良い』=上昇の流れに乗っている、『悪い』=下落の流れの中にいる",
        },
        "ファンダメンタルズ": {
            "judge": _verdict(sub.get("fundamental", 0)),
            "why": "割安さ(PEG)・売上の伸び・稼ぐ力(ROE/利益率)から判定。『良い』=業績が伸びて値段も妥当、『悪い』=業績鈍化や割高",
        },
        "財務健全性": {
            "judge": "良い 👍" if fin_score >= 2 else ("悪い 👎" if fin_score <= -1 else "普通 ➖"),
            "why": "・".join(fin_notes) if fin_notes else "現金と負債のバランス、自力でお金を生む力(FCF)から判定",
        },
        "需給(空売り)": {
            "judge": _verdict(sub.get("supply_demand", 0), good=8, bad=-8),
            "why": "空売り残高の多さと増減から判定。『悪い』=プロが下落に賭けている、『良い』=売り圧力が軽い",
        },
        "市場の評価": {
            "judge": _verdict(sub.get("market_position", 0), good=15, bad=-15),
            "why": "アナリスト目標株価との差・機関投資家の保有・52週の位置から判定",
        },
    }

    # ══════════ 総合スコア（重み付け） ══════════
    weights = {
        "technical": 0.25,
        "fundamental": 0.25,
        "supply_demand": 0.10,
        "catalyst": 0.12,
        "news": 0.10,
        "market_position": 0.18,
    }
    raw = sum(sub.get(k, 0) * w for k, w in weights.items())  # -100〜+100
    total_score = round((raw + 100) / 2)  # 0〜100 に変換

    # 総合評価ランク
    if total_score >= 75:
        rating = "◎ 強気"
        outlook = "強気（1ヶ月）：上昇の可能性が優勢"
    elif total_score >= 60:
        rating = "○ やや強気"
        outlook = "やや強気（1ヶ月）：緩やかな上昇を想定"
    elif total_score >= 45:
        rating = "△ 中立"
        outlook = "中立（1ヶ月）：方向感に乏しく様子見"
    elif total_score >= 30:
        rating = "▲ やや弱気"
        outlook = "やや弱気（1ヶ月）：調整・下押しに注意"
    else:
        rating = "× 弱気"
        outlook = "弱気（1ヶ月）：下落リスクが優勢"

    # サポート/レジスタンスから当面の想定レンジ
    range_info = {}
    if ta and "error" not in ta:
        range_info = {
            "support": ta.get("support_20d"),
            "resistance": ta.get("resistance_20d"),
            "last_price": ta.get("last_price"),
        }

    return {
        "symbol": symbol.upper(),
        "total_score": total_score,       # 0-100
        "rating": rating,                 # ◎○△▲×
        "outlook_1m": outlook,
        "sub_scores": sub,                # 各観点の -100〜+100
        "verdicts": verdicts,             # 観点ごとの 良い/普通/悪い ＋ 理由
        "positives": positives,           # 好材料
        "negatives": negatives,           # 悪材料
        "expected_range": range_info,     # 想定レンジ
        "short_interest": short if "error" not in short else None,
        "news": news.get("articles", []) if "error" not in news else [],
        "news_tone": news.get("tone") if "error" not in news else None,
        "disclaimer": "本評価は過去データに基づく機械的スコアです。将来の株価を保証するものではありません。",
    }
