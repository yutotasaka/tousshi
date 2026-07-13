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


def fmt_shares(v) -> str:
    """端株（小数）を見やすく表示。0.5 → '0.5', 3.0 → '3', 1.2345 → '1.2345'"""
    try:
        f = float(v)
        if f == int(f):
            return f"{int(f):,}"
        return f"{f:,.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "—"


def render_evaluation(sym: str):
    """銘柄の総合評価（スコア・1ヶ月見通し・好材料/悪材料・空売り・ニュース）を描画。"""
    from tools.scoring import evaluate_stock
    ev = evaluate_stock(sym)

    score = ev.get("total_score", 0)
    rating = ev.get("rating", "—")
    # スコアで色分け
    if score >= 60:
        box = st.success
    elif score >= 45:
        box = st.info
    else:
        box = st.warning
    box(f"### 総合評価： {rating}　（スコア {score}/100）\n{ev.get('outlook_1m','')}")

    # サブスコア
    sub = ev.get("sub_scores", {})
    labels = {
        "technical": "テクニカル", "fundamental": "ファンダ",
        "supply_demand": "需給(空売り)", "catalyst": "決算材料", "news": "ニュース",
        "market_position": "市場評価",
    }
    if sub:
        scols = st.columns(len(sub))
        for i, (k, lbl) in enumerate([(k, labels.get(k, k)) for k in sub]):
            v = sub[k]  # -100〜+100
            mark = "🟢" if v > 15 else ("🔴" if v < -15 else "🟡")
            scols[i].metric(lbl, f"{mark}{v:+d}")

    # 言葉の判定（良い/普通/悪い）
    verdicts = ev.get("verdicts", {})
    if verdicts:
        st.markdown("**📝 わかりやすい判定**")
        for name, vd in verdicts.items():
            st.markdown(f"- **{name}：{vd['judge']}** — {vd['why']}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**✅ 好材料**")
        pos = ev.get("positives", [])
        if pos:
            for p in pos:
                st.markdown(f"- {p}")
        else:
            st.caption("特筆すべき好材料なし")
    with c2:
        st.markdown("**⚠️ 悪材料・リスク**")
        neg = ev.get("negatives", [])
        if neg:
            for n in neg:
                st.markdown(f"- {n}")
        else:
            st.caption("特筆すべき悪材料なし")

    # 想定レンジ
    rng = ev.get("expected_range", {})
    if rng.get("support") and rng.get("resistance"):
        st.caption(
            f"📊 当面の想定レンジ：サポート {rng['support']:,.0f} 〜 レジスタンス {rng['resistance']:,.0f}"
            f"（現在 {rng.get('last_price', '—')}）"
        )

    # 空売り
    si = ev.get("short_interest")
    if si:
        parts = []
        if si.get("short_pct_of_float") is not None:
            parts.append(f"空売り比率 {si['short_pct_of_float']}%")
        if si.get("short_ratio_days") is not None:
            parts.append(f"買い戻し日数 {si['short_ratio_days']}日")
        if si.get("shares_short_change_pct") is not None:
            parts.append(f"前月比 {si['shares_short_change_pct']:+.0f}%")
        if parts:
            st.caption("🩳 機関の空売り： " + " / ".join(parts))

    # ニュース
    articles = ev.get("news", [])
    if articles:
        with st.expander(f"📰 関連ニュース（{ev.get('news_tone','')}）", expanded=False):
            for a in articles:
                icon = {"好材料": "🟢", "悪材料": "🔴"}.get(a["sentiment"], "⚪")
                topic = a.get("topic_jp", "")
                date = a.get("published") or ""
                title = a["title"]
                if a.get("link"):
                    st.markdown(f"{icon} {topic} [{title}]({a['link']}) — {a.get('publisher','')} {date}")
                else:
                    st.markdown(f"{icon} {topic} {title} — {a.get('publisher','')} {date}")
    st.caption("※ " + ev.get("disclaimer", ""))
    return ev


