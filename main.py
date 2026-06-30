#!/usr/bin/env python3
"""
機関投資家エージェント CLI
"""
import argparse
import os
import sys

from rich.console import Console

console = Console()


def check_api_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[bold red]エラー: ANTHROPIC_API_KEY 環境変数が設定されていません。[/bold red]")
        console.print("export ANTHROPIC_API_KEY='your-api-key' を実行してください。")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="機関投資家エージェント — Claude claude-opus-4-8 による総合マーケット分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python main.py                          # 標準の日次総合分析
  python main.py --target "NVDA"          # NVDAに焦点を当てた分析
  python main.py --context "FOMCが今夜"   # 追加コンテキストを与えて分析
        """,
    )
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="特定の銘柄・セクター・テーマに焦点を当てた分析 (例: NVDA, 半導体セクター)",
    )
    parser.add_argument(
        "--context",
        type=str,
        default="",
        help="分析に加える補足情報 (例: 「本日FOMCがある」「決算シーズン真っ只中」)",
    )
    args = parser.parse_args()

    check_api_key()

    from agent import run_analysis
    run_analysis(target=args.target, extra_context=args.context)


if __name__ == "__main__":
    main()
