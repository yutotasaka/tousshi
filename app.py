"""
機関投資家エージェント — Streamlit Web UI（日本円ベース）
"""
import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="機関投資家エージェント",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PORTFOLIO_FILE = Path("portfolio.json")


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_api_key() -> str:
    """Secrets → 環境変数 → サイドバー入力 の順で探す"""
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


def load_portfolio() -> list[dict]:
    try:
        if PORTFOLIO_FILE.exists():
            data = json.loads(PORTFOLIO_FILE.read_text())
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def save_portfolio(holdings: list[dict]) -> None:
    try:
        PORTFOLIO_FILE.write_text(json.dumps(holdings, ensure_ascii=False, indent=2))
    except Exception as e:
        st.warning(f"保存に失敗しました: {e}")


def normalize_input_symbol(sym: str) -> str:
    """4桁の数字（日本株の証券コード）なら .T を付ける"""
    s = sym.strip().upper()
    if s.isdigit() and len(s) == 4:
        return f"{s}.T"
    return s


def yen(v) -> str:
    try:
        return f"¥{float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


# ── Session state for portfolio (survives reruns even if file write fails) ───
if "holdings" not in st.session_state:
    st.session_state.holdings = load_portfolio()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 機関投資家エージェント")
    st.caption("Claude AI による総合マーケット分析")

    api_key = get_api_key()
    if not api_key:
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            help="console.anthropic.com で取得したAPIキーを入力",
        )
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
        st.success("APIキー設定済み", icon="🔑")
    else:
        st.warning("APIキーが未設定です", icon="⚠️")

    st.divider()

    mode = st.radio(
        "分析モード",
        ["💼 ポートフォリオ分析", "🌐 マーケット分析"],
        index=0,
        help="ポートフォリオ分析＝保有銘柄の診断 / マーケット分析＝相場全体の総括",
    )

    st.divider()

    target = st.text_input(
        "フォーカス銘柄・テーマ（任意）",
        placeholder="例: 7203, NVDA, 半導体",
    )
    context = st.text_input(
        "補足情報（任意）",
        placeholder="例: 本日FOMC、日銀会合",
    )

    run_btn = st.button("🚀 分析開始", type="primary", use_container_width=True)

    st.divider()
    with st.expander("❓ 使い方"):
        st.markdown("""
**1. APIキーを設定**（初回のみ）

**2. モードを選ぶ**
- 💼 ポートフォリオ分析：保有株の診断・売買アドバイス
- 🌐 マーケット分析：今日の相場総括

**3. ポートフォリオ分析の場合**
右の画面で保有銘柄を登録：
- 日本株 → 証券コード4桁（例: `7203`）
- 米国株 → ティッカー（例: `AAPL`）
- 株数と、1株あたりの買値（日本株は円、米国株はドル）

**4. 「🚀 分析開始」を押す**
1〜3分でレポートが生成されます
""")


is_portfolio_mode = "ポートフォリオ" in mode