# ── Session state for portfolio (survives reruns even if file write fails) ───
if "holdings" not in st.session_state:
    st.session_state.holdings = load_portfolio()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 機関投資家エージェント")
    st.caption("日本株・米国株の総合マーケット分析（無料）")

    mode = st.radio(
        "メニュー",
        ["💼 ポートフォリオ", "🌐 マーケット", "🔍 銘柄検索"],
        index=0,
        help="ポートフォリオ＝保有銘柄の損益・診断 / マーケット＝世界の相場状況 / 銘柄検索＝個別銘柄の全情報",
    )

    st.divider()
    with st.expander("❓ 使い方", expanded=False):
        st.markdown("""
**💼 ポートフォリオ**
保有銘柄を登録して損益・テクニカル・決算をまとめてチェック
- 日本株 → 証券コード4桁（例: `7203`）
- 米国株 → ティッカー（例: `AAPL`）
- 金額は日本株＝円、米国株＝ドル

**🌐 マーケット**
世界の株価指数・為替・金利・コモディティを一覧表示

**🔍 銘柄検索**
気になる銘柄のコードを入れると、価格チャート・テクニカル・割安度・決算・財務を表示

すべて無料で利用できます。
""")


is_portfolio_mode = "ポートフォリオ" in mode
is_search_mode = "銘柄検索" in mode


