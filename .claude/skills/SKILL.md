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

## Strategies

### CRT + CISD (Candle Range Theory + Change in State of Delivery)

**Concept:** A 3-candle price action pattern that identifies liquidity grabs and structural shifts for high-RR entries.

**CRT (Candle Range Theory) — The Pattern:**
- **C1 (Setup):** Establishes a range — its high and low become liquidity pools
- **C2 (Manipulation/Sweep):** Sweeps beyond C1's extreme to grab liquidity (stop hunts)
- **C3 (Expansion):** Moves in the opposite direction of the sweep — the real move

**CISD (Change in State of Delivery) — The Entry:**
- The exact price level where delivery shifts from one direction to the other
- For SHORT: CISD = C1's high. C2 sweeps above it, price returns below → enter short at this level
- For LONG: CISD = C1's low. C2 sweeps below it, price returns above → enter long at this level

**SHORT Setup:**
1. C2 makes a higher high than C1 (sweeps buy-side liquidity)
2. C2 closes back inside C1's range or below C1's high
3. CISD level = C1 high
4. Entry: Sell at CISD (C1 high) on C3
5. Stop Loss: Just above C2 high (tight, a few ticks)
6. Take Profit: 2.5x risk (2.5R) below entry

**LONG Setup:**
1. C2 makes a lower low than C1 (sweeps sell-side liquidity)
2. C2 closes back inside C1's range or above C1's low
3. CISD level = C1 low
4. Entry: Buy at CISD (C1 low) on C3
5. Stop Loss: Just below C2 low
6. Take Profit: 2.5x risk (2.5R) above entry

**Multi-Timeframe Alignment:**
- **1D CRT** → Determines macro bias (SHORT or LONG for the day)
- **1H CRT + CISD** → Confirms direction aligns with 1D, identifies entry zone
- **5M** → Precision entry at CISD level with tight stop

**Key Filters:**
- "Both sides swept" = stronger signal (C2 swept both C1 high AND low)
- 1H direction must align with 1D direction
- Best setups: C2 has long wick beyond C1 extreme but closes inside range

**Risk Management:**
- Risk per trade: 0.10% of capital
- RR target: 2.5R minimum
- SL always at C2 extreme (natural invalidation point)

**Example (HYPE SHORT, Feb 27 2026):**
- 1D: C1=Feb 25, C2=Feb 26 (range 25.62-29.41), C3=Feb 27
- 1H CISD: 28.42 (C1 high)
- Entry: 28.42 | SL: 28.45 | TP: 28.35 (2.5R)

---

## Your Trading Knowledge
<!-- Paste additional trading skills, setups, and strategies below this line -->
<!-- Claude will use this context when helping with backtesting -->


