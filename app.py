"""
機関投資家エージェント — Streamlit Web UI
"""
import json
import os
from pathlib import Path

import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="機関投資家エージェント",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #0f1117; }
.metric-card {
    background: #1e2130;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 4px 0;
}
.profit { color: #00d4aa; font-weight: bold; }
.loss   { color: #ff4b4b; font-weight: bold; }
.neutral { color: #ffa500; font-weight: bold; }
.tool-badge {
    background: #2d2d2d;
    border-left: 3px solid #00d4aa;
    padding: 4px 10px;
    border-radius: 0 4px 4px 0;
    font-size: 0.8em;
    color: #aaa;
    margin: 2px 0;
}
</style>
""", unsafe_allow_html=True)

PORTFOLIO_FILE = Path("portfolio.json")


def load_portfolio() -> list[dict]:
    if PORTFOLIO_FILE.exists():
        return json.loads(PORTFOLIO_FILE.read_text())
    return []


def save_portfolio(holdings: list[dict]) -> None:
    PORTFOLIO_FILE.write_text(json.dumps(holdings, ensure_ascii=False, indent=2))


def pnl_color(val: float) -> str:
    if val > 0:
        return "profit"
    elif val < 0:
        return "loss"
    return "neutral"


def recommendation_emoji(rec: str) -> str:
    rec = (rec or "").lower()
    if "strong_buy" in rec or "strongbuy" in rec:
        return "🟢 強気買い"
    elif "buy" in rec:
        return "🟩 買い"
    elif "hold" in rec or "neutral" in rec:
        return "🟡 中立"
    elif "sell" in rec or "underperform" in rec:
        return "🔴 売り"
    return f"⚪ {rec}"


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 機関投資家エージェント")
    st.caption("Claude claude-opus-4-8 powered")

    # API Key
    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        placeholder="sk-ant-...",
    )
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    st.divider()

    # Mode selection
    mode = st.radio(
        "分析モード",
        ["🌐 マーケット分析", "💼 ポートフォリオ分析"],
        index=0,
    )

    st.divider()

    # Common options
    target = st.text_input("フォーカス銘柄・テーマ", placeholder="例: NVDA, 半導体セクター")
    context = st.text_input("補足情報", placeholder="例: 本日FOMC、決算シーズン")

    run_btn = st.button("🚀 分析開始", type="primary", use_container_width=True)


# ── Portfolio manager tab ─────────────────────────────────────────────────────
is_portfolio_mode = "ポートフォリオ" in mode

if is_portfolio_mode:
    st.header("💼 ポートフォリオ管理")

    holdings = load_portfolio()

    # Add holding form
    with st.expander("➕ 銘柄を追加", expanded=len(holdings) == 0):
        col1, col2, col3, col4 = st.columns([2, 1, 2, 1])
        with col1:
            new_sym = st.text_input("ティッカー", placeholder="AAPL").upper().strip()
        with col2:
            new_shares = st.number_input("株数", min_value=0.0, step=1.0, value=0.0)
        with col3:
            new_cost = st.number_input("取得単価 ($)", min_value=0.0, step=0.01, value=0.0)
        with col4:
            st.write("")
            st.write("")
            add_btn = st.button("追加", use_container_width=True)

        if add_btn and new_sym and new_shares > 0 and new_cost > 0:
            # Update if already exists
            existing = next((h for h in holdings if h["symbol"] == new_sym), None)
            if existing:
                existing["shares"] = new_shares
                existing["avg_cost"] = new_cost
                st.success(f"{new_sym} を更新しました")
            else:
                holdings.append({"symbol": new_sym, "shares": new_shares, "avg_cost": new_cost})
                st.success(f"{new_sym} を追加しました")
            save_portfolio(holdings)
            st.rerun()

    # Portfolio table
    if holdings:
        st.subheader("保有銘柄一覧")
        for i, h in enumerate(holdings):
            col1, col2, col3, col4 = st.columns([2, 1, 2, 1])
            with col1:
                st.write(f"**{h['symbol']}**")
            with col2:
                st.write(f"{h['shares']:,.0f} 株")
            with col3:
                st.write(f"取得単価: ${h['avg_cost']:,.2f}")
            with col4:
                if st.button("🗑️", key=f"del_{i}"):
                    holdings.pop(i)
                    save_portfolio(holdings)
                    st.rerun()
        st.caption(f"合計 {len(holdings)} 銘柄")
    else:
        st.info("上のフォームから銘柄を追加してください")

else:
    # Market mode header
    st.header("🌐 マーケット総合分析")
    st.caption("主要指数・セクター・クロスアセット・テクニカル・ニュースを網羅した機関投資家向けレポート")


# ── Run analysis ──────────────────────────────────────────────────────────────
if run_btn:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("サイドバーにAnthropicのAPIキーを入力してください")
        st.stop()

    holdings = load_portfolio() if is_portfolio_mode else []
    if is_portfolio_mode and not holdings:
        st.error("ポートフォリオに銘柄を追加してください")
        st.stop()

    from agent import stream_analysis

    st.divider()

    # Tool activity log
    tool_log = st.empty()
    tool_messages = []

    # Main output
    st.subheader("📋 分析レポート")
    output_area = st.empty()
    full_text = ""

    status = st.status("分析中...", expanded=True)

    for event in stream_analysis(
        mode="portfolio" if is_portfolio_mode else "market",
        holdings=holdings if is_portfolio_mode else None,
        target=target,
        extra_context=context,
    ):
        if event["type"] == "thinking":
            status.write("💭 思考中...")

        elif event["type"] == "tool_start":
            msg = f"🔧 **{event['name']}** を実行中..."
            tool_messages.append(msg)
            status.write(msg)

        elif event["type"] == "tool_result":
            msg = f"✅ **{event['name']}** 完了"
            tool_messages.append(msg)
            status.write(msg)

        elif event["type"] == "text":
            full_text += event["content"]
            output_area.markdown(full_text)

        elif event["type"] == "done":
            status.update(label="✅ 分析完了", state="complete", expanded=False)
            output_area.markdown(full_text)

        elif event["type"] == "error":
            status.update(label="❌ エラー", state="error")
            st.error(f"エラーが発生しました: {event['content']}")

    # Save to session for download
    if full_text:
        st.divider()
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label="📥 レポートをダウンロード",
            data=full_text,
            file_name=f"market_report_{date_str}.md",
            mime="text/markdown",
        )
