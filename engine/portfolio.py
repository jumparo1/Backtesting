"""
Portfolio tracker — positions, cash balance, P&L, trade log.
Supports both LONG and SHORT positions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from engine.order import Fill, OrderSide


@dataclass
class Position:
    """An open position in a single asset."""

    symbol: str
    quantity: float
    entry_price: float
    side: str = "LONG"  # "LONG" or "SHORT"
    entry_time: datetime | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.entry_price


@dataclass
class Trade:
    """A completed round-trip trade (entry + exit)."""

    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees: float = 0.0


class Portfolio:
    """Tracks cash, open positions, and completed trades."""

    def __init__(self, starting_capital: float = 10_000.0):
        self.starting_capital = starting_capital
        self.cash = starting_capital
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime | None, float]] = []

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def position_side(self, symbol: str) -> str | None:
        """Return 'LONG', 'SHORT', or None if no position."""
        pos = self.positions.get(symbol)
        return pos.side if pos else None

    def total_equity(self, current_prices: dict[str, float] | None = None) -> float:
        """Cash + mark-to-market value of all open positions."""
        equity = self.cash
        for sym, pos in self.positions.items():
            price = (current_prices or {}).get(sym, pos.entry_price)
            if pos.side == "LONG":
                equity += pos.quantity * price
            else:  # SHORT
                # Short P&L: profit when price drops below entry
                # Margin held = quantity * entry_price
                # Unrealized PnL = (entry_price - current_price) * quantity
                equity += pos.quantity * pos.entry_price + (pos.entry_price - price) * pos.quantity
        return equity

    # ------------------------------------------------------------------
    # LONG order application
    # ------------------------------------------------------------------

    def apply_buy(self, fill: Fill, stop_loss_pct: float | None, take_profit_pct: float | None) -> None:
        """Record a buy fill: deduct cash, open long position."""
        cost = fill.quantity * fill.price + fill.fee
        self.cash -= cost

        sl = fill.price * (1.0 - stop_loss_pct) if stop_loss_pct else None
        tp = fill.price * (1.0 + take_profit_pct) if take_profit_pct else None

        self.positions[fill.symbol] = Position(
            symbol=fill.symbol,
            quantity=fill.quantity,
            entry_price=fill.price,
            side="LONG",
            entry_time=fill.timestamp,
            stop_loss=sl,
            take_profit=tp,
        )

    def apply_sell(self, fill: Fill) -> Trade:
        """Record a sell fill: close long position, add proceeds, log trade."""
        pos = self.positions.pop(fill.symbol)
        proceeds = fill.quantity * fill.price - fill.fee
        self.cash += proceeds

        pnl = (fill.price - pos.entry_price) * fill.quantity - fill.fee
        entry_cost = pos.quantity * pos.entry_price
        pnl_pct = pnl / entry_cost if entry_cost > 0 else 0.0

        trade = Trade(
            symbol=fill.symbol,
            side="LONG",
            entry_price=pos.entry_price,
            exit_price=fill.price,
            quantity=fill.quantity,
            entry_time=pos.entry_time,
            exit_time=fill.timestamp,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fees=fill.fee,
        )
        self.trades.append(trade)
        return trade

    # ------------------------------------------------------------------
    # SHORT order application
    # ------------------------------------------------------------------

    def apply_short(self, fill: Fill, stop_loss_pct: float | None, take_profit_pct: float | None) -> None:
        """Record a short fill: reserve margin from cash, open short position."""
        # Margin = quantity * entry_price + fee
        margin = fill.quantity * fill.price + fill.fee
        self.cash -= margin

        # For shorts: SL is ABOVE entry, TP is BELOW entry
        sl = fill.price * (1.0 + stop_loss_pct) if stop_loss_pct else None
        tp = fill.price * (1.0 - take_profit_pct) if take_profit_pct else None

        self.positions[fill.symbol] = Position(
            symbol=fill.symbol,
            quantity=fill.quantity,
            entry_price=fill.price,
            side="SHORT",
            entry_time=fill.timestamp,
            stop_loss=sl,
            take_profit=tp,
        )

    def apply_cover(self, fill: Fill) -> Trade:
        """Record a cover fill: close short position, return margin +/- PnL."""
        pos = self.positions.pop(fill.symbol)

        # Short PnL: (entry_price - exit_price) * quantity - fees
        pnl = (pos.entry_price - fill.price) * fill.quantity - fill.fee
        margin = pos.quantity * pos.entry_price
        self.cash += margin + pnl

        entry_cost = pos.quantity * pos.entry_price
        pnl_pct = pnl / entry_cost if entry_cost > 0 else 0.0

        trade = Trade(
            symbol=fill.symbol,
            side="SHORT",
            entry_price=pos.entry_price,
            exit_price=fill.price,
            quantity=fill.quantity,
            entry_time=pos.entry_time,
            exit_time=fill.timestamp,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fees=fill.fee,
        )
        self.trades.append(trade)
        return trade

    def snapshot(self, timestamp: datetime | None, current_prices: dict[str, float] | None = None) -> None:
        """Record a point on the equity curve."""
        self.equity_curve.append((timestamp, self.total_equity(current_prices)))
