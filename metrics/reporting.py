"""
Reporting module — console summary tables and CSV/JSON trade log export.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from config.settings import OUTPUT_DIR
from engine.portfolio import Trade
from metrics.performance import compute_metrics


# ======================================================================
# Console reporting
# ======================================================================

def print_summary(
    metrics: dict,
    strategy_name: str = "",
    symbol: str = "",
) -> None:
    """Print a nicely formatted summary table to the console."""
    w = 60  # total box width
    border = "═" * w
    thin = "─" * w

    title = "BACKTEST RESULTS"
    if strategy_name:
        title += f"  ·  {strategy_name}"
    if symbol:
        title += f"  ·  {symbol}"

    print()
    print(f"╔{border}╗")
    print(f"║{title:^{w}}║")
    print(f"╠{border}╣")

    _section(w, "RETURNS")
    _row(w, "Total Return", _pct(metrics.get("total_return")))
    _row(w, "Final Equity", _usd(metrics.get("final_equity")))
    _row(w, "Max Drawdown", _pct(metrics.get("max_drawdown")))
    _row(w, "Max DD Duration", f"{metrics.get('max_dd_duration_candles', '—')} candles")

    _section(w, "RISK-ADJUSTED")
    _row(w, "Sharpe Ratio", _num(metrics.get("sharpe_ratio")))
    _row(w, "Sortino Ratio", _num(metrics.get("sortino_ratio")))
    _row(w, "Profit Factor", _num(metrics.get("profit_factor")))

    _section(w, "TRADES")
    _row(w, "Total Trades", str(metrics.get("total_trades", 0)))
    _row(w, "Win Rate", _pct(metrics.get("win_rate")))
    _row(w, "Winning / Losing", f"{metrics.get('winning_trades', 0)} / {metrics.get('losing_trades', 0)}")
    _row(w, "Avg Win", _usd(metrics.get("avg_win")))
    _row(w, "Avg Loss", _usd(metrics.get("avg_loss")))
    _row(w, "Gross Profit", _usd(metrics.get("gross_profit")))
    _row(w, "Gross Loss", _usd(metrics.get("gross_loss")))

    _section(w, "ACTIVITY")
    _row(w, "Avg Duration", f"{metrics.get('avg_duration_days', 0):.1f} days")
    _row(w, "Exposure", _pct(metrics.get("exposure_pct")))
    _row(w, "Total Fees", _usd(metrics.get("total_fees")))

    print(f"╚{border}╝")
    print()


def print_comparison_table(
    results: list[tuple[str, dict]],
    title: str = "MULTI-SYMBOL COMPARISON",
) -> None:
    """Print a side-by-side comparison table for multiple symbols.

    Args:
        results: List of (symbol, metrics_dict) tuples.
        title: Table title.
    """
    if not results:
        print("No results to display.")
        return

    # Column definitions: (header, key, formatter, width)
    columns = [
        ("Symbol",   None,              str,   8),
        ("Trades",   "total_trades",    str,   7),
        ("Win%",     "win_rate",        _pct,  8),
        ("Return",   "total_return",    _pct,  9),
        ("Equity",   "final_equity",    _usd, 12),
        ("MaxDD",    "max_drawdown",    _pct,  8),
        ("Sharpe",   "sharpe_ratio",    _num,  8),
        ("Sortino",  "sortino_ratio",   _num,  8),
        ("PF",       "profit_factor",   _num,  6),
        ("Fees",     "total_fees",      _usd,  9),
    ]

    # Header
    header_parts = []
    sep_parts = []
    for hdr, _, _, w in columns:
        header_parts.append(f"{hdr:>{w}}")
        sep_parts.append("─" * w)

    print()
    print(f"  {title}")
    print(f"  {'  '.join(header_parts)}")
    print(f"  {'──'.join(sep_parts)}")

    # Rows
    for symbol, metrics in results:
        parts = []
        for hdr, key, fmt, w in columns:
            if key is None:
                val = symbol
            else:
                val = fmt(metrics.get(key))
            parts.append(f"{val:>{w}}")
        print(f"  {'  '.join(parts)}")

    print()


# ======================================================================
# Trade log display
# ======================================================================

def print_trade_log(trades: list[Trade], max_rows: int = 20) -> None:
    """Print a formatted trade log to the console."""
    if not trades:
        print("  No trades.")
        return

    show = trades[:max_rows]
    header = (
        f"  {'#':>3}  {'Entry Date':>12}  {'Exit Date':>12}  "
        f"{'Entry $':>12}  {'Exit $':>12}  {'P&L':>10}  {'P&L%':>8}  {'Result':>6}"
    )
    print(header)
    print(f"  {'─' * (len(header) - 2)}")

    for i, t in enumerate(show, 1):
        entry_date = _fmt_date(t.entry_time)
        exit_date = _fmt_date(t.exit_time)
        result = "WIN" if t.pnl > 0 else "LOSS"
        pnl_str = f"${t.pnl:>+,.2f}"
        pnl_pct_str = f"{t.pnl_pct:>+.2%}"
        print(
            f"  {i:>3}  {entry_date:>12}  {exit_date:>12}  "
            f"${t.entry_price:>11,.2f}  ${t.exit_price:>11,.2f}  "
            f"{pnl_str:>10}  {pnl_pct_str:>8}  {result:>6}"
        )

    if len(trades) > max_rows:
        print(f"  ... and {len(trades) - max_rows} more trades")


# ======================================================================
# CSV / JSON export
# ======================================================================

def export_trades_csv(
    trades: list[Trade],
    filepath: str | Path | None = None,
    symbol: str = "",
    strategy_name: str = "",
) -> Path:
    """Export trade log to a CSV file.

    Returns the path of the written file.
    """
    if filepath is None:
        parts = [strategy_name or "backtest", symbol, "trades"]
        filename = "_".join(p for p in parts if p) + ".csv"
        filepath = OUTPUT_DIR / filename

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "trade_num", "symbol", "side",
        "entry_date", "exit_date",
        "entry_price", "exit_price",
        "quantity", "pnl", "pnl_pct", "fees",
        "duration_days",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, t in enumerate(trades, 1):
            entry_dt = _to_dt(t.entry_time)
            exit_dt = _to_dt(t.exit_time)
            duration = ""
            if entry_dt and exit_dt:
                duration = f"{(exit_dt - entry_dt).total_seconds() / 86400:.1f}"

            writer.writerow({
                "trade_num": i,
                "symbol": t.symbol,
                "side": t.side,
                "entry_date": _fmt_date(t.entry_time),
                "exit_date": _fmt_date(t.exit_time),
                "entry_price": f"{t.entry_price:.2f}",
                "exit_price": f"{t.exit_price:.2f}",
                "quantity": f"{t.quantity:.8f}",
                "pnl": f"{t.pnl:.2f}",
                "pnl_pct": f"{t.pnl_pct:.4f}",
                "fees": f"{t.fees:.2f}",
                "duration_days": duration,
            })

    return filepath


def export_equity_csv(
    equity_curve: list[tuple[datetime | None, float]],
    filepath: str | Path | None = None,
    symbol: str = "",
    strategy_name: str = "",
) -> Path:
    """Export the equity curve to a CSV file."""
    if filepath is None:
        parts = [strategy_name or "backtest", symbol, "equity"]
        filename = "_".join(p for p in parts if p) + ".csv"
        filepath = OUTPUT_DIR / filename

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "equity"])
        for ts, eq in equity_curve:
            writer.writerow([_fmt_date(ts), f"{eq:.2f}"])

    return filepath


def export_summary_json(
    metrics: dict,
    filepath: str | Path | None = None,
    symbol: str = "",
    strategy_name: str = "",
) -> Path:
    """Export metrics summary to a JSON file."""
    if filepath is None:
        parts = [strategy_name or "backtest", symbol, "summary"]
        filename = "_".join(p for p in parts if p) + ".json"
        filepath = OUTPUT_DIR / filename

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "strategy": strategy_name,
        "symbol": symbol,
        "metrics": metrics,
    }

    with open(filepath, "w") as f:
        json.dump(output, f, indent=2, default=str)

    return filepath


# ======================================================================
# Formatting helpers
# ======================================================================

def _row(w: int, label: str, value: str) -> None:
    """Print a single key-value row inside the box."""
    padding = w - len(label) - len(value) - 4
    print(f"║  {label}{'·' * max(padding, 1)}{value}  ║")


def _section(w: int, title: str) -> None:
    """Print a section header."""
    print(f"║{'─' * w}║")
    print(f"║  {title:<{w - 4}}  ║")
    print(f"║{'─' * w}║")


def _pct(val) -> str:
    if val is None:
        return "—"
    return f"{val:.2%}"


def _usd(val) -> str:
    if val is None:
        return "—"
    return f"${val:,.2f}"


def _num(val) -> str:
    if val is None:
        return "—"
    if val == float("inf"):
        return "∞"
    return f"{val:.2f}"


def _fmt_date(val) -> str:
    if val is None:
        return "—"
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    return str(val)[:10]


def _to_dt(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime()
    return None
