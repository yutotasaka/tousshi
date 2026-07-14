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
def normalize_input_symbol(sym: str) -> str:
    """4桁の数字（日本株の証券コード）なら .T を付ける"""
    s = sym.strip().upper()
    if s.isdigit() and len(s) == 4:
        return f"{s}.T"
    return s


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


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 機関投資家エージェント")
    st.caption("日本株・米国株の総合マーケット分析（無料）")

    mode = st.radio(
        "メニュー",
        ["⭐ ウォッチリスト（売買判断）", "🎯 銘柄選定", "🌐 マーケット", "🔍 銘柄検索"],
        index=0,
        help="ウォッチリスト＝登録銘柄の買い時/売り時判定 / 銘柄選定＝基準でふるいにかける / マーケット＝相場状況 / 銘柄検索＝個別銘柄の全情報",
    )

    st.divider()
    with st.expander("❓ 使い方", expanded=False):
        st.markdown("""
**⭐ ウォッチリスト**
気になる銘柄を登録すると、平均PERとの比較で「買い増しゾーン/売り検討」を判定。
材料・決算日・テクニカルも加味されます（損益はPayPay証券アプリで確認）

**🎯 銘柄選定**
PER10倍以下・配当利回り2.5%以上・増配傾向・連続増収・ROEなどの基準で✅❌診断

**🌐 マーケット**
資金フロー・世界の指数・為替・金利・注目ニュース

**🔍 銘柄検索**
個別銘柄の総合評価・チャート・ファンダを表示

- 日本株 → 証券コード4桁（例: `7203`）／ 米国株 → ティッカー（例: `AAPL`）
- すべて無料で利用できます
""")


is_watchlist_mode = "ウォッチリスト" in mode
is_screening_mode = "銘柄選定" in mode
is_search_mode = "銘柄検索" in mode


# ── Portfolio manager ─────────────────────────────────────────────────────────
WATCHLIST_FILE = Path("watchlist.json")


def load_watchlist() -> list[str]:
    try:
        if WATCHLIST_FILE.exists():
            data = json.loads(WATCHLIST_FILE.read_text())
            if isinstance(data, list):
                return [str(s) for s in data]
    except Exception:
        pass
    # 旧ポートフォリオから移行
    try:
        if PORTFOLIO_FILE.exists():
            old = json.loads(PORTFOLIO_FILE.read_text())
            if isinstance(old, list):
                return [h["symbol"] for h in old if isinstance(h, dict) and h.get("symbol")]
    except Exception:
        pass
    return []


def save_watchlist(symbols: list[str]) -> None:
    try:
        WATCHLIST_FILE.write_text(json.dumps(symbols, ensure_ascii=False, indent=2))
    except Exception as e:
        st.warning(f"保存に失敗しました: {e}")


if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()


def render_timing(sym: str):
    """買い時・売り時判定カードを描画。"""
    from tools.screening import timing_judgment
    tj = timing_judgment(sym)

    verdict = tj.get("verdict", "⚪ 判定不可")
    advice = tj.get("advice", "")
    if "買い" in verdict:
        box = st.success
    elif "売り" in verdict or "警戒" in verdict:
        box = st.error if "売り検討" in verdict else st.warning
    else:
        box = st.info
    box(f"### {verdict}\n{advice}")

    # PERバンド
    if tj.get("avg_per") and tj.get("current_per"):
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("現在PER", f"{tj['current_per']}倍",
                  f"{tj['deviation_pct']:+.1f}% vs 平均" if tj.get("deviation_pct") is not None else None,
                  delta_color="inverse")
        k2.metric(f"過去平均PER（約{tj.get('per_years_used','—')}年）", f"{tj['avg_per']}倍")
        k3.metric("🟢 買い増し目安", f"{tj['buy_zone_price']:,.0f}", help="過去平均PERの15%割安水準")
        k4.metric("🔴 売り検討目安", f"{tj['sell_zone_price']:,.0f}", help="過去平均PERの20%割高水準")
        cur = tj.get("current_price")
        fair = tj.get("fair_price")
        if cur and fair:
            st.caption(f"現在値 {cur:,.1f} ／ 適正株価の目安（平均PER×EPS）: {fair:,.1f}")

    # 判定理由
    st.markdown("**判定理由：**")
    for f in tj.get("factors", []):
        st.markdown(f"- {f}")

    if tj.get("next_earnings"):
        st.caption(f"📅 次回決算: {tj['next_earnings']}")

    # ニュース
    articles = tj.get("news", [])
    if articles:
        with st.expander(f"📰 直近の材料（{tj.get('news_tone','')}）", expanded=False):
            for a in articles:
                icon = {"好材料": "🟢", "悪材料": "🔴"}.get(a["sentiment"], "⚪")
                topic = a.get("topic_jp", "")
                if a.get("link"):
                    st.markdown(f"{icon} {topic} [{a['title']}]({a['link']}) — {a.get('published','')}")
                else:
                    st.markdown(f"{icon} {topic} {a['title']} — {a.get('published','')}")
    st.caption("※ " + tj.get("disclaimer", ""))


