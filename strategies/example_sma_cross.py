"""
Example strategy: SMA crossover.

Buy when fast SMA crosses above slow SMA (golden cross).
Sell when fast SMA crosses below slow SMA (death cross).
"""

from __future__ import annotations

from engine.order import Order
from strategies.base import Strategy


class SMACrossover(Strategy):
    def __init__(self):
        super().__init__(
            name="SMA Crossover",
            description="Buy on golden cross, sell on death cross",
        )
        self.fast_period = 20
        self.slow_period = 50
        self.size_pct = 0.95  # allocate 95% of balance per trade
        self.stop_loss_pct = 0.05
        self.take_profit_pct = 0.10
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def setup(self, params: dict) -> None:
        self.fast_period = params.get("fast_period", self.fast_period)
        self.slow_period = params.get("slow_period", self.slow_period)
        self.size_pct = params.get("size_pct", self.size_pct)
        self.stop_loss_pct = params.get("stop_loss_pct", self.stop_loss_pct)
        self.take_profit_pct = params.get("take_profit_pct", self.take_profit_pct)
        self._prev_fast = None
        self._prev_slow = None

    def on_candle(self, candle: dict, indicators, portfolio) -> list[Order]:
        fast = indicators.sma(self.fast_period)
        slow = indicators.sma(self.slow_period)

        if fast is None or slow is None:
            return []

        orders: list[Order] = []
        symbol = candle["symbol"]

        # Detect crossover (fast crosses above slow)
        if (
            self._prev_fast is not None
            and self._prev_slow is not None
            and self._prev_fast <= self._prev_slow
            and fast > slow
            and not portfolio.has_position(symbol)
        ):
            orders.append(
                self.buy(
                    symbol=symbol,
                    size_pct=self.size_pct,
                    stop_loss_pct=self.stop_loss_pct,
                    take_profit_pct=self.take_profit_pct,
                )
            )

        # Detect crossunder (fast crosses below slow)
        if (
            self._prev_fast is not None
            and self._prev_slow is not None
            and self._prev_fast >= self._prev_slow
            and fast < slow
            and portfolio.has_position(symbol)
        ):
            orders.append(self.sell(symbol=symbol))

        self._prev_fast = fast
        self._prev_slow = slow
        return orders
