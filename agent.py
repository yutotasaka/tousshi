"""
Institutional investor agent — orchestrates Claude with tool use to produce
comprehensive market analysis from an institutional perspective.
"""
import json
import os
from datetime import datetime

import anthropic
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from config import MODEL, DEFAULT_WATCHLIST
from tools.market_data import (
    MARKET_SNAPSHOT_TOOL,
    PRICE_HISTORY_TOOL,
    dispatch as market_dispatch,
)
from tools.technical_analysis import TECHNICAL_ANALYSIS_TOOL, dispatch as ta_dispatch
from tools.news_search import WEB_SEARCH_TOOL

console = Console()

CUSTOM_TOOLS = [MARKET_SNAPSHOT_TOOL, PRICE_HISTORY_TOOL, TECHNICAL_ANALYSIS_TOOL]
ALL_TOOLS = CUSTOM_TOOLS + [WEB_SEARCH_TOOL]

SYSTEM_PROMPT = """あなたは経験豊富なマクロ系ヘッジファンドのチーフストラテジストです。
機関投資家の視点で市場分析を行い、以下の観点を必ず網羅してください：

1. **マクロ環境** — 金利、インフレ、中央銀行政策、地政学リスク
2. **セクターローテーション** — 資金フローの方向性、強弱セクターの特定
3. **テクニカル分析** — RSI、MACD、ボリンジャーバンド、出来高、サポート/レジスタンス
4. **市場の材料・カタリスト** — 最新ニュース、決算、経済指標
5. **センチメント・ポジショニング** — VIX、恐怖貪欲指数、資金フロー
6. **売買戦略** — エントリー/エグジットポイント、リスク管理、ポジションサイジング

分析は日本語で行い、機関投資家が実際に意思決定に使用できるレベルの深度で記述してください。
数値とロジックを明確に示し、曖昧な表現を避けてください。"""

ANALYSIS_PROMPT = """本日（{date}）の機関投資家向け総合マーケット分析を実施してください。

以下のステップで体系的に分析を進めてください：

**Step 1: マーケット概況の把握**
主要指数（SPX、NDX、DJI、RUT、VIX、日経225）の現在値と前日比を取得する。

**Step 2: セクター分析**
全11セクターETFの騰落率を取得し、資金フローとローテーションの方向性を分析する。

**Step 3: クロスアセット分析**
債券（TLT、HYG）、コモディティ（GLD、USO）、ドル指数（DX-Y.NYB）を確認する。

**Step 4: 重点銘柄のテクニカル分析**
S&P500（^GSPC）とNASDAQ（^NDX）の3ヶ月チャートを取得し、テクニカル指標を算出する。
さらに、最も強いセクターの代表銘柄1-2つについてもテクニカル分析を実施する。

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

具体的な数値、価格レベル、パーセンテージを必ず含めること。"""


def _dispatch_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name in ("get_market_snapshot", "get_price_history"):
        return market_dispatch(tool_name, tool_input)
    elif tool_name == "run_technical_analysis":
        return ta_dispatch(tool_name, tool_input)
    else:
        return json.dumps({"error": f"Unknown local tool: {tool_name}"})


def run_analysis(target: str | None = None, extra_context: str = "") -> None:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    date_str = datetime.now().strftime("%Y年%m月%d日")
    user_content = ANALYSIS_PROMPT.format(date=date_str)
    if target:
        user_content += f"\n\n**追加指示**: {target}"
    if extra_context:
        user_content += f"\n\n**補足情報**: {extra_context}"

    messages = [{"role": "user", "content": user_content}]

    console.print(Panel(
        f"[bold cyan]機関投資家エージェント 起動[/bold cyan]\n"
        f"[dim]モデル: {MODEL} | 日付: {date_str}[/dim]",
        border_style="cyan",
    ))

    iteration = 0
    max_iterations = 20

    while iteration < max_iterations:
        iteration += 1
        console.print(f"\n[dim]─── エージェントループ #{iteration} ───[/dim]")

        # Stream the response
        full_text = ""
        tool_uses = []
        stop_reason = None

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
                        if block.type == "text":
                            pass
                        elif block.type == "thinking":
                            console.print("[dim italic]💭 思考中...[/dim italic]")
                        elif block.type == "tool_use":
                            console.print(f"[yellow]🔧 ツール呼び出し: {block.name}[/yellow]")

                elif event_type == "RawContentBlockDeltaEvent":
                    delta = event.delta
                    if hasattr(delta, "text"):
                        full_text += delta.text
                        # Print text incrementally
                        console.print(delta.text, end="")

            final_msg = stream.get_final_message()
            stop_reason = final_msg.stop_reason

            # Collect tool uses from final message
            for block in final_msg.content:
                if hasattr(block, "type") and block.type == "tool_use":
                    tool_uses.append(block)

        if full_text:
            console.print()  # newline after streaming text

        # Add assistant response to messages
        messages.append({"role": "assistant", "content": final_msg.content})

        if stop_reason == "end_turn" or not tool_uses:
            console.print("\n[bold green]✅ 分析完了[/bold green]")
            break

        if stop_reason == "tool_use":
            tool_results = []
            for tool_use in tool_uses:
                console.print(f"[cyan]  → {tool_use.name}({json.dumps(tool_use.input, ensure_ascii=False)[:120]})[/cyan]")
                result_str = _dispatch_tool(tool_use.name, tool_use.input)
                result_preview = result_str[:200] + "..." if len(result_str) > 200 else result_str
                console.print(f"[dim]  ← {result_preview}[/dim]")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_str,
                })

            messages.append({"role": "user", "content": tool_results})

    if iteration >= max_iterations:
        console.print("[red]⚠️ 最大イテレーション数に達しました[/red]")
