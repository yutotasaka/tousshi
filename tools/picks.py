"""
注目銘柄ピックアップ：定義済みユニバースを選定基準＋売買タイミングでスキャンし、
総合スコア順にランキングする（無料・yfinanceのみ）。
"""
from tools.screening import check_criteria, timing_judgment
from tools.paypay_universe import PAYPAY_JP, PAYPAY_US, UNIVERSE_LABEL_JP, UNIVERSE_LABEL_US


# スキャン対象ユニバース（日米の主要銘柄・流動性が高いもの）
UNIVERSES = {
    "日本株・高配当/バリュー": [
        "7203.T",  # トヨタ
        "8058.T",  # 三菱商事
        "8031.T",  # 三井物産
        "8001.T",  # 伊藤忠
        "2914.T",  # JT
        "9433.T",  # KDDI
        "9432.T",  # NTT
        "8306.T",  # 三菱UFJ
        "8316.T",  # 三井住友FG
        "8411.T",  # みずほFG
        "8766.T",  # 東京海上
        "1605.T",  # INPEX
        "5401.T",  # 日本製鉄
        "9101.T",  # 日本郵船
        "9104.T",  # 商船三井
        "4502.T",  # 武田薬品
        "6301.T",  # コマツ
        "7267.T",  # ホンダ
        "8593.T",  # 三菱HCキャピタル
        "8591.T",  # オリックス
    ],
    "日本株・成長/テック": [
        "6758.T",  # ソニーG
        "6861.T",  # キーエンス
        "8035.T",  # 東京エレクトロン
        "6501.T",  # 日立
        "6902.T",  # デンソー
        "6981.T",  # 村田製作所
        "6273.T",  # SMC
        "6367.T",  # ダイキン
        "4063.T",  # 信越化学
        "9983.T",  # ファーストリテイリング
        "9984.T",  # ソフトバンクG
        "4568.T",  # 第一三共
        "6098.T",  # リクルート
        "7741.T",  # HOYA
        "6954.T",  # ファナック
    ],
    "米国株・配当/バリュー": [
        "JNJ", "PG", "KO", "PEP", "MCD",
        "VZ", "T", "MO", "PM", "XOM",
        "CVX", "ABBV", "MRK", "PFE", "BMY",
        "HD", "LOW", "CAT", "JPM", "BAC",
    ],
    "米国株・成長/テック": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META",
        "NVDA", "AMD", "AVGO", "TSM", "QCOM",
        "CRM", "ORCL", "ADBE", "NFLX", "TSLA",
    ],
}

# PayPay証券の取扱銘柄（参考版・全銘柄スキャン用）
UNIVERSES[UNIVERSE_LABEL_JP] = PAYPAY_JP
UNIVERSES[UNIVERSE_LABEL_US] = PAYPAY_US


def scan_symbols(
    symbols: list[str],
    max_per: float = 10.0,
    min_dividend_yield: float = 3.0,
    min_roe: float = 10.0,
    min_dividend_streak: int = 3,
    max_de_ratio: float = 100.0,
    min_op_margin: float = 8.0,
    max_payout_ratio: float = 60.0,
    min_rev_growth: float = 3.0,
    min_earnings_growth: float = 0.0,
    progress_callback=None,
) -> list[dict]:
    """任意の銘柄リストを一括診断（scan_universeの実体）。"""
    results = []
    for i, sym in enumerate(symbols):
        if progress_callback:
            progress_callback(i, len(symbols), sym)
        try:
            cr = check_criteria(
                sym, max_per=max_per, min_dividend_yield=min_dividend_yield,
                min_roe=min_roe, min_dividend_streak=min_dividend_streak,
                max_de_ratio=max_de_ratio, min_op_margin=min_op_margin,
                max_payout_ratio=max_payout_ratio, min_rev_growth=min_rev_growth,
                min_earnings_growth=min_earnings_growth,
            )
            tj = timing_judgment(sym)

            criteria_ratio = cr["passed"] / cr["total"] if cr["total"] else 0
            timing_score = tj.get("score", 0)
            timing_norm = max(0.0, min(1.0, (timing_score + 4) / 9))
            combined = round((criteria_ratio * 0.6 + timing_norm * 0.4) * 100)

            results.append({
                "symbol": sym,
                "name": cr.get("name", sym),
                "combined_score": combined,
                "grade": cr["grade"],
                "passed": cr["passed"],
                "total": cr["total"],
                "verdict": tj.get("verdict", "—"),
                "deviation_pct": tj.get("deviation_pct"),
                "current_per": tj.get("current_per"),
                "avg_per": tj.get("avg_per"),
                "news_tone": tj.get("news_tone"),
                "checks": cr["checks"],
                "factors": tj.get("factors", []),
            })
        except Exception as e:
            results.append({"symbol": sym, "error": str(e), "combined_score": -1})

    results.sort(key=lambda r: r.get("combined_score", -1), reverse=True)
    return results


def scan_universe(
    universe_name: str,
    max_per: float = 10.0,
    min_dividend_yield: float = 3.0,
    min_roe: float = 10.0,
    min_dividend_streak: int = 3,
    max_de_ratio: float = 100.0,
    min_op_margin: float = 8.0,
    max_payout_ratio: float = 60.0,
    min_rev_growth: float = 3.0,
    min_earnings_growth: float = 0.0,
    progress_callback=None,
) -> list[dict]:
    """
    ユニバースを一括診断し、スコア順に返す。
    総合スコア = 基準クリア数の割合(60%) + 売買タイミングスコア(40%)
    """
    return scan_symbols(
        UNIVERSES.get(universe_name, []),
        max_per=max_per, min_dividend_yield=min_dividend_yield,
        min_roe=min_roe, min_dividend_streak=min_dividend_streak,
        max_de_ratio=max_de_ratio, min_op_margin=min_op_margin,
        max_payout_ratio=max_payout_ratio, min_rev_growth=min_rev_growth,
        min_earnings_growth=min_earnings_growth,
        progress_callback=progress_callback,
    )
