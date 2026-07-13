"""無料のニュース取得（yfinance経由）。銘柄・市場のニュース見出しを取得する。"""
import json
from datetime import datetime, timezone

import yfinance as yf


# 見出しに含まれるとポジティブ/ネガティブと推定するキーワード（簡易センチメント）
_POSITIVE = [
    "beat", "beats", "surge", "surges", "soar", "rally", "record", "upgrade",
    "raises", "raise", "boost", "jump", "gains", "gain", "profit", "growth",
    "wins", "win", "approval", "approved", "outperform", "buy", "bullish",
    "strong", "high", "expands", "partnership", "breakthrough", "top",
]
_NEGATIVE = [
    "miss", "misses", "plunge", "plunges", "fall", "falls", "drop", "drops",
    "downgrade", "cuts", "cut", "slump", "loss", "losses", "warn", "warning",
    "lawsuit", "probe", "investigation", "recall", "layoff", "layoffs",
    "weak", "bearish", "sell", "concern", "concerns", "decline", "slashes",
    "fraud", "delay", "delayed", "halt", "ban", "fine", "risk",
]


# 見出しの趣旨を日本語タグ化するためのキーワード辞書（順に優先）
_TOPIC_TAGS = [
    ("【決算】", ["earnings", "quarterly results", "revenue", "profit", "eps", "guidance", "forecast", "outlook", "beat", "miss"]),
    ("【アナリスト】", ["analyst", "upgrade", "downgrade", "price target", "rating", "initiate", "overweight", "underweight", "buy rating", "sell rating"]),
    ("【M&A・提携】", ["acquisition", "acquire", "merger", "takeover", "deal", "partnership", "stake", "joint venture", "buyout"]),
    ("【新製品・技術】", ["launch", "unveil", "new product", "chip", "ai ", " ai", "model", "technology", "innovation", "patent", "breakthrough"]),
    ("【規制・訴訟】", ["lawsuit", "sue", "probe", "investigation", "regulator", "antitrust", "fine", "ban", "court", "settlement", "sec ", "ftc"]),
    ("【人事・経営】", ["ceo", "cfo", "executive", "resign", "appoint", "layoff", "job cuts", "restructuring", "hire"]),
    ("【配当・還元】", ["dividend", "buyback", "repurchase", "split"]),
    ("【金利・中銀】", ["fed", "fomc", "rate", "interest", "boj", "ecb", "central bank", "powell", "inflation", "cpi"]),
    ("【政治・地政学】", ["tariff", "trump", "election", "china", "trade war", "sanction", "war", "geopolit", "congress", "government"]),
    ("【株価動向】", ["stock", "shares", "surge", "plunge", "rally", "jump", "fall", "drop", "record high", "52-week"]),
]


def _jp_gist(title: str) -> str:
    """英語見出しから日本語の趣旨タグを推定。"""
    t = (title or "").lower()
    for tag, kws in _TOPIC_TAGS:
        if any(k in t for k in kws):
            return tag
    return "【その他】"


def _classify(title: str) -> str:
    t = (title or "").lower()
    pos = sum(1 for w in _POSITIVE if w in t)
    neg = sum(1 for w in _NEGATIVE if w in t)
    if pos > neg:
        return "好材料"
    if neg > pos:
        return "悪材料"
    return "中立"


def _parse_item(item: dict) -> dict | None:
    """yfinanceの新旧両フォーマットに対応してニュース1件を正規化。"""
    if not isinstance(item, dict):
        return None
    # 新フォーマット: {"content": {...}}
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = content.get("title") or item.get("title")
    if not title:
        return None

    # publisher
    publisher = None
    prov = content.get("provider")
    if isinstance(prov, dict):
        publisher = prov.get("displayName")
    publisher = publisher or item.get("publisher")

    # link
    link = None
    cu = content.get("canonicalUrl") or content.get("clickThroughUrl")
    if isinstance(cu, dict):
        link = cu.get("url")
    link = link or item.get("link")

    # time
    ts = None
    for key in ("pubDate", "displayTime"):
        if content.get(key):
            ts = content.get(key)
            break
    published = None
    if isinstance(ts, str):
        published = ts[:10]
    elif item.get("providerPublishTime"):
        try:
            published = datetime.fromtimestamp(
                item["providerPublishTime"], tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except Exception:
            published = None

    return {
        "title": title,
        "publisher": publisher or "—",
        "link": link,
        "published": published,
        "sentiment": _classify(title),
        "topic_jp": _jp_gist(title),
    }


def get_stock_news(symbol: str, limit: int = 10) -> dict:
    """個別銘柄の最新ニュース見出しを取得（簡易センチメント付き）。"""
    try:
        raw = yf.Ticker(symbol).news or []
        items = []
        for it in raw:
            parsed = _parse_item(it)
            if parsed:
                items.append(parsed)
            if len(items) >= limit:
                break
        pos = sum(1 for i in items if i["sentiment"] == "好材料")
        neg = sum(1 for i in items if i["sentiment"] == "悪材料")
        tone = "ポジティブ優勢" if pos > neg else ("ネガティブ優勢" if neg > pos else "中立")
        return {
            "symbol": symbol.upper(),
            "count": len(items),
            "tone": tone,
            "positive_count": pos,
            "negative_count": neg,
            "articles": items,
        }
    except Exception as e:
        return {"error": str(e), "articles": []}


def dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_stock_news":
        result = get_stock_news(tool_input["symbol"], tool_input.get("limit", 10))
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)
