"""
Order representation and execution with slippage + fees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime


class OrderSide(Enum):
    BUY = auto()
    SELL = auto()


@dataclass
class Order:
    """A trade order created by a strategy.

    size_pct: fraction of available balance to allocate (BUY only).
              1.0 = all available balance. 0.02 = 2%.
    stop_loss_pct: optional stop-loss as fractional distance from entry.
    take_profit_pct: optional take-profit as fractional distance from entry.
    """

    symbol: str
    side: OrderSide
    size_pct: float = 1.0
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None


@dataclass
class Fill:
    """Record of an executed order."""

    symbol: str
    side: OrderSide
    price: float
    quantity: float
    fee: float
    slippage_cost: float
    timestamp: datetime | None = None


def execute_buy(
    order: Order,
    fill_price: float,
    available_balance: float,
    fee_pct: float,
    slippage_pct: float,
) -> Fill | None:
    """Execute a BUY order.

    fill_price: the raw price (next candle open).
    Returns a Fill or None if the order can't be filled.
    """
    if available_balance <= 0:
        return None

    alloc = available_balance * order.size_pct
    if alloc <= 0:
        return None

    # Apply slippage (buy at slightly higher price)
    actual_price = fill_price * (1.0 + slippage_pct)
    fee = alloc * fee_pct
    spend = alloc - fee
    if spend <= 0:
        return None

    quantity = spend / actual_price
    slippage_cost = quantity * fill_price * slippage_pct

    return Fill(
        symbol=order.symbol,
        side=OrderSide.BUY,
        price=actual_price,
        quantity=quantity,
        fee=fee,
        slippage_cost=slippage_cost,
    )


def execute_sell(
    symbol: str,
    quantity: float,
    fill_price: float,
    fee_pct: float,
    slippage_pct: float,
) -> Fill:
    """Execute a SELL (close position).

    fill_price: the raw price (next candle open, or stop/TP trigger).
    """
    # Slippage works against us — sell at slightly lower price
    actual_price = fill_price * (1.0 - slippage_pct)
    gross = quantity * actual_price
    fee = gross * fee_pct
    slippage_cost = quantity * fill_price * slippage_pct

    return Fill(
        symbol=symbol,
        side=OrderSide.SELL,
        price=actual_price,
        quantity=quantity,
        fee=fee,
        slippage_cost=slippage_cost,
    )
