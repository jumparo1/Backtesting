#!/usr/bin/env python3
"""
Interactive backtesting CLI — text your trade idea, pick a coin, see results.

Usage:
    python main.py                    # Interactive mode
    python main.py --idea "..."       # One-shot with a trade idea
    python main.py --idea "..." --coin BTC
    python main.py --list-coins       # Show available coins
"""

import argparse
import sys
import copy

from config.coins import get_coin_list
from data.storage import load_ohlcv, has_cached_data, list_cached_symbols
from engine.backtester import run_backtest, BacktestConfig
from engine.runner import run_multi, run_sweep, print_sweep_results
from metrics.reporting import (
    print_summary,
    print_trade_log,
    print_comparison_table,
    export_trades_csv,
    export_equity_csv,
    export_summary_json,
)
from strategies.parser import parse_trade_idea, _EXAMPLE_IDEAS
from strategies.rule_based import RuleBasedStrategy


# ======================================================================
# Interactive mode
# ======================================================================

def interactive_mode() -> None:
    """Full interactive loop: type idea → pick coin → see results → repeat."""
    _print_banner()

    while True:
        # --- Get trade idea ---
        print("━" * 64)
        idea = _prompt(
            "📝 Describe your trade idea (or 'examples' / 'quit'):\n> "
        )

        if idea.lower() in ("quit", "exit", "q"):
            print("\nGoodbye! Happy trading. 🚀\n")
            break

        if idea.lower() in ("examples", "help", "ex"):
            _show_examples()
            continue

        if idea.lower() in ("coins", "list"):
            _show_cached_coins()
            continue

        # --- Parse the idea ---
        result = parse_trade_idea(idea)

        if not result.success:
            print(f"\n❌ {result.message}\n")
            continue

        strategy = result.strategy
        for w in result.warnings:
            print(f"  ⚠ {w}")

        print(f"\n✅ Parsed strategy:")
        print(strategy.describe_rules())
        print()

        # --- Pick coin(s) ---
        coin_input = _prompt(
            "🪙 Which coin(s)? (e.g. BTC, ETH, or 'all' for all cached):\n> "
        )

        symbols = _resolve_symbols(coin_input)
        if not symbols:
            print("  No valid coins found. Make sure data is cached (run fetch_data.py).\n")
            continue

        # --- Run backtest ---
        config = BacktestConfig()

        if len(symbols) == 1:
            _run_single(strategy, symbols[0], config)
        else:
            _run_multi(strategy, symbols, config)

        # --- Export prompt ---
        export = _prompt("\n💾 Export results? (y/n): ").lower()
        if export in ("y", "yes"):
            for sym in symbols:
                data = load_ohlcv(sym, "1d")
                if data is None:
                    continue
                s = _fresh_strategy(strategy)
                r = run_backtest(s, data, symbol=sym, config=config)
                m = r.summary()
                csv_path = export_trades_csv(r.trades, symbol=sym, strategy_name=strategy.name)
                eq_path = export_equity_csv(r.equity_curve, symbol=sym, strategy_name=strategy.name)
                json_path = export_summary_json(m, symbol=sym, strategy_name=strategy.name)
                print(f"  {sym}: {csv_path.name}, {eq_path.name}, {json_path.name}")
            print(f"  Saved to output/ directory.\n")

        print()


# ======================================================================
# One-shot mode
# ======================================================================

def oneshot_mode(idea: str, coin: str | None, all_coins: bool, export: bool) -> int:
    """Parse idea, run backtest, print results."""
    result = parse_trade_idea(idea)

    if not result.success:
        print(f"❌ {result.message}")
        return 1

    strategy = result.strategy
    for w in result.warnings:
        print(f"  ⚠ {w}")

    print(strategy.describe_rules())
    print()

    config = BacktestConfig()

    if all_coins:
        symbols = list_cached_symbols("1d")
    elif coin:
        symbols = _resolve_symbols(coin)
    else:
        symbols = ["BTC"]

    if not symbols:
        print("No cached data found. Run fetch_data.py first.")
        return 1

    if len(symbols) == 1:
        _run_single(strategy, symbols[0], config)
    else:
        _run_multi(strategy, symbols, config)

    if export:
        for sym in symbols:
            data = load_ohlcv(sym, "1d")
            if data is None:
                continue
            s = _fresh_strategy(strategy)
            r = run_backtest(s, data, symbol=sym, config=config)
            m = r.summary()
            export_trades_csv(r.trades, symbol=sym, strategy_name=strategy.name)
            export_equity_csv(r.equity_curve, symbol=sym, strategy_name=strategy.name)
            export_summary_json(m, symbol=sym, strategy_name=strategy.name)
        print(f"  Exported to output/ directory.")

    return 0


# ======================================================================
# Helpers
# ======================================================================