# ── Portfolio manager ─────────────────────────────────────────────────────────
if is_portfolio_mode:
    st.header("💼 ポートフォリオ管理")
    st.caption("日本株は証券コード4桁（例: 7203 → トヨタ）、米国株はティッカー（例: AAPL）。金額は日本株＝円、米国株＝ドルで入力してください。合計は円換算で表示されます。")

    holdings = st.session_state.holdings

    with st.expander("➕ 銘柄を追加・変更", expanded=len(holdings) == 0):
        st.caption("💡 PayPay証券など端株（0.5株など小数）もそのまま入力できます。")
        input_mode = st.radio(
            "入力方法",
            ["保有数量＋取得単価（PayPay向け）", "投資金額から自動計算"],
            horizontal=True,
            help=(
                "・保有数量＋取得単価：PayPay証券アプリの「保有数量」と「平均取得単価」をそのまま入力（小数OK）\n"
                "・投資金額から自動計算：いくら分買ったか（円/ドル）を入れると株数を自動計算"
            ),
        )
        by_amount = "金額" in input_mode

        with st.form("add_holding", clear_on_submit=True):
            col1, col2, col3 = st.columns([2, 2, 2])
            with col1:
                new_sym = st.text_input("証券コード / ティッカー", placeholder="7203 または AAPL")
            with col2:
                if by_amount:
                    new_amount = st.number_input(
                        "投資金額（日本株:円 / 米国株:ドル）",
                        min_value=0.0, step=1000.0, value=0.0,
                        help="PayPayで「1000円分買った」なら 1000 と入力",
                    )
                    new_shares = 0.0
                else:
                    new_shares = st.number_input(
                        "保有数量（株）",
                        min_value=0.0, step=0.1, value=0.0, format="%.4f",
                        help="0.5 など小数もOK。PayPayアプリの「保有数量」をそのまま入力",
                    )
                    new_amount = 0.0
            with col3:
                new_cost = st.number_input(
                    "取得単価（日本株:円 / 米国株:ドル）" + ("　※0=現在値で計算" if by_amount else ""),
                    min_value=0.0, step=0.01, value=0.0, format="%.2f",
                    help="PayPayアプリの「平均取得単価」をそのまま入力",
                )
            new_fx = st.number_input(
                "取得為替レート（米国株のみ・任意）",
                min_value=0.0, step=0.01, value=0.0, format="%.2f",
                help=(
                    "米国株で、PayPay証券の損益に近づけたい場合に入力。"
                    "PayPayアプリの「取得為替レート」（例: 162.78）をそのまま入力すると、"
                    "取得金額の円換算がPayPayと一致します。空欄(0)なら現在レートで計算。"
                ),
            )
            add_btn = st.form_submit_button("追加 / 更新", use_container_width=True)

        if add_btn:
            sym = normalize_input_symbol(new_sym)
            err = None
            if not sym:
                err = "証券コードまたはティッカーを入力してください"
            elif by_amount and new_amount <= 0:
                err = "投資金額を入力してください"
            elif not by_amount and new_shares <= 0:
                err = "保有数量を入力してください"
            elif not by_amount and new_cost <= 0:
                err = "取得単価を入力してください"

            if err:
                st.error(err)
            else:
                cost = new_cost
                if by_amount:
                    # 取得単価が未入力なら現在値を取得して使う
                    if cost <= 0:
                        with st.spinner(f"{sym} の現在値を取得中..."):
                            try:
                                import yfinance as yf
                                hist = yf.Ticker(sym).history(period="2d", auto_adjust=True)
                                if hist is not None and not hist.empty:
                                    cost = float(hist["Close"].iloc[-1])
                            except Exception:
                                cost = 0.0
                    if cost <= 0:
                        st.error(f"{sym} の株価を取得できませんでした。取得単価を手入力してください。")
                        st.stop()
                    new_shares = round(new_amount / cost, 6)
                    st.info(f"計算結果: {new_amount:,.0f} ÷ 単価 {cost:,.2f} = **{fmt_shares(new_shares)} 株** として登録します")

                # 取得為替レート（米国株のみ有効）
                is_us = not sym.endswith(".T")
                fx_at_cost = new_fx if (is_us and new_fx > 0) else None

                existing = next((h for h in holdings if h["symbol"] == sym), None)
                if existing:
                    existing["shares"] = new_shares
                    existing["avg_cost"] = round(cost, 4)
                    if fx_at_cost:
                        existing["fx_at_cost"] = round(fx_at_cost, 4)
                    else:
                        existing.pop("fx_at_cost", None)
                    st.success(f"{sym} を更新しました（{fmt_shares(new_shares)}株 @ {cost:,.2f}）")
                else:
                    new_h = {"symbol": sym, "shares": new_shares, "avg_cost": round(cost, 4)}
                    if fx_at_cost:
                        new_h["fx_at_cost"] = round(fx_at_cost, 4)
                    holdings.append(new_h)
                    st.success(f"{sym} を追加しました（{fmt_shares(new_shares)}株 @ {cost:,.2f}）")
                save_portfolio(holdings)

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
            cols[1].write(f"{fmt_shares(h['shares'])} 株")
            fx_note = f"（取得為替 {h['fx_at_cost']:.2f}）" if h.get("fx_at_cost") else ""
            cols[2].write(f"{h['avg_cost']:,.2f} {unit}{fx_note}")
            if cols[3].button("削除", key=f"del_{i}"):
                holdings.pop(i)
                save_portfolio(holdings)
                st.rerun()
        st.caption(f"合計 {len(holdings)} 銘柄（分析実行時に現在値・損益を円換算で算出します）")

        # ── ダッシュボード ────────────────────────────────────────────────
        st.divider()
        st.subheader("📈 ダッシュボード")
        st.caption("データ取得に数十秒かかります。")

        haircut_pct = st.number_input(
            "PayPay評価調整：米国株の評価額を◯%控除（任意）",
            min_value=0.0, max_value=5.0, step=0.05, value=0.0, format="%.2f",
            help=(
                "PayPay証券の評価額はスプレッド（手数料）が引かれているため、アプリの方が数%高く出ます。"
                "ここに調整率を入れると米国株の評価額をその分控除してPayPayに近づけます。"
                "PayPayと見比べて、一致する値（目安0.5〜1.0）に調整してください。0なら市場価格のまま。"
            ),
        )

        if st.button("💹 ダッシュボードを表示", type="primary", use_container_width=True):
            from tools.portfolio import get_portfolio_snapshot
            from tools.market_data import get_price_history
            from tools.technical_analysis import run_technical_analysis
            from tools.fundamentals import get_valuation_metrics, get_earnings_calendar

            # 1) 損益サマリー
            with st.spinner("損益を計算中..."):
                try:
                    snap = get_portfolio_snapshot(holdings, us_valuation_haircut_pct=haircut_pct)
                    s = snap["summary"]
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("評価額合計", yen(s["total_value_jpy"]))
                    m2.metric("取得額合計", yen(s["total_cost_jpy"]))
                    m3.metric("評価損益", yen(s["total_pnl_jpy"]), f"{s['total_pnl_pct']:+.2f}%")
                    m4.metric("ドル円", f"{snap['usdjpy_rate']:.2f}")
                except Exception as e:
                    st.error(f"損益計算に失敗しました: {e}")
                    snap = {"holdings": []}

            # 2) 各銘柄の詳細（損益・テクニカル・割安度・次回決算）
            for r in snap["holdings"]:
                sym = r["symbol"]
                if "error" in r:
                    st.warning(f"{sym}: {r['error']}")
                    continue

                pnl = r["unrealized_pnl_jpy"]
                emoji = "🟢" if pnl >= 0 else "🔴"
                with st.expander(
                    f"{emoji} {sym}（{r.get('name','')}）　損益 {yen(pnl)}（{r['unrealized_pnl_pct']:+.1f}%）",
                    expanded=False,
                ):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("現在値", f"{r['current_price']:,.1f} {r['currency']}", f"{r['day_change_pct']:+.2f}%")
                    c2.metric("評価額（円）", yen(r["market_value_jpy"]))
                    c3.metric("構成比", f"{r.get('allocation_pct', 0):.1f}%")
                    tgt = r["analyst"].get("target_mean")
                    ups = r["analyst"].get("upside_pct")
                    c4.metric(
                        "アナリスト目標",
                        f"{tgt:,.0f}" if tgt else "—",
                        f"{ups:+.1f}%" if ups is not None else None,
                    )

                    # 総合評価（テクニカル・ファンダ・空売り・決算材料・ニュースを統合）
                    with st.spinner(f"{sym} を評価中..."):
                        try:
                            render_evaluation(sym)
                        except Exception as e:
                            st.caption(f"評価の生成に失敗しました: {e}")

            st.success("ダッシュボード表示完了")
    else:
        st.info("👆 上のフォームから保有銘柄を追加してください（例：PayPay証券でNVDAを0.5株、平均取得単価180ドルなら → コード「NVDA」保有数量「0.5」取得単価「180」）")

