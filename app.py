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
    ev = cached_evaluation(sym)

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
気になる銘柄を登録すると、妥当PER（過去平均×業種×成長力）との比較で「買い増しゾーン/売り検討」を判定。
材料・決算日・テクニカルも加味されます（損益はPayPay証券アプリで確認）

**🎯 銘柄選定**
PER10倍以下・配当3%以上・配当性向低め・増配・増収増益・ROE・財務健全性の12基準で✅❌診断

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


# ── データ取得キャッシュ（15分）：再描画を速くし、結果消失を防ぐ ──────────────
@st.cache_data(ttl=900, show_spinner=False)
def cached_timing(sym: str) -> dict:
    from tools.screening import timing_judgment
    return timing_judgment(sym)


@st.cache_data(ttl=900, show_spinner=False)
def cached_evaluation(sym: str) -> dict:
    from tools.scoring import evaluate_stock
    return evaluate_stock(sym)


@st.cache_data(ttl=900, show_spinner=False)
def cached_criteria(sym: str, params: tuple) -> dict:
    from tools.screening import check_criteria
    (max_per, min_yield, min_roe, min_streak, max_de, min_opm,
     max_payout, min_rg, min_eg) = params
    return check_criteria(
        sym, max_per=max_per, min_dividend_yield=min_yield,
        min_roe=min_roe, min_dividend_streak=int(min_streak),
        max_de_ratio=max_de, min_op_margin=min_opm,
        max_payout_ratio=max_payout, min_rev_growth=min_rg,
        min_earnings_growth=min_eg,
    )


@st.cache_data(ttl=900, show_spinner=False)
def cached_val(sym: str) -> dict:
    from tools.fundamentals import get_valuation_metrics
    return get_valuation_metrics(sym)


@st.cache_data(ttl=900, show_spinner=False)
def cached_hist(sym: str, period: str) -> dict:
    from tools.market_data import get_price_history
    return get_price_history(sym, period)


@st.cache_data(ttl=900, show_spinner=False)
def cached_cal(sym: str) -> dict:
    from tools.fundamentals import get_earnings_calendar
    return get_earnings_calendar(sym)


@st.cache_data(ttl=900, show_spinner=False)
def cached_eh(sym: str) -> dict:
    from tools.fundamentals import get_earnings_history
    return get_earnings_history(sym)


@st.cache_data(ttl=900, show_spinner=False)
def cached_bs(sym: str) -> dict:
    from tools.fundamentals import get_balance_sheet_summary
    return get_balance_sheet_summary(sym)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_name(sym: str) -> str:
    """銘柄名を取得（1日キャッシュ）。取得できなければコードを返す。"""
    import yfinance as yf
    try:
        info = yf.Ticker(sym).info or {}
        return info.get("shortName") or info.get("longName") or sym
    except Exception:
        return sym


@st.cache_data(ttl=3600, show_spinner=False)
def cached_next_earnings(sym: str) -> dict:
    """次回決算日と会社名を取得（1時間キャッシュ）。"""
    import yfinance as yf
    out = {"symbol": sym, "date": None, "name": sym, "eps_estimate": None}
    try:
        t = yf.Ticker(sym)
        try:
            out["name"] = (t.info or {}).get("shortName", sym)
        except Exception:
            pass
        cal = t.calendar
        if isinstance(cal, dict) and cal.get("Earnings Date"):
            ed = cal["Earnings Date"][0]
            out["date"] = ed.strftime("%Y-%m-%d") if hasattr(ed, "strftime") else str(ed)
            out["eps_estimate"] = cal.get("Earnings Average")
    except Exception:
        pass
    return out


# ── ウォッチリスト（URL・ファイル二重保存で消えないように） ────────────────────
WATCHLIST_FILE = Path("watchlist.json")


