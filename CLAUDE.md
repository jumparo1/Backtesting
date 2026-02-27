# Backtesting Tool

Crypto strategy backtesting engine — describe strategies in plain English, test across 108 altcoins.

## Stack
- **Backend:** Python 3.12 (`web_server.py` port 8877)
- **Frontend:** `ui/index.html` (single file, dark theme)
- **Data:** 108 coins × 5 years daily candles in `data/cache/` (Parquet)
- **AI:** Claude Vision (screenshot analysis), Claude Haiku (NL translation)

## Status
- [x] Core engine (candle-by-candle backtest, no look-ahead bias)
- [x] NL parser (natural language → strategy rules)
- [x] Web UI with coin selector, equity chart, trade log
- [x] 108 coins fetched and cached (99 current as of 2026-02-27)
- [x] Claude Vision screenshot analysis
- [x] Deploy frontend to Netlify (via `npx netlify-cli deploy --prod --dir=.` from `/Users/jumparo/deploy/`)
- [x] Fallback coin list + examples in UI (works without backend)
- [x] Strategy dropdown menu (first strategy: CRT + CISD)
- [x] CRT + CISD strategy documented in SKILL.md
- [x] CRT + CISD implemented in engine (`strategies/crt_cisd.py`)
- [x] SHORT selling support in engine (order, portfolio, backtester)
- [x] CRT + CISD bidirectional (LONG + SHORT trades)
- [x] Frontend shows trade side (LONG/SHORT) in trade log
- [x] Metrics include long/short breakdown (win rates per side)
- [x] Backtest validated: 13,110 trades across 108 coins, 32.5% WR
- [ ] Backend not hosted yet (runs locally only)
- [ ] 12 top-100 coins stale (CRO, KAS, LEO, OKB, KCS, MKR, MNT, FTM, HNT, EOS, XMR, OCEAN — not on Binance)
- [ ] No automated tests

## Recent Changes
- 2026-02-27: Added SHORT support to engine (OrderSide.SHORT/COVER, portfolio.apply_short/apply_cover)
- 2026-02-27: Updated CRT+CISD for bidirectional trading (LONG on bullish CRT, SHORT on bearish CRT)
- 2026-02-27: Updated backtester SL/TP handling for short positions (inverted levels)
- 2026-02-27: Added LONG/SHORT side column to frontend trade log
- 2026-02-27: Added long/short breakdown to metrics (long_trades, short_trades, long_win_rate, short_win_rate)
- 2026-02-27: Updated SKILL.md with backtest results (13,110 trades, 32.5% WR, shorts outperform longs)
- 2026-02-27: Refreshed all coin data to today (87/108 fully current)
- 2026-02-27: Added fallback coin list for Netlify (coins show without backend)

## Backtest Results (CRT+CISD, 108 coins, 5yr daily)
- **13,110 trades** (6,560 long, 6,550 short)
- **32.5% overall win rate** (30.4% long, 34.6% short)
- **Profit factor: 0.89** | Avg win: $661 | Avg loss: $358
- **Top coins:** FTM (+402%), ASTER (+136%), ENA (+88%), AAVE (+63%)
- **14/108 coins profitable** (13%)

## Next Steps
- Fix stale coin data (need alternative sources for non-Binance coins)
- Host backend (Render prepared but paused)
- Add more strategies to dropdown
- Optimize CRT+CISD (relax body-inside-body, add volume filter, tune RR)
- Add multi-timeframe alignment

## How to Run
```bash
cd JumpTools/Backtesting
pip install -r requirements.txt
python web_server.py
# Open http://localhost:8877
```
