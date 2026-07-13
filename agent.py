"""
Institutional investor agent — orchestrates Claude with tool use to produce
comprehensive market analysis from an institutional perspective.
"""
import json
import os
from datetime import datetime
from typing import Generator

import anthropic

from config import MODEL
from tools.market_data import (
    MARKET_SNAPSHOT_TOOL,
    PRICE_HISTORY_TOOL,
    dispatch as market_dispatch,
)
from tools.technical_analysis import TECHNICAL_ANALYSIS_TOOL, dispatch as ta_dispatch
from tools.news_search import WEB_SEARCH_TOOL
from tools.portfolio import (
    PORTFOLIO_SNAPSHOT_TOOL,
    PORTFOLIO_RISK_TOOL,
    dispatch as portfolio_dispatch,
)
from tools.fundamentals import (
    EARNINGS_HISTORY_TOOL,
    EARNINGS_CALENDAR_TOOL,
    BALANCE_SHEET_TOOL,
    VALUATION_METRICS_TOOL,
    dispatch as fundamentals_dispatch,
)

CUSTOM_TOOLS = [
    MARKET_SNAPSHOT_TOOL,
    PRICE_HISTORY_TOOL,
    TECHNICAL_ANALYSIS_TOOL,
    PORTFOLIO_SNAPSHOT_TOOL,
    PORTFOLIO_RISK_TOOL,
    EARNINGS_HISTORY_TOOL,
    EARNINGS_CALENDAR_TOOL,
    BALANCE_SHEET_TOOL,
    VALUATION_METRICS_TOOL,
]
ALL_TOOLS = CUSTOM_TOOLS + [WEB_SEARCH_TOOL]

SYSTEM_PROMPT = """あなたは経験豊富なマクロ系ヘッジファンドのチーフストラテジストです。
機関投資家の視点で市場分析を行い、以下の観点を必ず網羅してください：

1. **マクロ環境** — 金利、インフレ、中央銀行政策、地政学リスク
2. **セクターローテーション** — 資金フローの方向性、強弱セクターの特定
3. **テクニカル分析** — RSI、MACD、ボリンジャーバンド、出来高、サポート/レジスタンス
4. **市場の材料・カタリスト** — 最新ニュース、決算、経済指標
5. **センチメント・ポジショニング** — VIX、恐怖貪欲指数、資金フロー
6. **売買戦略** — エントリー/エグジットポイント、リスク管理、ポジションサイジング

ポートフォリオ分析の場合は追加で：
- 各ポジションのP&L状況と今後の見通し
- アナリストコンセンサスと目標株価との乖離
- ポートフォリオ全体のリスク（ベータ、集中リスク、相関）
- 監視すべき重要な価格・指標レベル
- リバランス・ヘッジの提案

ファンダメンタルズ分析ツールが利用可能です：
- get_earnings_history: 四半期・年次の売上/純利益/EPSとYoY・QoQ成長率
- get_earnings_calendar: 次回決算日・予想EPS/売上・過去のサプライズ実績
- get_balance_sheet_summary: 現金・負債・ネットキャッシュ・FCF
- get_valuation_metrics: PER/PEG/PBR/EV/EBITDA/ROE/ROA/マージン/配当

個別銘柄を分析する際は、テクニカルだけでなく必ずこれらのファンダメンタルズも確認し、
バリュエーションの妥当性・決算カタリスト・財務健全性を統合した判断を示してください。

分析は日本語で行い、機関投資家が実際に意思決定に使用できるレベルの深度で記述してください。
数値とロジックを明確に示し、曖昧な表現を避けてください。"""

MARKET_PROMPT = """本日（{date}）の機関投資家向け総合マーケット分析を実施してください。

以下のステップで体系的に分析を進めてください：

**Step 1: マーケット概況**
主要指数（SPX、NDX、DJI、RUT、VIX、日経225）の現在値と前日比を取得する。

**Step 2: セクター分析**
全11セクターETFの騰落率を取得し、資金フローとローテーションの方向性を分析する。

**Step 3: クロスアセット分析**
債券（TLT、HYG）、コモディティ（GLD、USO）、ドル指数（DX-Y.NYB）を確認する。

**Step 4: テクニカル分析**
S&P500（^GSPC）とNASDAQ（^NDX）の3ヶ月チャートを取得しテクニカル指標を算出する。

**Step 5: 材料・ニュース収集**
本日の重要な市場材料、マクロイベント、地政学リスクをウェブ検索で収集する。

**Step 6: 総合レポート作成**
以下の構成で詳細な機関投資家向けレポートを日本語で作成する：

---
## 📊 本日の総括
## 🌍 マクロ環境
## 🔄 セクターローテーション
## 📈 テクニカル分析
## 📰 本日の主要材料・カタリスト
## 💼 機関投資家向け売買戦略
## ⚠️ リスクシナリオ
---

具体的な数値、価格レベル、パーセンテージを必ず含めること。{extra}"""

