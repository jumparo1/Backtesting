# Backtesting Tool

## About
Crypto strategy backtesting engine. Describe strategies in plain English, test across 108 altcoins with 5 years of daily data. Supports LONG and SHORT trades. Outputs win rate, P&L, Sharpe, drawdown and full trade log.

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
5. Supports LONG (buy/sell) and SHORT (short/cover) positions
6. Metrics calculated, equity curve + trade log returned

## Project Structure
```
config/       → settings, coin list
data/         → fetcher, Parquet storage, preprocessor
strategies/   → base class, rule system, NL parser, CRT+CISD
engine/       → backtest loop, portfolio (long+short), orders
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

## Engine Architecture
- **Order types:** BUY (open long), SELL (close long), SHORT (open short), COVER (close short)
- **Long SL/TP:** SL below entry, TP above entry
- **Short SL/TP:** SL above entry (price goes up = loss), TP below entry (price goes down = profit)
- **Short PnL:** (entry_price - exit_price) × quantity - fees
- **Margin model:** Short margin = quantity × entry_price (reserved from cash)

---

## Strategies

### CRT + CISD (Candle Range Theory + Change in State of Delivery)

**Source:** ICT (Inner Circle Trader) concepts. Derived from ICT Liquidity Sweep, ICT Power of 3, and ICT Session High/Low Liquidity.

#### CRT — Candle Range Theory (The Pattern)

CRT is a **3-candle AMD (Accumulation → Manipulation → Distribution)** pattern, also called ICT Power of 3:

| Candle | Phase | Role |
|--------|-------|------|
| **C1** | Accumulation | Forms the range. Mark its High and Low — these are liquidity pools. |
| **C2** | Manipulation | Sweeps beyond C1's extreme (liquidity grab / stop hunt). Body stays inside C1's body. The wick extends past C1's high or low. |
| **C3** | Distribution | The real move — expands in the opposite direction of the sweep. |

**Key rule:** C2's **body** (open-close) must be inside C1's body. Only the **wick** extends beyond C1's extreme. This is what makes it a manipulation candle — it looks like a breakout but closes back inside.

**Bullish CRT:**
1. C2 wick sweeps below C1 low (grabs sell-side liquidity)
2. C2 body stays within C1 body range
3. C2 closes as a **green candle** (close > open = rejection of downside)
4. C3 expands upward (distribution to the upside)

**Bearish CRT:**
1. C2 wick sweeps above C1 high (grabs buy-side liquidity)
2. C2 body stays within C1 body range
3. C2 closes as a **red candle** (close < open = rejection of upside)
4. C3 expands downward (distribution to the downside)

**"Both sides swept"** = C2 swept BOTH C1 high AND C1 low (long wick candle / doji). This is a stronger signal because maximum liquidity was grabbed.

#### CISD — Change in State of Delivery (The Entry)

CISD identifies the exact level where price delivery shifts direction. **Ignore wicks — only look at open and close prices.**

- **Bullish CISD:** Price closes ABOVE the opening price of prior bearish delivery. The bearish candles become a bullish order block (support).
- **Bearish CISD:** Price closes BELOW the opening price of prior bullish delivery. The bullish candles become a bearish order block (resistance).

CISD is a short-term reversal signal that precedes and confirms Market Structure Shift (MSS).

#### Combined CRT + CISD Trade Process

**Step 1 — Mark key levels** (prior highs/lows, order blocks, FVGs)
**Step 2 — Identify CRT** at a key level (C2 sweeps liquidity at that level)
**Step 3 — Wait for CISD/MSS on lower timeframe** for precise entry

#### SHORT Setup (Bearish CRT + Bearish CISD)

1. C2 wick sweeps above C1 high (buy-side liquidity grabbed)
2. C2 body inside C1 body, C2 closes **red** (close < open)
3. CISD level = C1 high (or opening price of bullish delivery)
4. **Entry:** Sell short at C3 open
5. **Stop Loss:** C2 high (the sweep extreme)
6. **Take Profit:** 2.5x risk (2.5R) below entry, or target C1 low / next liquidity level

#### LONG Setup (Bullish CRT + Bullish CISD)

1. C2 wick sweeps below C1 low (sell-side liquidity grabbed)
2. C2 body inside C1 body, C2 closes **green** (close > open)
3. CISD level = C1 low (or opening price of bearish delivery)
4. **Entry:** Buy at C3 open
5. **Stop Loss:** C2 low
6. **Take Profit:** 2.5x risk (2.5R) above entry, or target C1 high / next liquidity level

#### Multi-Timeframe Alignment

| Timeframe | Purpose |
|-----------|---------|
| **1D CRT** | Determines macro bias (direction for the day) |
| **1H CRT + CISD** | Confirms alignment with 1D, identifies the entry zone |
| **5M / 15M** | Precision entry at CISD level with tight stop |

Best performance when CRT aligns with daily bias and occurs during major sessions (London / New York killzones).

#### Killzone Timing (Forex/Crypto)
- **Asian session** = Accumulation (range forms)
- **London session (3:00-6:00 NY time)** = Manipulation (CRT sweeps)
- **New York session (8:30-11:30 NY time)** = Distribution (main move, highest volume)

#### Risk Management
- Risk per trade: 0.10% of capital
- RR target: 2.5R minimum
- SL always at C2 extreme (natural invalidation)
- TP at C1 opposite extreme or next liquidity level

#### Backtesting Implementation (`strategies/crt_cisd.py`)

Current implementation uses **daily candles**, supports **both LONG and SHORT**:
- **ENTER LONG:** Bullish CRT detected (C2 sweeps C1 low, closes green, body inside C1)
- **ENTER SHORT:** Bearish CRT detected (C2 sweeps C1 high, closes red, body inside C1)
- **Long SL:** C2 low | **Long TP:** 2.5R above entry
- **Short SL:** C2 high | **Short TP:** 2.5R below entry
- Opposite signal closes current position and opens new one
- Multi-timeframe and killzone timing not yet implemented

#### Backtest Results (Feb 2026 — 108 coins, 5yr daily, $10k capital, 0.1% fee+slippage)

| Metric | Value |
|--------|-------|
| **Total trades** | 13,110 |
| **LONG trades** | 6,560 (WR: 30.4%) |
| **SHORT trades** | 6,550 (WR: 34.6%) |
| **Overall win rate** | 32.5% |
| **Profit factor** | 0.89 |
| **Avg win** | $660.94 |
| **Avg loss** | $357.52 |
| **Win/Loss ratio** | 1.85:1 |
| **Profitable coins** | 14/108 (13%) |

**Top performers:** FTM (+402.6%), ASTER (+135.8%), ENA (+87.5%), AAVE (+63.0%), APT (+61.8%)

**Analysis:** The 2.5R target produces a favorable win/loss ratio (1.85:1), but the 32.5% win rate isn't enough to overcome fees/slippage. Shorts outperform longs (34.6% vs 30.4% WR). Strategy works best on volatile coins with clear liquidity patterns.

**Optimization paths:**
- Relax body-inside-body rule → more trades, potentially higher WR
- Add volume confirmation → fewer trades, better quality
- Multi-timeframe alignment → enter only with daily bias
- Adjust RR target (try 2.0R or 3.0R)

---

## Your Trading Knowledge
<!-- Paste additional trading skills, setups, and strategies below this line -->
<!-- Claude will use this context when helping with backtesting -->


