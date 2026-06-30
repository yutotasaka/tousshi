# 機関投資家エージェント (tousshi)

Claude claude-opus-4-8 を使った機関投資家向け総合マーケット分析エージェント。

## セットアップ

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY='your-api-key'
```

## 使い方

```bash
# 標準の日次総合分析
python main.py

# 特定銘柄に焦点
python main.py --target "NVDA"

# 補足コンテキストを追加
python main.py --context "本日FOMC議事録公開"
```

## アーキテクチャ

```
main.py          - CLIエントリーポイント
agent.py         - Claude APIエージェントループ (tool use + streaming)
config.py        - ウォッチリスト・設定
tools/
  market_data.py      - yfinance による価格・出来高データ取得
  technical_analysis.py - RSI/MACD/ボリンジャーバンド/ATR 計算
  news_search.py      - Claude API web_search サーバーサイドツール定義
```

## 使用ツール

| ツール | 種別 | 説明 |
|--------|------|------|
| `get_market_snapshot` | カスタム (yfinance) | 複数銘柄の現在値・前日比・出来高 |
| `get_price_history` | カスタム (yfinance) | OHLCV ヒストリカルデータ |
| `run_technical_analysis` | カスタム (pandas/numpy) | テクニカル指標一括計算 |
| `web_search` | サーバーサイド (Anthropic) | ニュース・材料収集 |

## 分析カバレッジ

- マクロ環境（金利・インフレ・地政学）
- セクターローテーション（全11セクターETF）
- クロスアセット（株・債券・商品・FX・暗号資産）
- テクニカル分析（主要指数・強弱銘柄）
- 材料・カタリスト（最新ニュース・経済指標）
- 機関投資家向け売買戦略・リスク管理