PORTFOLIO_PROMPT = """本日（{date}）、以下のポートフォリオを機関投資家の視点で総合分析してください。

**ポートフォリオ：**
{portfolio_text}

以下のステップで分析を進めてください：

**Step 1: ポートフォリオ現況把握**
get_portfolio_snapshot で各ポジションの現在値・損益・アナリスト評価を取得する。

**Step 2: リスク分析**
get_portfolio_risk でポートフォリオベータ・相関・集中リスクを算出する。

**Step 3: 市場環境確認**
主要指数・VIX・関連セクターの現況を取得する。

**Step 4: 各銘柄のテクニカル分析**
保有銘柄それぞれの3ヶ月チャートを取得しテクニカル指標を算出する。

**Step 5: ファンダメンタルズ分析**
各保有銘柄について get_valuation_metrics（PER/PEG/ROE等）と get_earnings_calendar
（次回決算日・予想・過去サプライズ）を取得する。主要ポジションは get_earnings_history
と get_balance_sheet_summary で業績トレンド・財務健全性も確認する。

**Step 6: 最新材料収集**
保有銘柄・関連セクターの最新ニュース・アナリストレポートをウェブ検索で収集する。

**Step 7: 総合レポート作成**

---
## 📊 ポートフォリオ現況サマリー
## 💰 各ポジション分析（損益・アナリスト評価・テクニカル）
## 📑 ファンダメンタルズ評価（バリュエーション・業績トレンド・次回決算）
## ⚖️ リスク評価（ベータ・集中リスク・相関）
## 📰 最新材料・カタリスト
## 🎯 監視すべき重要レベル
## 💼 売買アドバイス（買い増し・利確・損切り・ヘッジ）
## 🔄 リバランス提案
## ⚠️ リスクシナリオ
---

具体的な数値と根拠を必ず示すこと。{extra}"""


def _dispatch_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name in ("get_market_snapshot", "get_price_history"):
        return market_dispatch(tool_name, tool_input)
    elif tool_name == "run_technical_analysis":
        return ta_dispatch(tool_name, tool_input)
    elif tool_name in ("get_portfolio_snapshot", "get_portfolio_risk"):
        return portfolio_dispatch(tool_name, tool_input)
    elif tool_name in (
        "get_earnings_history",
        "get_earnings_calendar",
        "get_balance_sheet_summary",
        "get_valuation_metrics",
    ):
        return fundamentals_dispatch(tool_name, tool_input)
    else:
        return json.dumps({"error": f"Unknown local tool: {tool_name}"})


def stream_analysis(
    mode: str = "market",
    holdings: list[dict] | None = None,
    target: str = "",
    extra_context: str = "",
) -> Generator[dict, None, None]:
    """
    Generator that yields events:
      {"type": "text", "content": str}
      {"type": "tool_start", "name": str}
      {"type": "tool_result", "name": str, "preview": str}
      {"type": "thinking"}
      {"type": "done"}
      {"type": "error", "content": str}
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    date_str = datetime.now().strftime("%Y年%m月%d日")

    if mode == "portfolio" and holdings:
        portfolio_text = "\n".join(
            f"- {h['symbol']}: {h['shares']}株 @ ${h['avg_cost']}" for h in holdings
        )
        extra = f"\n\n**補足情報**: {extra_context}" if extra_context else ""
        if target:
            extra += f"\n**追加指示**: {target}"
        user_content = PORTFOLIO_PROMPT.format(
            date=date_str, portfolio_text=portfolio_text, extra=extra
        )
    else:
        extra = ""
        if target:
            extra += f"\n\n**追加指示**: {target}に焦点を当てた詳細分析も追加してください。"
        if extra_context:
            extra += f"\n\n**補足情報**: {extra_context}"
        user_content = MARKET_PROMPT.format(date=date_str, extra=extra)

    messages = [{"role": "user", "content": user_content}]
    iteration = 0
    max_iterations = 25

    while iteration < max_iterations:
        iteration += 1
        tool_uses = []

        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                thinking={"type": "adaptive"},
                tools=ALL_TOOLS,
                messages=messages,
            ) as stream:
                for event in stream:
                    event_type = type(event).__name__

                    if event_type == "RawContentBlockStartEvent":
                        block = event.content_block
                        if hasattr(block, "type"):
                            if block.type == "thinking":
                                yield {"type": "thinking"}
                            elif block.type == "tool_use":
                                yield {"type": "tool_start", "name": block.name}

                    elif event_type == "RawContentBlockDeltaEvent":
                        delta = event.delta
                        if hasattr(delta, "text") and delta.text:
                            yield {"type": "text", "content": delta.text}

                final_msg = stream.get_final_message()
                stop_reason = final_msg.stop_reason

                for block in final_msg.content:
                    if hasattr(block, "type") and block.type == "tool_use":
                        tool_uses.append(block)

        except Exception as e:
            yield {"type": "error", "content": str(e)}
            return

        messages.append({"role": "assistant", "content": final_msg.content})

        if stop_reason == "end_turn" or not tool_uses:
            break

        if stop_reason == "tool_use":
            tool_results = []
            for tool_use in tool_uses:
                result_str = _dispatch_tool(tool_use.name, tool_use.input)
                preview = result_str[:300] + "..." if len(result_str) > 300 else result_str
                yield {"type": "tool_result", "name": tool_use.name, "preview": preview}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_str,
                })
            messages.append({"role": "user", "content": tool_results})

    yield {"type": "done"}


# CLI fallback
def run_analysis(target: str | None = None, extra_context: str = "") -> None:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()

    date_str = datetime.now().strftime("%Y年%m月%d日")
    console.print(Panel(
        f"[bold cyan]機関投資家エージェント 起動[/bold cyan]\n[dim]モデル: {MODEL} | 日付: {date_str}[/dim]",
        border_style="cyan",
    ))

    for event in stream_analysis(mode="market", target=target or "", extra_context=extra_context):
        if event["type"] == "text":
            console.print(event["content"], end="")
        elif event["type"] == "thinking":
            console.print("\n[dim italic]💭 思考中...[/dim italic]")
        elif event["type"] == "tool_start":
            console.print(f"\n[yellow]🔧 {event['name']}[/yellow]")
        elif event["type"] == "tool_result":
            console.print(f"[dim]← {event['preview']}[/dim]")
        elif event["type"] == "done":
            console.print("\n\n[bold green]✅ 分析完了[/bold green]")
        elif event["type"] == "error":
            console.print(f"\n[red]エラー: {event['content']}[/red]")