elif is_search_mode:
    st.header("🔍 銘柄検索")
    st.caption("証券コード（例: 7203）またはティッカー（例: NVDA）を入力すると、価格・テクニカル・割安度・決算・財務・アナリスト評価をまとめて表示します")

    sc1, sc2 = st.columns([3, 1])
    with sc1:
        search_sym_raw = st.text_input("証券コード / ティッカー", placeholder="7203 または NVDA", label_visibility="collapsed")
    with sc2:
        search_btn = st.button("🔍 検索", type="primary", use_container_width=True)

    if search_btn and search_sym_raw.strip():
        sym = normalize_input_symbol(search_sym_raw)
        from tools.market_data import get_price_history
        from tools.technical_analysis import run_technical_analysis
        from tools.fundamentals import (
            get_valuation_metrics,
            get_earnings_calendar,
            get_earnings_history,
            get_balance_sheet_summary,
        )
        from tools.portfolio import get_usdjpy_rate

        with st.spinner(f"{sym} の情報を取得中...（20秒ほど）"):
            # ── 基本情報・現在値 ──
            val = {}
            try:
                val = get_valuation_metrics(sym)
            except Exception as e:
                val = {"error": str(e)}

            hist = get_price_history(sym, "6mo")

            if "error" in hist and "error" in val:
                st.error(f"「{sym}」のデータが見つかりません。コードを確認してください（日本株は4桁数字、米国株はアルファベット）。")
                st.stop()

            name = val.get("name") or sym
            is_jp = sym.endswith(".T")
            cur_label = "円" if is_jp else "ドル"
            st.subheader(f"{'🇯🇵' if is_jp else '🇺🇸'} {name}（{sym}）")

            # ── 総合評価（最上部に表示） ──
            try:
                render_evaluation(sym)
            except Exception as e:
                st.caption(f"総合評価の生成に失敗しました: {e}")
            st.divider()

            if val.get("sector"):
                st.caption(f"セクター: {val.get('sector')} ｜ 時価総額: {val['market_cap']:,} " + ("円" if is_jp else "ドル") if val.get("market_cap") else f"セクター: {val.get('sector')}")

            # ── 価格・テクニカル ──
            ta = {}
            if "data" in hist and hist["data"]:
                last_bar = hist["data"][-1]
                prev_bar = hist["data"][-2] if len(hist["data"]) >= 2 else last_bar
                chg = (last_bar["close"] - prev_bar["close"]) / prev_bar["close"] * 100 if prev_bar["close"] else 0
                p1, p2, p3, p4 = st.columns(4)
                p1.metric("現在値", f"{last_bar['close']:,.1f} {cur_label}", f"{chg:+.2f}%")
                if not is_jp:
                    usdjpy = get_usdjpy_rate()
                    p2.metric("円換算", f"¥{last_bar['close'] * usdjpy:,.0f}", f"ドル円 {usdjpy:.2f}")
                try:
                    ta = run_technical_analysis(hist["data"])
                except Exception:
                    ta = {}
                if ta and "error" not in ta:
                    p3.metric("RSI(14)", ta.get("rsi14", "—"))
                    p4.metric("トレンド", "📈 上昇" if ta.get("trend") == "UPTREND" else "📉 下落")

                # 価格チャート
                import pandas as pd
                df = pd.DataFrame(hist["data"])
                df["date"] = pd.to_datetime(df["date"])
                st.line_chart(df.set_index("date")["close"], height=250)

            # ── テクニカル詳細 ──
            if ta and "error" not in ta:
                st.markdown("#### 📈 テクニカル")
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("サポート(20日)", f"{ta.get('support_20d', 0):,.0f}")
                t2.metric("レジスタンス(20日)", f"{ta.get('resistance_20d', 0):,.0f}")
                ma = ta.get("moving_averages", {})
                t3.metric("20日EMA", f"{ma.get('ema20', 0):,.0f}" if ma.get("ema20") else "—")
                t4.metric("50日EMA", f"{ma.get('ema50', 0):,.0f}" if ma.get("ema50") else "—")
                for sig in ta.get("signals", []):
                    st.info(f"📶 {sig}")

            # ── バリュエーション・収益性 ──
            if val and "error" not in val:
                st.markdown("#### 📑 バリュエーション・収益性")
                v = val.get("valuation", {})
                p = val.get("profitability", {})
                g = val.get("growth", {})
                fh = val.get("financial_health", {})
                dv = val.get("dividend", {})
                b1, b2, b3, b4, b5 = st.columns(5)
                b1.metric("PER(実績)", v.get("trailing_pe") or "—")
                b2.metric("PER(予想)", v.get("forward_pe") or "—")
                b3.metric("PEG", v.get("peg_ratio") or "—")
                b4.metric("PBR", v.get("price_to_book") or "—")
                b5.metric("EV/EBITDA", v.get("ev_to_ebitda") or "—")
                c1_, c2_, c3_, c4_, c5_ = st.columns(5)
                c1_.metric("ROE", f"{p.get('roe_pct')}%" if p.get("roe_pct") is not None else "—")
                c2_.metric("営業利益率", f"{p.get('operating_margin_pct')}%" if p.get("operating_margin_pct") is not None else "—")
                c3_.metric("売上成長(YoY)", f"{g.get('revenue_growth_yoy_pct')}%" if g.get("revenue_growth_yoy_pct") is not None else "—")
                c4_.metric("配当利回り", f"{dv.get('dividend_yield_pct')}%" if dv.get("dividend_yield_pct") is not None else "—")
                c5_.metric("D/Eレシオ", fh.get("debt_to_equity") or "—")

            # ── 決算 ──
            st.markdown("#### 📅 決算")
            try:
                cal = get_earnings_calendar(sym)
                if "error" not in cal:
                    if cal.get("next_earnings_dates"):
                        est = f"（予想EPS {cal['eps_estimate_avg']}）" if cal.get("eps_estimate_avg") else ""
                        st.write(f"**次回決算予定**: {cal['next_earnings_dates'][0]} {est}")
                    if cal.get("past_surprises"):
                        st.write("**過去のEPSサプライズ**（予想 vs 実績）:")
                        for sp in reversed(cal["past_surprises"]):
                            if sp.get("surprise_pct") is not None:
                                mark = "✅ 上回り" if sp["surprise_pct"] >= 0 else "❌ 下回り"
                                st.write(f"- {sp['quarter']}: 予想 {sp.get('eps_estimate','—')} → 実績 {sp.get('eps_actual','—')}（{sp['surprise_pct']:+.1f}% {mark}）")
            except Exception:
                st.caption("決算カレンダーを取得できませんでした")

            try:
                eh = get_earnings_history(sym)
                if "error" not in eh and eh.get("quarterly"):
                    st.write("**四半期業績**（直近4四半期）:")
                    import pandas as pd
                    rows = []
                    for q_ in eh["quarterly"][:4]:
                        rows.append({
                            "四半期": q_["quarter_end"],
                            "売上": f"{q_['revenue']:,.0f}" if q_.get("revenue") else "—",
                            "売上YoY": f"{q_['revenue_yoy_pct']:+.1f}%" if q_.get("revenue_yoy_pct") is not None else "—",
                            "純利益": f"{q_['net_income']:,.0f}" if q_.get("net_income") else "—",
                            "EPS": q_.get("diluted_eps", "—"),
                        })
                    st.table(pd.DataFrame(rows))
            except Exception:
                pass

            # ── 財務 ──
            try:
                bs = get_balance_sheet_summary(sym)
                if "error" not in bs:
                    st.markdown("#### 🏦 財務健全性")
                    f1, f2, f3, f4 = st.columns(4)
                    f1.metric("現金等", f"{bs['cash_and_equivalents']:,.0f}" if bs.get("cash_and_equivalents") else "—")
                    f2.metric("総負債", f"{bs['total_debt']:,.0f}" if bs.get("total_debt") else "—")
                    f3.metric("ネットキャッシュ", f"{bs['net_cash']:,.0f}" if bs.get("net_cash") is not None else "—")
                    f4.metric("FCF(直近12ヶ月)", f"{bs['free_cash_flow_ttm']:,.0f}" if bs.get("free_cash_flow_ttm") else "—")
            except Exception:
                pass

            st.success("表示完了")