# ── ウォッチリスト（売買判断） ─────────────────────────────────────────────
if is_watchlist_mode:
    st.header("⭐ ウォッチリスト — 買い時・売り時判定")
    st.caption("銘柄を登録するだけでOK（損益はPayPay証券アプリで確認してください）。過去の平均PERと比べて今が割安か割高か、材料・決算・テクニカルを加味して判定します。")

    watchlist = st.session_state.watchlist

    wc1, wc2 = st.columns([3, 1])
    with wc1:
        new_sym_raw = st.text_input("銘柄を追加（証券コード4桁 or ティッカー）",
                                    placeholder="7203 または NVDA", label_visibility="collapsed")
    with wc2:
        if st.button("➕ 追加", use_container_width=True) and new_sym_raw.strip():
            sym = normalize_input_symbol(new_sym_raw)
            if sym not in watchlist:
                watchlist.append(sym)
                save_watchlist(watchlist)
                st.rerun()

    if watchlist:
        st.write("**登録銘柄：** " + " ".join(f"`{s}`" for s in watchlist))
        rm_cols = st.columns(min(len(watchlist), 8))
        for i, s in enumerate(watchlist):
            if rm_cols[i % 8].button(f"🗑 {s}", key=f"rm_{s}"):
                watchlist.remove(s)
                save_watchlist(watchlist)
                st.rerun()

        st.divider()
        if st.button("🎯 全銘柄の売買判定を実行", type="primary", use_container_width=True):
            for s in watchlist:
                st.subheader(f"{'🇯🇵' if s.endswith('.T') else '🇺🇸'} {s}")
                with st.spinner(f"{s} を判定中..."):
                    try:
                        render_timing(s)
                    except Exception as e:
                        st.error(f"{s} の判定に失敗: {e}")
                with st.expander(f"🔬 {s} の詳細評価（総合スコア・好悪材料）", expanded=False):
                    try:
                        render_evaluation(s)
                    except Exception as e:
                        st.caption(f"評価エラー: {e}")
                st.divider()
            st.success("全銘柄の判定完了")
    else:
        st.info("👆 気になる銘柄を追加してください（例: 7203、NVDA、AAPL）")