# ── Portfolio manager ─────────────────────────────────────────────────────────
if is_portfolio_mode:
    st.header("💼 ポートフォリオ管理")
    st.caption("日本株は証券コード4桁（例: 7203 → トヨタ）、米国株はティッカー（例: AAPL）。金額は日本株＝円、米国株＝ドルで入力してください。合計は円換算で表示されます。")

    holdings = st.session_state.holdings

    with st.expander("➕ 銘柄を追加・変更", expanded=len(holdings) == 0):
        with st.form("add_holding", clear_on_submit=True):
            col1, col2, col3 = st.columns([2, 1, 2])
            with col1:
                new_sym = st.text_input("証券コード / ティッカー", placeholder="7203 または AAPL")
            with col2:
                new_shares = st.number_input("株数", min_value=0.0, step=100.0, value=0.0)
            with col3:
                new_cost = st.number_input(
                    "取得単価（日本株:円 / 米国株:ドル）",
                    min_value=0.0, step=1.0, value=0.0,
                )
            add_btn = st.form_submit_button("追加 / 更新", use_container_width=True)

        if add_btn:
            sym = normalize_input_symbol(new_sym)
            if not sym:
                st.error("証券コードまたはティッカーを入力してください")
            elif new_shares <= 0:
                st.error("株数を入力してください")
            elif new_cost <= 0:
                st.error("取得単価を入力してください")
            else:
                existing = next((h for h in holdings if h["symbol"] == sym), None)
                if existing:
                    existing["shares"] = new_shares
                    existing["avg_cost"] = new_cost
                    st.success(f"{sym} を更新しました")
                else:
                    holdings.append({"symbol": sym, "shares": new_shares, "avg_cost": new_cost})
                    st.success(f"{sym} を追加しました")
                save_portfolio(holdings)
                st.rerun()

    if holdings:
        st.subheader("保有銘柄")
        header = st.columns([2, 1.5, 2, 1])
        header[0].markdown("**銘柄**")
        header[1].markdown("**株数**")
        header[2].markdown("**取得単価**")
        for i, h in enumerate(holdings):
            is_jp = str(h["symbol"]).endswith(".T")
            unit = "円" if is_jp else "ドル"
            cols = st.columns([2, 1.5, 2, 1])
            cols[0].write(f"**{h['symbol']}** {'🇯🇵' if is_jp else '🇺🇸'}")
            cols[1].write(f"{h['shares']:,.0f} 株")
            cols[2].write(f"{h['avg_cost']:,.1f} {unit}")
            if cols[3].button("削除", key=f"del_{i}"):
                holdings.pop(i)
                save_portfolio(holdings)
                st.rerun()
        st.caption(f"合計 {len(holdings)} 銘柄（分析実行時に現在値・損益を円換算で算出します）")

        # 即時サマリー（API不要・yfinanceのみ）
        if st.button("💹 現在の損益をチェック（AI分析なし・無料）"):
            with st.spinner("価格取得中..."):
                try:
                    from tools.portfolio import get_portfolio_snapshot
                    snap = get_portfolio_snapshot(holdings)
                    s = snap["summary"]
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("評価額合計", yen(s["total_value_jpy"]))
                    m2.metric("取得額合計", yen(s["total_cost_jpy"]))
                    m3.metric("評価損益", yen(s["total_pnl_jpy"]), f"{s['total_pnl_pct']:+.2f}%")
                    m4.metric("ドル円", f"{snap['usdjpy_rate']:.2f}")
                    for r in snap["holdings"]:
                        if "error" in r:
                            st.warning(f"{r['symbol']}: {r['error']}")
                        else:
                            pnl = r["unrealized_pnl_jpy"]
                            emoji = "🟢" if pnl >= 0 else "🔴"
                            st.write(
                                f"{emoji} **{r['symbol']}** ({r.get('name','')}) — "
                                f"現在値 {r['current_price']:,.1f} {r['currency']} "
                                f"（前日比 {r['day_change_pct']:+.2f}%）／ "
                                f"評価損益 {yen(pnl)}（{r['unrealized_pnl_pct']:+.1f}%）／ "
                                f"構成比 {r.get('allocation_pct', 0):.1f}%"
                            )
                except Exception as e:
                    st.error(f"価格取得に失敗しました: {e}")
    else:
        st.info("👆 上のフォームから保有銘柄を追加してください（例：トヨタなら「7203」、株数「100」、取得単価「2500」）")

else:
    st.header("🌐 マーケット総合分析")
    st.caption("日米の指数・為替・セクター・金利・ニュースを網羅した機関投資家向け日次レポートを生成します")


# ── Run analysis ──────────────────────────────────────────────────────────────
if run_btn:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("サイドバーにAnthropicのAPIキーを入力してください")
        st.stop()

    holdings = st.session_state.holdings if is_portfolio_mode else []
    if is_portfolio_mode and not holdings:
        st.error("ポートフォリオに銘柄を追加してから分析を実行してください")
        st.stop()

    st.divider()
    st.subheader("📋 分析レポート")
    output_area = st.empty()
    full_text = ""

    status = st.status("分析中...（1〜3分かかります）", expanded=True)

    try:
        from agent import stream_analysis

        for event in stream_analysis(
            mode="portfolio" if is_portfolio_mode else "market",
            holdings=holdings if is_portfolio_mode else None,
            target=target,
            extra_context=context,
        ):
            if event["type"] == "thinking":
                status.write("💭 思考中...")
            elif event["type"] == "tool_start":
                status.write(f"🔧 {event['name']} を実行中...")
            elif event["type"] == "tool_result":
                status.write(f"✅ {event['name']} 完了")
            elif event["type"] == "text":
                full_text += event["content"]
                output_area.markdown(full_text)
            elif event["type"] == "done":
                status.update(label="✅ 分析完了", state="complete", expanded=False)
                output_area.markdown(full_text)
            elif event["type"] == "error":
                status.update(label="❌ エラー", state="error")
                msg = event["content"]
                if "authentication" in msg.lower() or "401" in msg:
                    st.error("APIキーが無効です。console.anthropic.com でキーを確認してください。")
                elif "credit" in msg.lower() or "billing" in msg.lower():
                    st.error("Anthropicアカウントの残高が不足しています。console.anthropic.com の Billing でチャージしてください。")
                elif "overloaded" in msg.lower() or "529" in msg:
                    st.error("AIサーバーが混雑しています。少し待ってから再実行してください。")
                else:
                    st.error(f"エラーが発生しました: {msg}")
    except Exception as e:
        status.update(label="❌ エラー", state="error")
        st.error(f"予期しないエラー: {e}")

    if full_text:
        st.divider()
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label="📥 レポートをダウンロード",
            data=full_text,
            file_name=f"report_{date_str}.md",
            mime="text/markdown",
        )