else:
    st.header("🌐 マーケットダッシュボード")
    st.caption("資金フロー（どこにお金が流れたか）・世界の指数・為替・金利・注目ニュースを表示します")

    if st.button("🌐 今の相場を表示", type="primary", use_container_width=True):
        from tools.macro_data import get_global_macro_snapshot, get_fund_flows
        from tools.news_feed import get_stock_news

        def render_group(title, items, price_fmt="{:,.2f}"):
            st.markdown(f"**{title}**")
            cols = st.columns(4)
            for i, item in enumerate(items):
                with cols[i % 4]:
                    if "error" in item:
                        st.caption(f"{item['label']}: 取得不可")
                    else:
                        st.metric(
                            item["label"],
                            price_fmt.format(item["price"]),
                            f"{item['change_1d_pct']:+.2f}%" if item.get("change_1d_pct") is not None else None,
                        )

        # ── 資金フロー分析 ──
        with st.spinner("資金フローを分析中..."):
            try:
                flow = get_fund_flows()
                regime = flow.get("regime", "")
                box = st.success if "オン" in regime else (st.warning if "オフ" in regime else st.info)
                box(f"### 💰 資金フロー判定： {regime}")
                for sig in flow.get("signals", []):
                    st.markdown(f"- {sig}")
                if flow.get("rotation"):
                    st.markdown(f"- 🔄 **セクター循環**: {flow['rotation']}")

                fc1, fc2 = st.columns(2)
                with fc1:
                    st.markdown("**📈 資金が向かったセクター**")
                    for s in flow.get("sector_winners", []):
                        st.markdown(f"- 🟢 {s['label']} {s['change_pct']:+.2f}%")
                with fc2:
                    st.markdown("**📉 資金が抜けたセクター**")
                    for s in flow.get("sector_losers", []):
                        st.markdown(f"- 🔴 {s['label']} {s['change_pct']:+.2f}%")

                st.markdown("**🔀 主要アセットの騰落（株・債券・金・ドル・原油・暗号資産）**")
                render_group("", flow.get("assets", []), "{:,.2f}")
            except Exception as e:
                st.caption(f"資金フロー分析エラー: {e}")

        st.divider()

        # ── グローバル指数・為替・金利・コモディティ ──
        with st.spinner("世界のマーケットデータを取得中...（30秒ほど）"):
            try:
                macro = get_global_macro_snapshot()
                render_group("📊 世界の株価指数", macro.get("global_indices", []), "{:,.0f}")
                st.divider()
                render_group("💱 為替", macro.get("fx", []), "{:,.3f}")
                st.divider()
                render_group("🏦 米国債利回り (%)", macro.get("us_treasury_yields", []), "{:.2f}")
                st.divider()
                render_group("🛢️ コモディティ", macro.get("commodities", []), "{:,.1f}")
            except Exception as e:
                st.error(f"データ取得に失敗しました: {e}")

        st.divider()

        # ── 注目ニュース（市場全体） ──
        st.markdown("### 📰 注目ニュース（政治・世界経済・市場）")
        with st.spinner("ニュースを取得中..."):
            seen = set()
            shown = 0
            for proxy in ["SPY", "^GSPC", "^N225", "DX-Y.NYB"]:
                try:
                    nf = get_stock_news(proxy, 8)
                    for a in nf.get("articles", []):
                        key = a["title"]
                        if key in seen:
                            continue
                        seen.add(key)
                        icon = {"好材料": "🟢", "悪材料": "🔴"}.get(a["sentiment"], "⚪")
                        topic = a.get("topic_jp", "")
                        date = a.get("published") or ""
                        if a.get("link"):
                            st.markdown(f"{icon} {topic} [{a['title']}]({a['link']}) — {a.get('publisher','')} {date}")
                        else:
                            st.markdown(f"{icon} {topic} {a['title']} — {a.get('publisher','')} {date}")
                        shown += 1
                        if shown >= 15:
                            break
                except Exception:
                    continue
                if shown >= 15:
                    break
            if shown == 0:
                st.caption("ニュースを取得できませんでした")

        st.success("表示完了")