def _run_single(strategy: RuleBasedStrategy, symbol: str, config: BacktestConfig) -> None:
    """Run and display a single-coin backtest."""
    data = load_ohlcv(symbol, "1d")
    if data is None or data.empty:
        print(f"  No data for {symbol}.")
        return

    s = _fresh_strategy(strategy)
    result = run_backtest(s, data, symbol=symbol, config=config)
    metrics = result.summary()

    print_summary(metrics, strategy_name=strategy.name, symbol=symbol)
    print("TRADE LOG:")
    print_trade_log(result.trades, max_rows=15)


def _run_multi(strategy: RuleBasedStrategy, symbols: list[str], config: BacktestConfig) -> None:
    """Run and display a multi-coin backtest."""
    all_results = []

    for sym in symbols:
        data = load_ohlcv(sym, "1d")
        if data is None or data.empty:
            continue
        s = _fresh_strategy(strategy)
        r = run_backtest(s, data, symbol=sym, config=config)
        m = r.summary()
        all_results.append((sym, m))

    if not all_results:
        print("  No results.")
        return

    print_comparison_table(all_results, title=f"{strategy.name} — {len(all_results)} COINS")

    # Show best and worst
    sorted_results = sorted(all_results, key=lambda x: x[1].get("total_return", 0), reverse=True)
    best_sym, best_m = sorted_results[0]
    worst_sym, worst_m = sorted_results[-1]
    print(f"  🏆 Best:  {best_sym} ({best_m.get('total_return', 0):+.1%})")
    print(f"  📉 Worst: {worst_sym} ({worst_m.get('total_return', 0):+.1%})")

    # Aggregate stats
    total_trades = sum(m.get("total_trades", 0) for _, m in all_results)
    avg_return = sum(m.get("total_return", 0) for _, m in all_results) / len(all_results)
    profitable = sum(1 for _, m in all_results if m.get("total_return", 0) > 0)
    print(f"  📊 Avg return: {avg_return:+.1%} | Profitable: {profitable}/{len(all_results)} coins | Total trades: {total_trades}")
    print()


def _fresh_strategy(strategy: RuleBasedStrategy) -> RuleBasedStrategy:
    """Create a deep copy of a strategy so internal state is clean."""
    return copy.deepcopy(strategy)


def _resolve_symbols(text: str) -> list[str]:
    """Parse a coin input string into a list of valid cached symbols."""
    text = text.strip()

    if text.lower() in ("all", "*"):
        return sorted(list_cached_symbols("1d"))

    raw = [s.strip().upper() for s in text.replace(",", " ").split()]
    valid = []
    for s in raw:
        if has_cached_data(s, "1d"):
            valid.append(s)
        else:
            print(f"  ⚠ No cached data for {s} — skipping (run fetch_data.py to download).")

    return valid


def _prompt(msg: str) -> str:
    """Read input with a prompt."""
    try:
        return input(msg).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n")
        sys.exit(0)


def _print_banner() -> None:
    print("""
╔══════════════════════════════════════════════════════════════╗
║          🔮  CRYPTO STRATEGY BACKTESTER  🔮                 ║
║                                                              ║
║  Type your trade idea in plain English and backtest it       ║
║  against any of the top 100 altcoins.                        ║
║                                                              ║
║  Examples:                                                   ║
║    "buy when RSI below 30, sell when RSI above 70"           ║
║    "buy on golden cross, sell on death cross"                ║
║    "buy when MACD crosses above signal, sl 5%, tp 10%"       ║
║                                                              ║
║  Commands: 'examples', 'coins', 'quit'                       ║
╚══════════════════════════════════════════════════════════════╝
""")


def _show_examples() -> None:
    print("\n📚 Example trade ideas:\n")
    for i, idea in enumerate(_EXAMPLE_IDEAS, 1):
        print(f"  {i}. \"{idea}\"")
    print()


def _show_cached_coins() -> None:
    symbols = sorted(list_cached_symbols("1d"))
    if not symbols:
        print("  No cached coin data. Run: python fetch_data.py\n")
    else:
        print(f"\n  {len(symbols)} coins cached: {', '.join(symbols)}\n")


# ======================================================================
# Entry point
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Backtest crypto trade ideas against historical altcoin data",
    )
    parser.add_argument(
        "--idea", "-i",
        type=str,
        help='Trade idea in plain English, e.g. "buy when RSI below 30, sell when RSI above 70"',
    )
    parser.add_argument(
        "--coin", "-c",
        type=str,
        help="Coin symbol (e.g. BTC, ETH, SOL) or comma-separated list",
    )
    parser.add_argument(
        "--all-coins", "-a",
        action="store_true",
        help="Run on all cached coins",
    )
    parser.add_argument(
        "--export", "-e",
        action="store_true",
        help="Export trade log CSV, equity CSV, and summary JSON",
    )
    parser.add_argument(
        "--list-coins",
        action="store_true",
        help="Show all cached coins and exit",
    )
    args = parser.parse_args()

    if args.list_coins:
        _show_cached_coins()
        return 0

    if args.idea:
        return oneshot_mode(args.idea, args.coin, args.all_coins, args.export)

    # Default: interactive mode
    interactive_mode()
    return 0


if __name__ == "__main__":
    sys.exit(main())