# ── 銘柄選定（スクリーニング） ─────────────────────────────────────────────
elif is_screening_mode:
    st.header("🎯 銘柄選定 — 基準チェック")
    st.caption("候補銘柄が選定基準を満たすか✅❌で診断します。基準は下で調整できます。")

    with st.expander("⚙️ 選定基準の設定", expanded=False):
        b1, b2, b3 = st.columns(3)
        with b1:
            max_per = st.number_input("PER 上限（倍）", 1.0, 100.0, 10.0, 1.0)
            min_yield = st.number_input("配当利回り 下限（%）", 0.0, 10.0, 2.5, 0.1)
        with b2:
            min_roe = st.number_input("ROE 下限（%）", 0.0, 50.0, 10.0, 1.0)
            min_streak = st.number_input("連続増配 下限（年）", 0, 20, 3, 1)
        with b3:
            max_de = st.number_input("負債比率D/E 上限（%）", 0.0, 500.0, 100.0, 10.0)
            min_opm = st.number_input("営業利益率 下限（%）", 0.0, 50.0, 8.0, 1.0)

    cand_raw = st.text_input(
        "診断する銘柄（カンマ区切りで複数OK）",
        placeholder="例: 7203, 8058, 9433, VZ, MO",
    )
    if st.button("🔍 基準チェック実行", type="primary", use_container_width=True) and cand_raw.strip():
        from tools.screening import check_criteria
        symbols = [normalize_input_symbol(s) for s in cand_raw.replace("、", ",").split(",") if s.strip()]
        results = []
        for s in symbols:
            with st.spinner(f"{s} を診断中..."):
                try:
                    r = check_criteria(
                        s, max_per=max_per, min_dividend_yield=min_yield,
                        min_roe=min_roe, min_dividend_streak=int(min_streak),
                        max_de_ratio=max_de, min_op_margin=min_opm,
                    )
                    results.append(r)
                except Exception as e:
                    st.error(f"{s}: {e}")

        # 合格数順に表示
        results.sort(key=lambda r: r["passed"], reverse=True)
        for r in results:
            grade = r["grade"]
            icon = "🏆" if grade.startswith("S") else ("🥈" if grade.startswith("A") else ("🥉" if grade.startswith("B") else "—"))
            with st.expander(
                f"{icon} {r['symbol']}（{r.get('name','')}）　{r['passed']}/{r['total']} 基準クリア　【{grade}】",
                expanded=grade.startswith(("S", "A")),
            ):
                for chk in r["checks"]:
                    if chk["pass"] is True:
                        mark = "✅"
                    elif chk["pass"] is False:
                        mark = "❌"
                    else:
                        mark = "❔"
                    st.markdown(
                        f"{mark} **{chk['name']}**：{chk['actual']}　"
                        f"<span style='color:gray'>（基準: {chk['threshold']}｜{chk['note']}）</span>",
                        unsafe_allow_html=True,
                    )
                # 配当履歴ミニ表示
                dh = r.get("dividend_history", [])
                if len(dh) >= 3:
                    import pandas as pd
                    df = pd.DataFrame(dh).set_index("year")
                    st.bar_chart(df["dividend"], height=150)
                    st.caption("年間配当の推移（直近約10年）")
                if st.button(f"⭐ {r['symbol']} をウォッチリストに追加", key=f"add_{r['symbol']}"):
                    wl = st.session_state.watchlist
                    if r["symbol"] not in wl:
                        wl.append(r["symbol"])
                        save_watchlist(wl)
                        st.success("追加しました")

    # ── ✨ 注目銘柄ピックアップ ──────────────────────────────────────────
    st.divider()
    st.subheader("✨ 注目銘柄ピックアップ")
    st.caption("日米の主要銘柄を、上の選定基準＋売買タイミング判定で自動スキャンして、今注目の銘柄をランキングします。（15〜20銘柄で1〜2分かかります）")

    from tools.picks import UNIVERSES
    universe_name = st.selectbox("スキャンする銘柄群", list(UNIVERSES.keys()))
    st.caption(f"対象: {len(UNIVERSES[universe_name])}銘柄 — " + ", ".join(UNIVERSES[universe_name][:8]) + " ...")

    if st.button("✨ 注目銘柄をスキャン", type="primary", use_container_width=True):
        from tools.picks import scan_universe

        prog = st.progress(0, text="スキャン準備中...")

        def _cb(i, total, sym):
            prog.progress(i / total, text=f"診断中... {sym}（{i+1}/{total}）")

        results = scan_universe(
            universe_name,
            max_per=max_per, min_dividend_yield=min_yield,
            min_roe=min_roe, min_dividend_streak=int(min_streak),
            max_de_ratio=max_de, min_op_margin=min_opm,
            progress_callback=_cb,
        )
        prog.progress(1.0, text="完了")

        ok_results = [r for r in results if "error" not in r]
        if not ok_results:
            st.error("データを取得できませんでした。時間をおいて再実行してください。")
        else:
            st.markdown("### 🏆 注目銘柄ランキング")
            for rank, r in enumerate(ok_results[:10], 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}位")
                dev = f"　PER乖離 {r['deviation_pct']:+.0f}%" if r.get("deviation_pct") is not None else ""
                with st.expander(
                    f"{medal} {r['symbol']}（{r.get('name','')}）　総合 {r['combined_score']}点　"
                    f"基準 {r['passed']}/{r['total']}　{r['verdict']}{dev}",
                    expanded=rank <= 3,
                ):
                    if r.get("current_per") and r.get("avg_per"):
                        st.caption(f"現在PER {r['current_per']}倍 / 過去平均 {r['avg_per']}倍")
                    st.markdown("**基準チェック：**")
                    line = "　".join(
                        ("✅" if c["pass"] is True else "❌" if c["pass"] is False else "❔") + c["name"].split("（")[0]
                        for c in r["checks"]
                    )
                    st.markdown(line)
                    if r.get("factors"):
                        st.markdown("**売買タイミングの根拠：**")
                        for f in r["factors"][:4]:
                            st.markdown(f"- {f}")
                    if st.button(f"⭐ ウォッチリストに追加", key=f"pick_{r['symbol']}"):
                        wl = st.session_state.watchlist
                        if r["symbol"] not in wl:
                            wl.append(r["symbol"])
                            save_watchlist(wl)
                            st.success("追加しました")
            st.caption("※ スコア = 選定基準クリア率60% + 売買タイミング40%。機械的な参考情報であり、推奨ではありません。")

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

