"""
Performance metrics calculator.

Takes a BacktestResult and computes all core metrics from FRAMEWORK.md:
  - Win Rate
  - Total Return
  - Max Drawdown
  - Sharpe Ratio (annualized)
  - Sortino Ratio (annualized)
  - Profit Factor
  - Avg Win / Avg Loss
  - Trade Count
  - Avg Trade Duration
  - Exposure %
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from engine.portfolio import Trade


def compute_metrics(
    trades: list[Trade],
    equity_curve: list[tuple[datetime | None, float]],
    starting_capital: float,
    trading_days_per_year: float = 365.0,
) -> dict:
    """Compute full performance metrics from backtest outputs.

    Args:
        trades: List of completed Trade objects.
        equity_curve: List of (timestamp, equity) tuples — one per candle.
        starting_capital: Initial portfolio value.
        trading_days_per_year: Annualization factor (365 for crypto).

    Returns:
        Dict of metric_name -> value.
    """
    if not equity_curve:
        return {"error": "no equity data"}

    # ------------------------------------------------------------------
    # Basic trade stats
    # ------------------------------------------------------------------
    total_trades = len(trades)
    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl <= 0]

    win_rate = len(winning) / total_trades if total_trades else 0.0
    avg_win = sum(t.pnl for t in winning) / len(winning) if winning else 0.0
    avg_loss = sum(t.pnl for t in losing) / len(losing) if losing else 0.0
    total_fees = sum(t.fees for t in trades)

    gross_profit = sum(t.pnl for t in winning)
    gross_loss = abs(sum(t.pnl for t in losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 9999.99

    # ------------------------------------------------------------------
    # Return
    # ------------------------------------------------------------------
    final_equity = equity_curve[-1][1]
    total_return = (final_equity - starting_capital) / starting_capital

    # ------------------------------------------------------------------
    # Max Drawdown
    # ------------------------------------------------------------------
    peak = 0.0
    max_dd = 0.0
    max_dd_duration = 0
    current_dd_start = 0
    in_drawdown = False

    for idx, (_, eq) in enumerate(equity_curve):
        if eq > peak:
            if in_drawdown:
                dd_len = idx - current_dd_start
                if dd_len > max_dd_duration:
                    max_dd_duration = dd_len
                in_drawdown = False
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > 0 and not in_drawdown:
            in_drawdown = True
            current_dd_start = idx
        if dd > max_dd:
            max_dd = dd

    # If still in drawdown at end
    if in_drawdown:
        dd_len = len(equity_curve) - current_dd_start
        if dd_len > max_dd_duration:
            max_dd_duration = dd_len

    # ------------------------------------------------------------------
    # Daily returns for Sharpe / Sortino
    # ------------------------------------------------------------------
    equities = [eq for _, eq in equity_curve]
    daily_returns: list[float] = []
    for i in range(1, len(equities)):
        prev = equities[i - 1]
        if prev > 0:
            daily_returns.append((equities[i] - prev) / prev)

    sharpe = _sharpe_ratio(daily_returns, trading_days_per_year)
    sortino = _sortino_ratio(daily_returns, trading_days_per_year)

    # ------------------------------------------------------------------
    # Average trade duration
    # ------------------------------------------------------------------
    durations: list[float] = []
    for t in trades:
        if t.entry_time is not None and t.exit_time is not None:
            entry = _to_datetime(t.entry_time)
            exit_ = _to_datetime(t.exit_time)
            if entry and exit_:
                delta = (exit_ - entry).total_seconds() / 86400.0  # days
                durations.append(delta)

    avg_duration_days = sum(durations) / len(durations) if durations else 0.0

    # ------------------------------------------------------------------
    # Exposure % — fraction of candles where capital was deployed
    # ------------------------------------------------------------------
    # We approximate this from the trades: count candles between each
    # entry and exit vs. total candles.
    total_candles = len(equity_curve)
    if total_candles > 0 and trades:
        exposed_candles = _count_exposed_candles(trades, equity_curve)
        exposure_pct = exposed_candles / total_candles
    else:
        exposure_pct = 0.0

    # ------------------------------------------------------------------
    # Assemble output
    # ------------------------------------------------------------------
    return {
        "total_trades": total_trades,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(win_rate, 4),
        "total_return": round(total_return, 4),
        "final_equity": round(final_equity, 2),
        "max_drawdown": round(max_dd, 4),
        "max_dd_duration_candles": max_dd_duration,
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "sortino_ratio": round(sortino, 4) if sortino is not None else None,
        "profit_factor": round(profit_factor, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "total_fees": round(total_fees, 2),
        "avg_duration_days": round(avg_duration_days, 1),
        "exposure_pct": round(exposure_pct, 4),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }


# ----------------------------------------------------------------------
# Sharpe Ratio
# ----------------------------------------------------------------------

def _sharpe_ratio(
    daily_returns: list[float],
    trading_days_per_year: float,
    risk_free_rate: float = 0.0,
) -> float | None:
    """Annualized Sharpe Ratio.

    Sharpe = (mean_return - risk_free_daily) / std(returns) * sqrt(N)
    """
    if len(daily_returns) < 2:
        return None

    rf_daily = (1 + risk_free_rate) ** (1 / trading_days_per_year) - 1
    excess = [r - rf_daily for r in daily_returns]
    mean_excess = sum(excess) / len(excess)
    variance = sum((r - mean_excess) ** 2 for r in excess) / (len(excess) - 1)
    std = math.sqrt(variance)

    if std == 0:
        return None
    return (mean_excess / std) * math.sqrt(trading_days_per_year)


# ----------------------------------------------------------------------
# Sortino Ratio
# ----------------------------------------------------------------------

def _sortino_ratio(
    daily_returns: list[float],
    trading_days_per_year: float,
    risk_free_rate: float = 0.0,
) -> float | None:
    """Annualized Sortino Ratio.

    Like Sharpe but uses only downside deviation (negative returns).
    """
    if len(daily_returns) < 2:
        return None

    rf_daily = (1 + risk_free_rate) ** (1 / trading_days_per_year) - 1
    excess = [r - rf_daily for r in daily_returns]
    mean_excess = sum(excess) / len(excess)

    downside = [r for r in excess if r < 0]
    if not downside:
        return 9999.99 if mean_excess > 0 else None

    downside_var = sum(r ** 2 for r in downside) / len(excess)  # denominator = all periods
    downside_std = math.sqrt(downside_var)

    if downside_std == 0:
        return None
    return (mean_excess / downside_std) * math.sqrt(trading_days_per_year)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _to_datetime(val) -> datetime | None:
    """Coerce a timestamp value to a plain datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    # pandas Timestamp
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime()
    return None


def _count_exposed_candles(
    trades: list[Trade],
    equity_curve: list[tuple[datetime | None, float]],
) -> int:
    """Count how many equity-curve candles fall inside a trade's holding period."""
    if not trades or not equity_curve:
        return 0

    timestamps = [ts for ts, _ in equity_curve if ts is not None]
    if not timestamps:
        return 0

    exposed = set()
    for t in trades:
        entry = _to_datetime(t.entry_time)
        exit_ = _to_datetime(t.exit_time)
        if entry is None or exit_ is None:
            continue
        for idx, ts in enumerate(timestamps):
            ts_dt = _to_datetime(ts)
            if ts_dt and entry <= ts_dt <= exit_:
                exposed.add(idx)

    return len(exposed)