def load_watchlist() -> list[str]:
    # 1) URLパラメータ（更新・再デプロイに強い）
    try:
        qp = st.query_params.get("wl", "")
        if qp:
            syms = [s.strip().upper() for s in qp.split(",") if s.strip()]
            if syms:
                return syms
    except Exception:
        pass
    # 2) ファイル
    try:
        if WATCHLIST_FILE.exists():
            data = json.loads(WATCHLIST_FILE.read_text())
            if isinstance(data, list):
                return [str(s) for s in data]
    except Exception:
        pass
    # 3) 旧ポートフォリオから移行
    try:
        if PORTFOLIO_FILE.exists():
            old = json.loads(PORTFOLIO_FILE.read_text())
            if isinstance(old, list):
                return [h["symbol"] for h in old if isinstance(h, dict) and h.get("symbol")]
    except Exception:
        pass
    return []


def save_watchlist(symbols: list[str]) -> None:
    st.session_state.watchlist = symbols
    try:
        WATCHLIST_FILE.write_text(json.dumps(symbols, ensure_ascii=False, indent=2))
    except Exception:
        pass
    # URLにも保存（ブックマークすれば再デプロイ後も復元できる）
    try:
        if symbols:
            st.query_params["wl"] = ",".join(symbols)
        else:
            st.query_params.pop("wl", None)
    except Exception:
        pass


def add_to_watchlist(sym: str) -> bool:
    wl = st.session_state.watchlist
    if sym not in wl:
        wl.append(sym)
        save_watchlist(wl)
        return True
    return False


if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
    # 復元したリストをURLに同期
    if st.session_state.watchlist:
        save_watchlist(st.session_state.watchlist)


