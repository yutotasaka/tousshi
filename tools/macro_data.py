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


SECTOR_ETFS = {
    "XLK": "テクノロジー", "XLF": "金融", "XLE": "エネルギー", "XLV": "ヘルスケア",
    "XLI": "資本財", "XLC": "通信", "XLY": "一般消費財", "XLP": "生活必需品",
    "XLU": "公益", "XLRE": "不動産", "XLB": "素材",
}

FLOW_ASSETS = {
    "SPY": "米国株(S&P500)",
    "QQQ": "米ハイテク(NASDAQ100)",
    "TLT": "米長期国債",
    "HYG": "ハイイールド債(リスク選好)",
    "GLD": "金",
    "UUP": "米ドル",
    "USO": "原油",
    "BTC-USD": "ビットコイン",
}


def get_fund_flows() -> dict:
    """
    資金フロー分析：主要アセット（株・債券・金・ドル・原油・暗号資産）と
    全11セクターの騰落率から、資金がどこに向かったか・リスクオン/オフを判定する。
    """
    assets = _fetch_group(FLOW_ASSETS)
    sectors = _fetch_group(SECTOR_ETFS)

    def _chg(items, sym):
        for it in items:
            if it["symbol"] == sym and "change_1d_pct" in it and it["change_1d_pct"] is not None:
                return it["change_1d_pct"]
        return None

    stocks = _chg(assets, "SPY")
    bonds = _chg(assets, "TLT")
    gold = _chg(assets, "GLD")
    hyg = _chg(assets, "HYG")
    dollar = _chg(assets, "UUP")

    # リスクオン/オフ判定
    signals = []
    risk_score = 0
    if stocks is not None and bonds is not None:
        if stocks > 0 and bonds < 0:
            risk_score += 1; signals.append("株↑・債券↓ → リスクオン（資金が株式へ）")
        elif stocks < 0 and bonds > 0:
            risk_score -= 1; signals.append("株↓・債券↑ → リスクオフ（安全資産の債券へ逃避）")
    if hyg is not None:
        if hyg > 0:
            risk_score += 1; signals.append("ハイイールド債↑ → リスク選好（信用リスクを取る動き）")
        elif hyg < -0.3:
            risk_score -= 1; signals.append("ハイイールド債↓ → 信用リスク回避")
    if gold is not None and gold > 0.5:
        signals.append(f"金 +{gold:.1f}% → 有事・インフレヘッジ需要、または実質金利低下")
    if dollar is not None:
        if dollar > 0.3:
            signals.append(f"ドル +{dollar:.1f}% → ドル買い（リスク回避 or 米金利高観測）")
        elif dollar < -0.3:
            signals.append(f"ドル {dollar:.1f}% → ドル売り（リスク選好 or 米金利低下観測）")

    if risk_score >= 1:
        regime = "リスクオン（強気）"
    elif risk_score <= -1:
        regime = "リスクオフ（弱気・逃避）"
    else:
        regime = "中立・方向感なし"

    # セクターローテーション
    valid_sectors = [s for s in sectors if s.get("change_1d_pct") is not None]
    valid_sectors.sort(key=lambda x: x["change_1d_pct"], reverse=True)
    winners = valid_sectors[:3]
    losers = valid_sectors[-3:]

    # 循環局面の推定（景気敏感 vs ディフェンシブ）
    cyclical = ["XLK", "XLF", "XLY", "XLI", "XLB", "XLE"]
    defensive = ["XLP", "XLU", "XLV", "XLRE"]
    cyc_avg = _avg([s["change_1d_pct"] for s in valid_sectors if s["symbol"] in cyclical])
    def_avg = _avg([s["change_1d_pct"] for s in valid_sectors if s["symbol"] in defensive])
    rotation = None
    if cyc_avg is not None and def_avg is not None:
        if cyc_avg > def_avg + 0.2:
            rotation = f"景気敏感セクター優位（+{cyc_avg:.2f}% vs ディフェンシブ+{def_avg:.2f}%）→ 景気拡大期待"
        elif def_avg > cyc_avg + 0.2:
            rotation = f"ディフェンシブ優位（+{def_avg:.2f}% vs 景気敏感+{cyc_avg:.2f}%）→ 慎重ムード"
        else:
            rotation = "セクター間の方向感は限定的"

    return {
        "regime": regime,
        "signals": signals,
        "assets": assets,
        "sector_winners": [{"label": s["label"], "change_pct": s["change_1d_pct"]} for s in winners],
        "sector_losers": [{"label": s["label"], "change_pct": s["change_1d_pct"]} for s in reversed(losers)],
        "rotation": rotation,
    }


def _avg(nums):
    nums = [n for n in nums if n is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_global_macro_snapshot":
        result = get_global_macro_snapshot(tool_input.get("categories"))
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)
