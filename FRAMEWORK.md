# Crypto Altcoin Backtesting Tool

## Goal
Write trading strategies in Python and backtest them against historical data from the top 100 altcoins by market cap over the last 5 years. Output: win rate, P&L, and key performance metrics.

---

## Architecture Overview

```
backtesting/
├── config/
│   ├── settings.py              # Global config (timeframes, date ranges, API keys)
│   └── coins.py                 # Top 100 altcoin list management
│
├── data/
│   ├── fetcher.py               # Download OHLCV + volume data from exchange APIs
│   ├── storage.py               # Save/load data locally (Parquet files)
│   ├── cache/                   # Local data cache (Parquet files per coin)
│   └── preprocessor.py          # Clean data, handle gaps, normalize
│
├── indicators/
│   ├── base.py                  # Base indicator class
│   ├── moving_averages.py       # SMA, EMA, WMA, VWAP
│   ├── momentum.py              # RSI, MACD, Stochastic, CCI
│   ├── volatility.py            # Bollinger Bands, ATR, Keltner Channels
│   ├── volume.py                # OBV, Volume Profile, MFI
│   └── custom.py                # User-defined indicators
│
├── strategies/
│   ├── base.py                  # Abstract base strategy class
│   ├── example_sma_cross.py     # Example: SMA crossover strategy
│   └── my_strategies/           # User writes strategies here
│       └── __init__.py
│
├── engine/
│   ├── backtester.py            # Core backtesting loop
│   ├── portfolio.py             # Track positions, balance, exposure
│   ├── order.py                 # Order types (market, limit, stop-loss, take-profit)
│   └── risk.py                  # Position sizing, max drawdown limits
│
├── metrics/
│   ├── performance.py           # Win rate, profit factor, Sharpe, Sortino, max DD
│   └── reporting.py             # Generate summary tables and charts
│
├── output/
│   └── (generated reports go here)
│
├── tests/
│   ├── test_fetcher.py
│   ├── test_engine.py
│   └── test_strategies.py
│
├── main.py                      # CLI entry point
├── requirements.txt
└── README.md
```

---

## Data Layer

### Source
- **Primary:** CoinGecko API (free, has top 100 by mcap + OHLCV)
- **Fallback:** Binance API (better granularity for listed pairs, OHLCV via /klines)
- **Timeframes:** 1d (default), 4h, 1h as optional
- **Date range:** 5 years back from today (~Feb 2021 - Feb 2026)

### Storage
- Parquet files per coin per timeframe: `data/cache/BTC_1d.parquet`
- Schema: `timestamp | open | high | low | close | volume | market_cap`
- One-time fetch, then incremental updates only

### Coin List Management
- Fetch current top 100 by market cap from CoinGecko
- Track historical rank changes (a coin in top 100 today may not have been 5y ago)
- Option: use "top 100 at each point in time" vs "current top 100 applied historically"
- Exclude stablecoins (USDT, USDC, DAI, etc.) by default

---

## Strategy Interface

```python
from strategies.base import Strategy

class MySMAStrategy(Strategy):
    """User writes strategies by subclassing Strategy."""

    def __init__(self):
        super().__init__(
            name="SMA Crossover",
            description="Buy when fast SMA crosses above slow SMA",
        )

    def setup(self, params):
        """Define parameters and indicators needed."""
        self.fast_period = params.get("fast_period", 20)
        self.slow_period = params.get("slow_period", 50)

    def on_candle(self, candle, indicators, portfolio):
        """Called for each new candle. This is where the logic lives.

        Args:
            candle: OHLCV data for current bar
            indicators: Pre-computed indicator values
            portfolio: Current portfolio state (balance, positions)

        Returns:
            Signal: BUY, SELL, or HOLD
        """
        fast_sma = indicators.sma(self.fast_period)
        slow_sma = indicators.sma(self.slow_period)

        if fast_sma > slow_sma and not portfolio.has_position(candle.symbol):
            return self.buy(
                symbol=candle.symbol,
                size_pct=0.02,         # 2% of portfolio per trade
                stop_loss_pct=0.05,    # 5% stop loss
                take_profit_pct=0.10,  # 10% take profit
            )

        if fast_sma < slow_sma and portfolio.has_position(candle.symbol):
            return self.sell(symbol=candle.symbol)

        return self.hold()
```

---

## Backtesting Engine

