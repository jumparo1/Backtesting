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
- [x] 114 coins fetched and cached
- [x] Claude Vision screenshot analysis
- [x] Deploy frontend to Netlify
- [ ] Backend not hosted yet (runs locally only)
- [ ] No automated tests

## Recent Changes
- 2026-02-27: Pushed all source + data to GitHub, added SKILL.md

## Next Steps
- Teach Claude trading strategies via SKILL.md
- Host backend (was exploring Render, paused)
- Add more strategies and indicators

## How to Run
```bash
cd JumpTools/Backtesting
pip install -r requirements.txt
python web_server.py
# Open http://localhost:8877
```
