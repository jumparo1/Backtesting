# Backtesting Tool

## About
Crypto strategy backtesting engine. Describe strategies in plain English, test across 114 altcoins with 5 years of daily data. Outputs win rate, P&L, Sharpe, drawdown and full trade log.

## Stack
- Backend: Python 3.12 (pandas, pyarrow, ccxt, anthropic)
- Frontend: Single HTML file (`ui/index.html`)
- Server: `web_server.py` on port 8877
- Data: Parquet files in `data/cache/` (CoinGecko + Binance)

## How It Works
1. User types strategy in natural language (or uploads TradingView screenshot)
2. Parser converts to composable Rule objects
3. Engine runs candle-by-candle (no look-ahead bias)
4. Orders fill at next bar's open, stop/TP checked against high/low
5. Metrics calculated, equity curve + trade log returned

## Project Structure
```
config/       → settings, coin list
data/         → fetcher, Parquet storage, preprocessor
strategies/   → base class, rule system, NL parser
engine/       → backtest loop, portfolio, orders
indicators/   → SMA, EMA, RSI, MACD, Bollinger, ATR
metrics/      → performance calcs, reporting
vision/       → Claude Vision screenshot analysis
ui/           → single-file web frontend
```

## Conventions
- Files: `snake_case.py` | Classes: `PascalCase` | Functions: `snake_case()`
- Always use type hints (`float | None`, `list[Order]`)
- `@dataclass` for data containers
- Private helpers: `_leading_underscore()`

---

## Your Trading Knowledge
<!-- Paste your trading skills, setups, and strategies below this line -->
<!-- Claude will use this context when helping with backtesting -->