def render_timing(sym: str):
    """買い時・売り時判定カードを描画。"""
    tj = cached_timing(sym)

    verdict = tj.get("verdict", "⚪ 判定不可")
    advice = tj.get("advice", "")
    if "買い" in verdict:
        box = st.success
    elif "売り" in verdict or "警戒" in verdict:
        box = st.error if "売り検討" in verdict else st.warning
    else:
        box = st.info
    trend = tj.get("trend", "—")
    trend_icon = "📈" if "上昇" in trend else ("📉" if "下降" in trend else "⏸")
    box(f"### {verdict}　｜　{trend_icon} {trend}\n{advice}")

    # トレンド・RSI・アナリストを常時表示
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("トレンド", f"{trend_icon} {trend}")
    i2.metric("RSI(14)", f"{tj['rsi']:.0f}" if tj.get("rsi") is not None else "—")
    i3.metric("アナリスト評価", tj.get("analyst_rating", "—"),
              f"{tj['analyst_count']}名" if tj.get("analyst_count") else None, delta_color="off")
    i4.metric("目標株価", f"{tj['analyst_target']:,.0f}" if tj.get("analyst_target") else "—",
              f"{tj['analyst_upside_pct']:+.1f}%" if tj.get("analyst_upside_pct") is not None else None)

    # 妥当PERバンド（過去平均・業種標準・成長力のブレンド）
    if tj.get("fair_per") and tj.get("current_per"):
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("現在PER", f"{tj['current_per']}倍",
                  f"{tj['deviation_pct']:+.1f}% vs 妥当PER" if tj.get("deviation_pct") is not None else None,
                  delta_color="inverse")
        k2.metric("妥当PER（3要素ブレンド）", f"{tj['fair_per']}倍",
                  help="過去平均PER50% + 業種標準PER30% + 利益成長率に見合うPER20% の加重平均")
        if tj.get("buy_zone_price"):
            k3.metric("🟢 買い増し目安", f"{tj['buy_zone_price']:,.0f}", help="妥当PERの15%割安水準")
            k4.metric("🔴 売り検討目安", f"{tj['sell_zone_price']:,.0f}", help="妥当PERの20%割高水準")
        cur = tj.get("current_price")
        fair = tj.get("fair_price")
        if cur and fair:
            st.caption(f"現在値 {cur:,.1f} ／ 適正株価の目安（妥当PER×EPS）: {fair:,.1f}")
        comp = tj.get("fair_per_components", {})
        if comp:
            st.caption("内訳：" + " / ".join(f"{k} {v:.0f}倍" for k, v in comp.items())
                       + f"（業種: {tj.get('sector_jp','—')}）")

    # 売りシグナル分析（25日線・MACDデッドクロス・RSI・出来高）
    sell = tj.get("sell_signal")
    if sell and "error" not in sell:
        ss = sell.get("sell_score", 0)
        st.markdown(f"**🔻 売りシグナル分析：{sell.get('level','')}（売り度 {ss}/100）**")
        st.progress(ss / 100)
        st.caption(sell.get("summary", ""))
        if sell.get("sell_signals"):
            for s in sell["sell_signals"]:
                st.markdown(f"- {s}")
        d = sell.get("detail", {})
        if d:
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("25日線乖離", f"{d.get('disparity25_pct','—')}%" if d.get('disparity25_pct') is not None else "—")
            sc2.metric("MACDデッドクロス", "発生" if d.get("macd_dead_cross") else "なし")
            sc3.metric("RSI", f"{d.get('rsi14','—')}")
            sc4.metric("出来高比", f"{d.get('volume_ratio','—')}倍" if d.get('volume_ratio') is not None else "—")

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
        st.markdown("**登録銘柄：**")
        with st.spinner("銘柄名を取得中..."):
            for i, s in enumerate(watchlist):
                flag = "🇯🇵" if s.endswith(".T") else "🇺🇸"
                name = cached_name(s)
                lc, rc = st.columns([5, 1])
                lc.markdown(f"{flag} **{s}**　{name}")
                if rc.button("🗑 削除", key=f"rm_{s}"):
                    watchlist.remove(s)
                    save_watchlist(watchlist)
                    st.rerun()

        # ── 📅 決算カレンダー ──
        st.divider()
        with st.expander("📅 決算カレンダー（登録銘柄の次回決算）", expanded=True):
            if st.button("📅 決算予定を更新", key="refresh_earnings"):
                cached_next_earnings.clear()
            import datetime as _dt
            rows = []
            with st.spinner("決算予定を取得中..."):
                for s in watchlist:
                    info = cached_next_earnings(s)
                    rows.append(info)
            dated = [r for r in rows if r.get("date")]
            undated = [r for r in rows if not r.get("date")]
            # 日付順ソート
            def _parse(d):
                try:
                    return _dt.datetime.strptime(d[:10], "%Y-%m-%d").date()
                except Exception:
                    return _dt.date(2100, 1, 1)
            dated.sort(key=lambda r: _parse(r["date"]))
            today = _dt.date.today()
            if dated:
                for r in dated:
                    d = _parse(r["date"])
                    days = (d - today).days
                    if days < 0:
                        badge = "🔘 発表済/未定"
                    elif days == 0:
                        badge = "🔴 本日"
                    elif days <= 7:
                        badge = f"🔴 あと{days}日"
                    elif days <= 30:
                        badge = f"🟠 あと{days}日"
                    else:
                        badge = f"🟢 あと{days}日"
                    flag = "🇯🇵" if r["symbol"].endswith(".T") else "🇺🇸"
                    est = f"　予想EPS {r['eps_estimate']}" if r.get("eps_estimate") else ""
                    st.markdown(f"**{r['date']}**　{badge}　{flag} `{r['symbol']}` {r.get('name','')}{est}")
            if undated:
                st.caption("決算日未取得: " + "、".join(f"`{r['symbol']}`" for r in undated)
                           + "（日本株はYahoo Financeで取得できないことが多いです）")
            if not dated and not undated:
                st.caption("銘柄がありません")

        st.divider()
        jc1, jc2 = st.columns([3, 1])
        with jc1:
            if st.button("🎯 全銘柄の売買判定を実行", type="primary", use_container_width=True):
                st.session_state.wl_show_results = True
                # 最新データで再判定したい場合に備えキャッシュをクリア
                cached_timing.clear()
                cached_evaluation.clear()
        with jc2:
            if st.session_state.get("wl_show_results") and st.button("結果を閉じる", use_container_width=True):
                st.session_state.wl_show_results = False
                st.rerun()

        if st.session_state.get("wl_show_results"):
            for s in watchlist:
                st.subheader(f"{'🇯🇵' if s.endswith('.T') else '🇺🇸'} {s}　{cached_name(s)}")
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
            st.success("全銘柄の判定完了（結果は画面を操作しても保持されます）")
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
            min_yield = st.number_input("配当利回り 下限（%）", 0.0, 10.0, 3.0, 0.1)
            max_payout = st.number_input("配当性向 上限（%）", 10.0, 100.0, 60.0, 5.0,
                                         help="低いほど無理なく配当を払えている＝増配余力あり")
        with b2:
            min_roe = st.number_input("ROE 下限（%）", 0.0, 50.0, 10.0, 1.0)
            min_streak = st.number_input("連続増配 下限（年）", 0, 20, 3, 1)
            min_eg = st.number_input("利益成長 下限（前年比%）", -50.0, 100.0, 0.0, 1.0,
                                     help="0なら減益でないこと")
        with b3:
            max_de = st.number_input("負債比率D/E 上限（%）", 0.0, 500.0, 100.0, 10.0)
            min_opm = st.number_input("営業利益率 下限（%）", 0.0, 50.0, 8.0, 1.0)
            min_rg = st.number_input("増収率 下限（前年比%）", -50.0, 100.0, 3.0, 1.0)

    cand_raw = st.text_input(
        "診断する銘柄（カンマ区切りで複数OK）",
        placeholder="例: 7203, 8058, 9433, VZ, MO",
    )
    crit_params = (max_per, min_yield, min_roe, int(min_streak), max_de, min_opm,
                   max_payout, min_rg, min_eg)

    if st.button("🔍 基準チェック実行", type="primary", use_container_width=True) and cand_raw.strip():
        symbols = [normalize_input_symbol(s) for s in cand_raw.replace("、", ",").split(",") if s.strip()]
        results = []
        for s in symbols:
            with st.spinner(f"{s} を診断中..."):
                try:
                    r = cached_criteria(s, crit_params)
                    results.append(r)
                except Exception as e:
                    st.error(f"{s}: {e}")
        results.sort(key=lambda r: r["passed"], reverse=True)
        st.session_state.check_results = results

    # 結果はセッションに保持（ボタンを押しても消えない）
    if st.session_state.get("check_results"):
        results = st.session_state.check_results
        for r in results:
            grade = r["grade"]
            icon = "🏆" if grade.startswith("S") else ("🥈" if grade.startswith("A") else ("🥉" if grade.startswith("B") else "—"))
            with st.expander(
                f"{icon} {r['symbol']}（{r.get('name','')}）　{r['passed']}/{r['total']} 基準クリア　【{grade}】",
                expanded=grade.startswith(("S", "A")),
            ):
                unknown = [chk for chk in r["checks"] if chk["pass"] is None]
                for chk in r["checks"]:
                    if chk["pass"] is True:
                        st.markdown(
                            f"✅ **{chk['name']}**：{chk['actual']}　"
                            f"<span style='color:gray'>（基準: {chk['threshold']}｜{chk['note']}）</span>",
                            unsafe_allow_html=True,
                        )
                    elif chk["pass"] is False:
                        st.markdown(
                            f"❌ **{chk['name']}**：{chk['actual']}　"
                            f"<span style='color:gray'>（基準: {chk['threshold']}｜{chk['note']}）</span>",
                            unsafe_allow_html=True,
                        )
                if unknown:
                    st.caption("📭 データが取得できず判定対象外： " + "、".join(chk["name"] for chk in unknown)
                               + "（合格/不合格には数えていません）")
                # 配当履歴ミニ表示
                dh = r.get("dividend_history", [])
                if len(dh) >= 3:
                    import pandas as pd
                    df = pd.DataFrame(dh).set_index("year")
                    st.bar_chart(df["dividend"], height=150)
                    st.caption("年間配当の推移（直近約10年）")
                if r["symbol"] in st.session_state.watchlist:
                    st.caption("⭐ ウォッチリスト登録済み")
                elif st.button(f"⭐ {r['symbol']} をウォッチリストに追加", key=f"add_{r['symbol']}"):
                    add_to_watchlist(r["symbol"])
                    st.success("追加しました（結果はこのまま保持されます）")

    # ── ✨ 注目銘柄ピックアップ ──────────────────────────────────────────
    st.divider()
    st.subheader("✨ 注目銘柄ピックアップ")
    st.caption("日米の主要銘柄を、上の選定基準＋売買タイミング判定で自動スキャンして、今注目の銘柄をランキングします。（15〜20銘柄で1〜2分かかります）")

    from tools.picks import UNIVERSES

    CUSTOM_UNIVERSE_FILE = Path("custom_universe.json")

    def load_custom_universe() -> list[str]:
        # セッション（メモリ）優先 → ファイルの順で読む（クラウドはファイルが消えることがあるため）
        if st.session_state.get("custom_universe"):
            return st.session_state.custom_universe
        try:
            if CUSTOM_UNIVERSE_FILE.exists():
                data = json.loads(CUSTOM_UNIVERSE_FILE.read_text())
                if isinstance(data, list) and data:
                    st.session_state.custom_universe = data
                    return data
        except Exception:
            pass
        return []

    # ── カスタムリスト登録（プルダウンより先に処理して即反映させる） ──
    with st.expander("📋 カスタムリスト（PayPay公式の銘柄コードを貼り付けて保存）",
                     expanded=not bool(load_custom_universe())):
        st.caption("PayPay証券アプリ/サイトの取扱銘柄一覧から銘柄コードをコピーして貼り付けてください。"
                   "カンマ・スペース・改行区切りOK。日本株は4桁の数字（例: 7203）、米国株は英字ティッカー（例: AAPL）。"
                   "社名（トヨタ等）は無視されるので、必ずコード/ティッカーを貼ってください。")
        paste = st.text_area("銘柄コードを貼り付け", placeholder="7203, 8058, 9433\nAAPL MSFT NVDA ...", height=100)
        if st.button("💾 カスタムリストとして保存"):
            if not paste.strip():
                st.error("貼り付け欄が空です")
            else:
                import re
                tokens = re.split(r"[,、\s\n\t]+", paste.strip())
                syms, ignored = [], []
                for tk in tokens:
                    tk = tk.strip().upper().replace("．", ".")
                    if not tk:
                        continue
                    # 有効なパターンのみ受け付ける
                    if re.fullmatch(r"\d{4}", tk):
                        syms.append(f"{tk}.T")
                    elif re.fullmatch(r"\d{4}\.T", tk):
                        syms.append(tk)
                    elif re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,7}", tk):
                        syms.append(tk)
                    else:
                        ignored.append(tk)
                syms = sorted(set(syms))
                if not syms:
                    st.error("有効な銘柄コードが見つかりませんでした。数字4桁（日本株）または英字ティッカー（米国株）を貼り付けてください。"
                             + (f"（無視された例: {', '.join(ignored[:5])}）" if ignored else ""))
                else:
                    st.session_state.custom_universe = syms  # メモリに即保存（これで確実に反映）
                    try:
                        CUSTOM_UNIVERSE_FILE.write_text(json.dumps(syms, ensure_ascii=False, indent=1))
                    except Exception:
                        pass  # ファイル保存に失敗してもセッションで動く
                    st.success(f"✅ {len(syms)}銘柄を登録しました！下のプルダウンに「カスタム」が追加されています。")
                    if ignored:
                        st.warning(f"コードとして認識できず無視したもの（{len(ignored)}件）: " + ", ".join(ignored[:10]))

        if load_custom_universe():
            cur = load_custom_universe()
            st.caption(f"現在の登録: {len(cur)}銘柄 — " + ", ".join(cur[:10]) + (" ..." if len(cur) > 10 else ""))
            if st.button("🗑 カスタムリストを削除"):
                st.session_state.custom_universe = []
                try:
                    CUSTOM_UNIVERSE_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                st.rerun()

    custom_syms = load_custom_universe()
    universe_options = list(UNIVERSES.keys())
    custom_label = f"カスタム（自分で登録した{len(custom_syms)}銘柄）"
    if custom_syms:
        universe_options.insert(0, custom_label)  # 先頭に置いて選びやすく

    universe_name = st.selectbox(
        "スキャンする銘柄群", universe_options,
        index=0,
    )

    if universe_name.startswith("カスタム"):
        scan_targets = custom_syms
    else:
        scan_targets = UNIVERSES[universe_name]
    st.caption(f"対象: {len(scan_targets)}銘柄 — " + ", ".join(scan_targets[:8]) + " ...")
    if "PayPay" in universe_name:
        st.caption("⚠️ PayPay証券リストは参考版です（公式の最新取扱銘柄と多少異なる場合があります）。正確なリストは上の「カスタムリスト」から登録できます。")

    est_min = max(1, round(len(scan_targets) * 3 / 60))
    st.caption(f"⏱ 予想所要時間: 約{est_min}分（{len(scan_targets)}銘柄）")

    if st.button("✨ 注目銘柄をスキャン", type="primary", use_container_width=True):
        from tools.picks import scan_symbols

        prog = st.progress(0, text="スキャン準備中...")

        def _cb(i, total, sym):
            prog.progress(i / total, text=f"診断中... {sym}（{i+1}/{total}）")

        results = scan_symbols(
            scan_targets,
            max_per=max_per, min_dividend_yield=min_yield,
            min_roe=min_roe, min_dividend_streak=int(min_streak),
            max_de_ratio=max_de, min_op_margin=min_opm,
            max_payout_ratio=max_payout, min_rev_growth=min_rg,
            min_earnings_growth=min_eg,
            progress_callback=_cb,
        )
        prog.progress(1.0, text="完了")
        st.session_state.scan_results = results
        st.session_state.scan_universe_label = universe_name

    # スキャン結果はセッションに保持（ボタンを押しても消えない）
    if st.session_state.get("scan_results"):
        results = st.session_state.scan_results
        if st.session_state.get("scan_universe_label"):
            st.caption(f"スキャン結果: {st.session_state.scan_universe_label}")
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
                    ok_names = [x["name"].split("（")[0] for x in r["checks"] if x["pass"] is True]
                    ng_names = [x["name"].split("（")[0] for x in r["checks"] if x["pass"] is False]
                    na_count = sum(1 for x in r["checks"] if x["pass"] is None)
                    if ok_names:
                        st.markdown("✅ 合格： " + "、".join(dict.fromkeys(ok_names)))
                    if ng_names:
                        st.markdown("❌ 未達： " + "、".join(dict.fromkeys(ng_names)))
                    if na_count:
                        st.caption(f"📭 データ取得できず判定対象外: {na_count}項目")
                    if r.get("factors"):
                        st.markdown("**売買タイミングの根拠：**")
                        for f in r["factors"][:4]:
                            st.markdown(f"- {f}")
                    if r["symbol"] in st.session_state.watchlist:
                        st.caption("⭐ ウォッチリスト登録済み")
                    elif st.button(f"⭐ ウォッチリストに追加", key=f"pick_{r['symbol']}"):
                        add_to_watchlist(r["symbol"])
                        st.success("追加しました（結果はこのまま保持されます）")
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
        st.session_state.search_sym = normalize_input_symbol(search_sym_raw)

    # 検索結果はセッションに保持（他の操作をしても消えない）
    if st.session_state.get("search_sym"):
        sym = st.session_state.search_sym
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
                val = cached_val(sym)
            except Exception as e:
                val = {"error": str(e)}

            hist = cached_hist(sym, "6mo")

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
            if sym in st.session_state.watchlist:
                st.caption("⭐ ウォッチリスト登録済み")
            elif st.button(f"⭐ {sym} をウォッチリストに追加", key=f"srch_add_{sym}"):
                add_to_watchlist(sym)
                st.success("追加しました")
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
                cal = cached_cal(sym)
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
                eh = cached_eh(sym)
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
                bs = cached_bs(sym)
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

