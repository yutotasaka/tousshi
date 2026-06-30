MODEL = "claude-opus-4-8"

DEFAULT_WATCHLIST = {
    "US_INDICES": ["^GSPC", "^NDX", "^DJI", "^RUT", "^VIX"],
    "JP_INDICES": ["^N225", "^TOPX"],
    "SECTORS": ["XLK", "XLF", "XLE", "XLV", "XLI", "XLC", "XLY", "XLP", "XLU", "XLRE", "XLB"],
    "BONDS": ["TLT", "IEF", "SHY", "HYG", "LQD"],
    "COMMODITIES": ["GLD", "SLV", "USO", "UNG"],
    "FX": ["DX-Y.NYB", "EURUSD=X", "JPYUSD=X", "GBPUSD=X"],
    "CRYPTO": ["BTC-USD", "ETH-USD"],
    "MEGA_CAPS": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO"],
}

TECHNICAL_PERIODS = {
    "short": "1mo",
    "medium": "3mo",
    "long": "1y",
}

ANALYSIS_LANGUAGE = "Japanese"
