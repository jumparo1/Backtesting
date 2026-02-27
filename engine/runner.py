"""
Multi-coin runner and parameter sweep utilities.

- run_multi(): run a strategy across multiple coins
- run_sweep(): grid search over strategy parameters
"""

from __future__ import annotations

import copy
import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd

from data.storage import load_ohlcv, list_cached_symbols
from engine.backtester import run_backtest, BacktestConfig, BacktestResult
from strategies.base import Strategy


# ======================================================================
# Multi-coin backtest
# ======================================================================

def run_multi(
    strategy_factory,
    symbols: list[str] | None = None,
    timeframe: str = "1d",
    config: BacktestConfig | None = None,
    params: dict | None = None,
) -> list[BacktestResult]:
    """Run a strategy across multiple coins sequentially.

    Args:
        strategy_factory: Callable that returns a fresh Strategy instance.
                          Needed because strategies have internal state.
        symbols: List of symbols to test. If None, uses all cached symbols.
        timeframe: Data timeframe.
        config: Backtest configuration.
        params: Strategy parameters.

    Returns:
        List of BacktestResult objects.
    """
    if symbols is None:
        symbols = list_cached_symbols(timeframe)

    if not symbols:
        print("No cached data found. Run fetch_data.py first.")
        return []

    config = config or BacktestConfig()
    results: list[BacktestResult] = []

    for sym in symbols:
        data = load_ohlcv(sym, timeframe)
        if data is None or data.empty:
            continue

        strategy = strategy_factory()
        result = run_backtest(strategy, data, symbol=sym, config=config, params=params)
        results.append(result)

    return results


# ======================================================================
# Parameter sweep / grid search
# ======================================================================

@dataclass
class SweepResult:
    """Result of a single parameter combination."""

    params: dict
    metrics: dict
    symbol: str


def run_sweep(
    strategy_factory,
    param_grid: dict[str, list],
    symbol: str,
    timeframe: str = "1d",
    config: BacktestConfig | None = None,
    sort_by: str = "total_return",
) -> list[SweepResult]:
    """Run a grid search over strategy parameters.

    Args:
        strategy_factory: Callable that returns a fresh Strategy instance.
        param_grid: Dict of param_name -> list of values to try.
                    Example: {"fast_period": [10, 20, 30], "slow_period": [50, 100]}
        symbol: Coin to test on.
        timeframe: Data timeframe.
        config: Backtest configuration.
        sort_by: Metric key to sort results by (descending).

    Returns:
        List of SweepResult, sorted by sort_by descending.
    """
    data = load_ohlcv(symbol, timeframe)
    if data is None or data.empty:
        print(f"No data for {symbol}.")
        return []

    config = config or BacktestConfig()

    # Generate all parameter combinations
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))

    results: list[SweepResult] = []

    for combo in combinations:
        params = dict(zip(keys, combo))
        strategy = strategy_factory()
        result = run_backtest(strategy, data, symbol=symbol, config=config, params=params)
        metrics = result.summary()

        results.append(SweepResult(
            params=params,
            metrics=metrics,
            symbol=symbol,
        ))

    # Sort by the chosen metric (descending)
    results.sort(key=lambda r: r.metrics.get(sort_by, 0), reverse=True)

    return results


def print_sweep_results(
    sweep_results: list[SweepResult],
    param_names: list[str] | None = None,
    top_n: int = 10,
) -> None:
    """Print a formatted table of sweep results."""
    if not sweep_results:
        print("  No sweep results.")
        return

    if param_names is None:
        param_names = list(sweep_results[0].params.keys())

    show = sweep_results[:top_n]

    # Build header
    param_hdrs = [f"{p:>12}" for p in param_names]
    metric_hdrs = ["Return", "Win%", "Sharpe", "MaxDD", "PF", "Trades"]
    header = "  #  " + "  ".join(param_hdrs) + "  " + "  ".join(f"{h:>8}" for h in metric_hdrs)
    print(header)
    print("  " + "─" * (len(header) - 2))

    for i, sr in enumerate(show, 1):
        param_vals = [f"{sr.params.get(p, ''):>12}" for p in param_names]
        m = sr.metrics
        metric_vals = [
            f"{m.get('total_return', 0):>+7.1%}",
            f"{m.get('win_rate', 0):>7.0%}",
            f"{m.get('sharpe_ratio', 0) or 0:>7.2f}",
            f"{m.get('max_drawdown', 0):>7.1%}",
            f"{m.get('profit_factor', 0):>7.2f}",
            f"{m.get('total_trades', 0):>7}",
        ]
        print(f"  {i:<3}" + "  ".join(param_vals) + "  " + "  ".join(metric_vals))

    if len(sweep_results) > top_n:
        print(f"  ... {len(sweep_results) - top_n} more combinations not shown")
