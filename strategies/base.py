"""
Base Strategy class — all user strategies subclass this.

Strategies implement `on_candle()` which receives the current candle,
an IndicatorEngine with the full history up to now, and the current
portfolio state. They return a list of Order objects (or an empty list
to hold).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from engine.order import Order, OrderSide


class Strategy(ABC):
    """Abstract base strategy.

    Subclass and implement:
        setup(params)  — configure parameters
        on_candle(candle, indicators, portfolio) — return list of Orders
    """

    def __init__(self, name: str = "", description: str = ""):
        self.name = name or self.__class__.__name__
        self.description = description

    def setup(self, params: dict) -> None:
        """Override to set strategy parameters from a dict."""
        pass

    @abstractmethod
    def on_candle(self, candle: dict, indicators, portfolio) -> list[Order]:
        """Called on every candle. Return a list of Order objects to execute.

        Args:
            candle: dict with {timestamp, open, high, low, close, volume, symbol}
            indicators: IndicatorEngine with history up to current candle
            portfolio: Portfolio snapshot (balance, positions)

        Returns:
            List of Order objects. Empty list = hold / do nothing.
        """
        ...

    # ------------------------------------------------------------------
    # Convenience helpers for creating orders
    # ------------------------------------------------------------------

    def buy(
        self,
        symbol: str,
        size_pct: float = 1.0,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ) -> Order:
        """Create a market BUY order."""
        return Order(
            symbol=symbol,
            side=OrderSide.BUY,
            size_pct=size_pct,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

    def sell(self, symbol: str) -> Order:
        """Create a market SELL order (close entire position)."""
        return Order(
            symbol=symbol,
            side=OrderSide.SELL,
        )
