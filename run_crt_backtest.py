#!/usr/bin/env python3
"""
Run CRT+CISD backtest across ALL cached coins and report aggregate results.
Target: 1000+ trades to validate winrate.
"""

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.storage import load_ohlcv, list_cached_symbols
from engine.backtester import run_backtest, BacktestConfig
from strategies.crt_cisd import CRTCISDStrategy


def main():
    symbols = sorted(list_cached_symbols("1d"))
    print(f"Found {len(symbols)} cached coins\n")

    config = BacktestConfig(
        starting_capital=10_000.0,
        fee_pct=0.001,       # 0.1%
        slippage_pct=0.001,  # 0.1%
    )

    all_trades = []
    coin_results = []

    for sym in symbols:
        df = load_ohlcv(sym, "1d")
        if df is None or df.empty:
            continue

        strategy = CRTCISDStrategy()
        result = run_backtest(strategy, df, symbol=sym, config=config)
        metrics = result.summary()

        n_trades = metrics.get("total_trades", 0)
        longs = sum(1 for t in result.trades if t.side == "LONG")
        shorts = sum(1 for t in result.trades if t.side == "SHORT")
        win_rate = metrics.get("win_rate", 0)
        total_ret = metrics.get("total_return", 0)

        coin_results.append({
            "symbol": sym,
            "trades": n_trades,
            "longs": longs,
            "shorts": shorts,
            "win_rate": win_rate,
            "total_return": total_ret,
            "final_equity": metrics.get("final_equity", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "profit_factor": metrics.get("profit_factor", 0),
            "sharpe": metrics.get("sharpe_ratio", 0),
        })
        all_trades.extend(result.trades)

        if n_trades > 0:
            print(f"  {sym:>8}  trades={n_trades:>3} (L:{longs} S:{shorts})  "
                  f"WR={win_rate:.1%}  ret={total_ret:>+8.1%}  "
                  f"DD={metrics.get('max_drawdown', 0):.1%}")

    # --- Aggregate stats ---
    total_trades = len(all_trades)
    wins = sum(1 for t in all_trades if t.pnl > 0)
    losses = sum(1 for t in all_trades if t.pnl <= 0)
    total_longs = sum(1 for t in all_trades if t.side == "LONG")
    total_shorts = sum(1 for t in all_trades if t.side == "SHORT")
    long_wins = sum(1 for t in all_trades if t.side == "LONG" and t.pnl > 0)
    short_wins = sum(1 for t in all_trades if t.side == "SHORT" and t.pnl > 0)

    gross_profit = sum(t.pnl for t in all_trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in all_trades if t.pnl <= 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    avg_win = gross_profit / wins if wins > 0 else 0
    avg_loss = gross_loss / losses if losses > 0 else 0

    print("\n" + "=" * 70)
    print("AGGREGATE CRT + CISD RESULTS")
    print("=" * 70)
    print(f"  Coins tested:     {len(coin_results)}")
    print(f"  Total trades:     {total_trades}")
    print(f"  LONG trades:      {total_longs} (wins: {long_wins}, WR: {long_wins/total_longs:.1%})" if total_longs > 0 else "  LONG trades:      0")
    print(f"  SHORT trades:     {total_shorts} (wins: {short_wins}, WR: {short_wins/total_shorts:.1%})" if total_shorts > 0 else "  SHORT trades:     0")
    print(f"  Overall win rate: {wins/total_trades:.1%}" if total_trades > 0 else "  Overall win rate: N/A")
    print(f"  Wins / Losses:    {wins} / {losses}")
    print(f"  Gross profit:     ${gross_profit:,.2f}")
    print(f"  Gross loss:       ${gross_loss:,.2f}")
    print(f"  Profit factor:    {profit_factor:.2f}")
    print(f"  Avg win:          ${avg_win:,.2f}")
    print(f"  Avg loss:         ${avg_loss:,.2f}")

    # Top 10 coins by trade count
    coin_results.sort(key=lambda x: x["trades"], reverse=True)
    print(f"\nTop 10 coins by trade count:")
    print(f"  {'Coin':>8}  {'Trades':>6}  {'L':>3}  {'S':>3}  {'WR':>6}  {'Return':>9}  {'DD':>6}")
    for cr in coin_results[:10]:
        print(f"  {cr['symbol']:>8}  {cr['trades']:>6}  {cr['longs']:>3}  {cr['shorts']:>3}  "
              f"{cr['win_rate']:>5.1%}  {cr['total_return']:>+8.1%}  {cr['max_drawdown']:>5.1%}")

    # Profitable coins
    profitable = [cr for cr in coin_results if cr["total_return"] > 0]
    print(f"\n  Profitable coins: {len(profitable)} / {len(coin_results)} ({len(profitable)/len(coin_results):.0%})")

    return total_trades, wins / total_trades if total_trades > 0 else 0


if __name__ == "__main__":
    trades, wr = main()
    print(f"\nFINAL: {trades} trades, {wr:.1%} win rate")
