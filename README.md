# Backtesting Tool

Strategy backtesting engine for testing and validating trading setups using natural language.

## Features

- **Natural Language Input** — Describe strategies in plain English (e.g., "buy when RSI below 30, sell when overbought")
- **Multi-Coin Testing** — Test across multiple cryptocurrencies simultaneously with comparison table
- **Screenshot Analysis** — Upload TradingView chart screenshots, Claude Vision extracts the trading strategy automatically
- **Pre-built Examples** — 7+ common strategies (RSI oversold, golden cross, MACD crossover, Bollinger bands, etc.)
- **Configurable Parameters** — Starting capital, fees, slippage, test period (1W to 5Y)
- **Performance Metrics** — Total return, Sharpe/Sortino ratio, max drawdown, win rate, profit factor, trade log
- **Risk Management** — Built-in stop-loss and take-profit parameters

## Tech Stack

- **Frontend**: Single HTML file (`ui/index.html`) with dark theme, Canvas charts
- **Backend**: Python HTTP server (`web_server.py`)
- **AI**: Claude Vision for screenshot analysis, Claude Haiku for natural language translation
- **Data**: CoinGecko historical OHLCV data with local JSON caching

## Project Structure

```
ui/index.html       — Frontend (single HTML file)
web_server.py       — Python backend server
strategies/         — Strategy parser and definitions
vision/             — Claude Vision screenshot analyzer
engine/             — Backtesting engine core
indicators/         — Technical indicator calculations
metrics/            — Performance metric calculations
data/               — Cached historical price data
config/             — Configuration files
```

## Setup

```bash
pip install -r requirements.txt
python web_server.py
```

Then open `http://localhost:8080` in your browser.

## Live

Frontend hosted on Netlify: `jumptrading.netlify.app/backtesting.html`

(Note: Screenshot analysis and AI translation require the Python backend running locally)
