# Backtesting Tool

Crypto strategy backtesting engine — describe strategies in plain English, test across 114 altcoins.

## Stack
- **Backend:** Python 3.12 (`web_server.py` port 8877)
- **Frontend:** `ui/index.html` (single file, dark theme)
- **Data:** 114 coins × 5 years daily candles in `data/cache/` (Parquet)
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
- [x] CRT + CISD implemented in engine (`strategies/crt_cisd.py`) — body-inside-body, candle color, min sweep depth
- [ ] Backend not hosted yet (runs locally only)
- [ ] 12 top-100 coins stale (CRO, KAS, LEO, OKB, KCS, MKR, MNT, FTM, HNT, EOS, XMR, OCEAN — not on Binance)
- [ ] No automated tests

## Recent Changes
- 2026-02-27: Refreshed all coin data to today (87/108 fully current)
- 2026-02-27: Added fallback coin list for Netlify (coins show without backend)
- 2026-02-27: Added strategy dropdown with CRT + CISD as first template
- 2026-02-27: Documented CRT + CISD theory in SKILL.md
- 2026-02-27: Pushed all source + data to GitHub, added SKILL.md

## Next Steps
- Fix stale coin data (need alternative sources for non-Binance coins)
- Host backend (Render prepared but paused)
- Add more strategies to dropdown
- Add short-selling support to engine (bearish CRT currently only exits longs)

## How to Run
```bash
cd JumpTools/Backtesting
pip install -r requirements.txt
python web_server.py
# Open http://localhost:8877
```