### Execution Model
1. Load data for selected coins and timeframe
2. Initialize portfolio with starting balance (default $10,000)
3. Iterate candle-by-candle chronologically across all coins
4. For each candle: compute indicators -> call `on_candle()` -> execute orders
5. Apply slippage (configurable, default 0.1%) and trading fees (default 0.1%)
6. Track all trades in a trade log

### Order Handling
- **Market orders** fill at next candle's open
- **Stop-loss / take-profit** checked against each candle's high/low
- No look-ahead bias: strategy only sees past and current data

### Configuration
- Starting capital
- Fee structure (maker/taker)
- Slippage model
- Max concurrent positions
- Max allocation per coin
- Rebalance frequency (optional)

---

## Metrics & Output

### Core Metrics
| Metric              | Description                                    |
|---------------------|------------------------------------------------|
| Win Rate            | % of trades closed in profit                   |
| Total Return        | Portfolio % change over backtest period         |
| Max Drawdown        | Largest peak-to-trough decline                  |
| Sharpe Ratio        | Risk-adjusted return (annualized)               |
| Sortino Ratio       | Downside risk-adjusted return                   |
| Profit Factor       | Gross profit / gross loss                       |
| Avg Win / Avg Loss  | Average size of winning vs losing trades        |
| Trade Count         | Total trades executed                           |
| Avg Trade Duration  | Mean holding period                             |
| Exposure %          | % of time capital is deployed                   |

### Output Formats
- **Console:** Summary table printed after each run
- **CSV/JSON:** Detailed trade log export
- **Charts (optional, Phase 2):** Equity curve, drawdown chart, per-coin breakdown

---

## Roadmap

### Phase 1 — Foundation
- [ ] Set up project structure and dependencies
- [ ] Build data fetcher (CoinGecko + Binance fallback)
- [ ] Implement local Parquet storage and caching
- [ ] Fetch and store top 100 altcoin list
- [ ] Download 5y daily OHLCV for all 100 coins

### Phase 2 — Engine Core
- [ ] Define base Strategy class with `on_candle()` interface
- [ ] Build indicator library (SMA, EMA, RSI, MACD, Bollinger, ATR)
- [ ] Implement backtesting loop (candle-by-candle, no look-ahead)
- [ ] Add portfolio tracker (positions, balance, P&L)
- [ ] Add order execution with slippage and fees

### Phase 3 — Metrics & Output
- [ ] Calculate all core metrics (win rate, Sharpe, drawdown, etc.)
- [ ] Console reporting with summary tables
- [ ] Trade log export (CSV)
- [ ] Build example SMA crossover strategy as validation

### Phase 4 — Robustness
- [ ] Multi-coin parallel backtest (run strategy across all 100 coins)
- [ ] Parameter sweep / optimization (grid search over strategy params)
- [ ] Walk-forward analysis (train on window, test on next)
- [ ] Add unit tests for engine, indicators, and order execution

### Phase 5 — Enhancements (Optional)
- [ ] Matplotlib/Plotly equity curve and drawdown charts
- [ ] Intraday timeframes (4h, 1h) support
- [ ] Benchmark comparison (vs BTC buy-and-hold, vs market index)
- [ ] Strategy comparison mode (run multiple strategies side by side)
- [ ] CLI with argparse for running backtests from terminal

---

## Tech Stack

| Component       | Choice                          |
|-----------------|---------------------------------|
| Language        | Python 3.11+                    |
| Data handling   | pandas, pyarrow (Parquet)       |
| API clients     | requests, ccxt (exchange APIs)  |
| Indicators      | pandas-ta or custom             |
| Testing         | pytest                          |
| Charts (opt.)   | matplotlib, plotly              |
| CLI             | argparse                        |

---

## Key Design Decisions

1. **Candle-by-candle loop** — Not vectorized. Slower but accurate and prevents look-ahead bias. Strategy logic stays simple and readable.

2. **Strategy-as-a-class** — Users subclass `Strategy` and implement `on_candle()`. Clean separation between engine and strategy logic.

3. **Parquet for storage** — Fast reads, columnar compression, works natively with pandas. No database dependency.

4. **Fees and slippage by default** — Realistic results out of the box. No "perfect fill" fantasy backtests.

5. **Top 100 filtering** — Excludes stablecoins. Option to use current top 100 or historical top 100 at each time point (survivorship bias consideration).
