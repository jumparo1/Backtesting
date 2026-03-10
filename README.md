# Backtesting Tool

Crypto strategy backtesting engine — describe strategies in plain English, test across 108 altcoins.

## Live

- **Frontend:** [jumptrading.netlify.app/backtesting.html](https://jumptrading.netlify.app/backtesting.html)
- **Backend API:** [backtesting-api-6vb0.onrender.com](https://backtesting-api-6vb0.onrender.com) (free tier — may take ~30s to wake up)

## Features

- **Natural Language Input** — Describe strategies in plain English (e.g., "buy when RSI below 30, sell when overbought")
- **Multi-Coin Testing** — Test across 108 cryptocurrencies simultaneously with comparison table
- **Pre-built Strategies** — CRT + CISD, RSI oversold, golden cross, MACD crossover, Bollinger bands, and more
- **Screenshot Analysis** — Upload TradingView chart screenshots, Claude Vision extracts the strategy automatically
- **Configurable Parameters** — Starting capital, fees, slippage, test period (1W to 5Y)
- **Performance Metrics** — Total return, Sharpe/Sortino ratio, max drawdown, win rate, profit factor, trade log
- **Risk Management** — Built-in stop-loss and take-profit parameters

## Tech Stack

- **Frontend:** Single HTML file (`ui/index.html`) — vanilla JS, dark theme, Canvas charts
- **Backend:** Python 3.12 HTTP server (`web_server.py`)
- **AI:** Claude Vision (screenshot analysis), Claude Haiku (NL strategy translation)
- **Data:** 108 coins × 5 years of daily OHLCV candles (Binance via CCXT, cached as Parquet)
- **Hosting:** Netlify (frontend) + Render (backend)

## Project Structure

```
ui/index.html       — Frontend (single HTML file)
web_server.py       — Python backend server (port 8877)
strategies/         — Strategy parser and definitions (incl. CRT+CISD)
vision/             — Claude Vision screenshot analyzer
engine/             — Backtesting engine core (candle-by-candle, no look-ahead bias)
indicators/         — Technical indicator calculations
metrics/            — Performance metric calculations
data/cache/         — Cached OHLCV data (Parquet files)
render.yaml         — Render deployment config
```

## Local Setup

```bash
pip install -r requirements.txt
python web_server.py
# Open http://localhost:8877
```

Set `ANTHROPIC_API_KEY` in `.env` for AI features (screenshot analysis, NL translation).

## Deployment

- **Frontend** auto-deploys to Netlify via `jumparo1/JumpTools` repo
- **Backend** auto-deploys to Render from this repo (main branch)
