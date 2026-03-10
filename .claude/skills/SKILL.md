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
4. **Entry:** Sell at CISD level on C3
5. **Stop Loss:** Just above C2 high (a few ticks past the sweep extreme)
6. **Take Profit:** 2.5x risk (2.5R) below entry, or target C1 low / next liquidity level

#### LONG Setup (Bullish CRT + Bullish CISD)

1. C2 wick sweeps below C1 low (sell-side liquidity grabbed)
2. C2 body inside C1 body, C2 closes **green** (close > open)
3. CISD level = C1 low (or opening price of bearish delivery)
4. **Entry:** Buy at CISD level on C3
5. **Stop Loss:** Just below C2 low
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

Current implementation uses **daily candles only** (long-only, no shorting in engine):
- **ENTER LONG:** Bullish CRT detected (C2 sweeps C1 low, closes green, body inside C1)
- **EXIT:** Bearish CRT detected (C2 sweeps C1 high, closes red)
- **SL:** C2 low | **TP:** 2.5R above entry
- Multi-timeframe and killzone timing not yet implemented

#### Example (HYPE SHORT, Feb 27 2026)
- 1D: C1=Feb 25, C2=Feb 26 (range 25.62-29.41), C3=Feb 27
- 1H CISD: 28.42 (C1 high)
- Entry: 28.42 | SL: 28.45 | TP: 28.35 (2.5R)

---

### Spike Exhaustion Reversal (RSI + StochRSI + ZC Momentum + Volume)

**Source:** Journal-backed — enhanced with 4-layer scored confirmation from trading journal patterns.

#### Concept

Detects unsustainable price spikes (parabolic moves) and trades the mean-reversion back toward equilibrium. Uses a **scored confirmation system** — spike + rejection candle is always required, then at least 2 of 4 confirmation layers must align.

#### Parameters (in `strategies/spike_reversal.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `spike_pct` | 0.03 (3%) | Minimum % move to qualify as a spike |
| `lookback` | 5 | Number of candles to measure the spike over |
| `wick_ratio` | 1.5 | Min wick-to-body ratio for strong rejection |
| `rsi_os` | 40 | RSI oversold threshold for entry |
| `rsi_ob` | 65 | RSI overbought threshold for exit |
| `srsi_os` | 30 | StochRSI %K oversold threshold |
| `srsi_ob` | 75 | StochRSI %K overbought threshold |
| `mom_period` | 10 | Momentum/ROC period for ZC filter |
| `vol_mult` | 1.5 | Volume must exceed this × 20-period avg |
| `min_confirms` | 2 | Minimum confirmation layers needed (of 4) |
| `rr_target` | 2.0 | Reward:risk ratio for take-profit |

#### LONG Setup (After Spike DOWN)

**Required (always):**
1. Price drops ≥ `spike_pct` within `lookback` candles
2. Candle shows rejection: hammer wick (lower wick > 1.5× body) OR green close

**Confirmation layers (need 2 of 4):**
1. **RSI(14) < 40** — oversold
2. **StochRSI %K < 30 + %K > %D** — bullish crossover in oversold zone
3. **Momentum(ROC) recovering** — current ROC > previous ROC (selling pressure easing)
4. **Volume > 1.5× 20-period average** — capitulation volume

**SL:** Spike low (candle low) | **TP:** 2R above entry

#### EXIT (Spike UP with position)

**Required:** Price gains ≥ `spike_pct` within `lookback` candles

**Confirmation layers (need 2 of 4):**
1. Rejection wick (upper wick > 1.5× body)
2. RSI(14) > 65 (overbought)
3. StochRSI %K > 75
4. Momentum decelerating (current ROC < previous ROC)

#### Indicator Definitions

- **StochRSI:** Stochastic oscillator applied to RSI values. %K = SMA(3) of raw StochRSI, %D = SMA(3) of %K. Range 0–100. Bullish when %K crosses above %D in oversold zone.
- **Momentum/ROC:** Rate of Change = ((close - close[N ago]) / close[N ago]) × 100. Positive = bullish, negative = bearish. Zero-crossing signals trend shift.

#### Calibration Notes (BTC daily)
- 3% threshold → ~99 spike events/year, ~7 trades/year after filtering
- Scored 2-of-4 system is critical — requiring ALL conditions (AND gate) produces 0 trades
- Thresholds intentionally relaxed from textbook values (RSI 40 vs 30, SRSI 30 vs 20) to allow realistic signal frequency

---

### MR Long (Journal Edge)

**Source:** Reverse-engineered from trading journal — 100% WR on 8 trades.

#### Concept

Mean reversion long — buy support bounces at EMA pullback, sell at mean/resistance. Journal keyword signals: retest, ema, reversion, bounce, rejection, support.

#### ENTRY (ALL conditions required)
1. Price low dips to/below EMA(21), close bounces above
2. RSI(14) < 40 (stretched but not extreme)
3. Hammer candle (lower wick > 1.5× body)
4. Candle closes green (bullish rejection)
5. Lower Bollinger Band touch (within 1% tolerance)

**SL:** Candle low | **TP:** 2R above entry

#### EXIT
- RSI(14) > 65 (approaching overbought)
- OR price hits upper Bollinger Band
- OR take-profit / stop-loss hit

---

## Your Trading Knowledge
<!-- Paste additional trading skills, setups, and strategies below this line -->
<!-- Claude will use this context when helping with backtesting -->


