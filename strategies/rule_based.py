"""
Rule-based strategy — composable buy/sell conditions from indicator rules.

This is the bridge between natural-language trade ideas and the backtesting
engine. Instead of writing a Strategy subclass, you define rules like:

    buy_rules  = [RSIBelow(30), PriceBelowBollinger("lower")]
    sell_rules = [RSIAbove(70), PriceAboveBollinger("upper")]

Rules are AND'd together by default. Any rule can be individually negated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from engine.order import Order
from indicators.base import IndicatorEngine
from strategies.base import Strategy


# ======================================================================
# Rule interface
# ======================================================================

class Rule(ABC):
    """A single boolean condition evaluated on each candle."""

    @abstractmethod
    def evaluate(self, candle: dict, indicators: IndicatorEngine, portfolio) -> bool:
        ...

    @abstractmethod
    def describe(self) -> str:
        """Human-readable description of this rule."""
        ...


# ======================================================================
# Indicator-based rules
# ======================================================================

class RSIBelow(Rule):
    def __init__(self, threshold: float, period: int = 14):
        self.threshold = threshold
        self.period = period

    def evaluate(self, candle, indicators, portfolio) -> bool:
        rsi = indicators.rsi(self.period)
        return rsi is not None and rsi < self.threshold

    def describe(self) -> str:
        return f"RSI({self.period}) < {self.threshold}"


class RSIAbove(Rule):
    def __init__(self, threshold: float, period: int = 14):
        self.threshold = threshold
        self.period = period

    def evaluate(self, candle, indicators, portfolio) -> bool:
        rsi = indicators.rsi(self.period)
        return rsi is not None and rsi > self.threshold

    def describe(self) -> str:
        return f"RSI({self.period}) > {self.threshold}"


class SMACrossAbove(Rule):
    """Fast SMA crosses above slow SMA."""
    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def evaluate(self, candle, indicators, portfolio) -> bool:
        fast_val = indicators.sma(self.fast)
        slow_val = indicators.sma(self.slow)
        if fast_val is None or slow_val is None:
            return False

        crossed = (
            self._prev_fast is not None
            and self._prev_slow is not None
            and self._prev_fast <= self._prev_slow
            and fast_val > slow_val
        )
        self._prev_fast = fast_val
        self._prev_slow = slow_val
        return crossed

    def describe(self) -> str:
        return f"SMA({self.fast}) crosses above SMA({self.slow})"


class SMACrossBelow(Rule):
    """Fast SMA crosses below slow SMA."""
    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def evaluate(self, candle, indicators, portfolio) -> bool:
        fast_val = indicators.sma(self.fast)
        slow_val = indicators.sma(self.slow)
        if fast_val is None or slow_val is None:
            return False

        crossed = (
            self._prev_fast is not None
            and self._prev_slow is not None
            and self._prev_fast >= self._prev_slow
            and fast_val < slow_val
        )
        self._prev_fast = fast_val
        self._prev_slow = slow_val
        return crossed

    def describe(self) -> str:
        return f"SMA({self.fast}) crosses below SMA({self.slow})"


class EMACrossAbove(Rule):
    """Fast EMA crosses above slow EMA."""
    def __init__(self, fast: int = 12, slow: int = 26):
        self.fast = fast
        self.slow = slow
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def evaluate(self, candle, indicators, portfolio) -> bool:
        fast_val = indicators.ema(self.fast)
        slow_val = indicators.ema(self.slow)
        if fast_val is None or slow_val is None:
            return False

        crossed = (
            self._prev_fast is not None
            and self._prev_slow is not None
            and self._prev_fast <= self._prev_slow
            and fast_val > slow_val
        )
        self._prev_fast = fast_val
        self._prev_slow = slow_val
        return crossed

    def describe(self) -> str:
        return f"EMA({self.fast}) crosses above EMA({self.slow})"


class EMACrossBelow(Rule):
    """Fast EMA crosses below slow EMA."""
    def __init__(self, fast: int = 12, slow: int = 26):
        self.fast = fast
        self.slow = slow
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def evaluate(self, candle, indicators, portfolio) -> bool:
        fast_val = indicators.ema(self.fast)
        slow_val = indicators.ema(self.slow)
        if fast_val is None or slow_val is None:
            return False

        crossed = (
            self._prev_fast is not None
            and self._prev_slow is not None
            and self._prev_fast >= self._prev_slow
            and fast_val < slow_val
        )
        self._prev_fast = fast_val
        self._prev_slow = slow_val
        return crossed

    def describe(self) -> str:
        return f"EMA({self.fast}) crosses below EMA({self.slow})"


class PriceAboveSMA(Rule):
    def __init__(self, period: int = 50):
        self.period = period

    def evaluate(self, candle, indicators, portfolio) -> bool:
        sma = indicators.sma(self.period)
        return sma is not None and candle["close"] > sma

    def describe(self) -> str:
        return f"Price above SMA({self.period})"


class PriceBelowSMA(Rule):
    def __init__(self, period: int = 50):
        self.period = period

    def evaluate(self, candle, indicators, portfolio) -> bool:
        sma = indicators.sma(self.period)
        return sma is not None and candle["close"] < sma

    def describe(self) -> str:
        return f"Price below SMA({self.period})"


class PriceAboveEMA(Rule):
    def __init__(self, period: int = 50):
        self.period = period

    def evaluate(self, candle, indicators, portfolio) -> bool:
        ema = indicators.ema(self.period)
        return ema is not None and candle["close"] > ema

    def describe(self) -> str:
        return f"Price above EMA({self.period})"


class PriceBelowEMA(Rule):
    def __init__(self, period: int = 50):
        self.period = period

    def evaluate(self, candle, indicators, portfolio) -> bool:
        ema = indicators.ema(self.period)
        return ema is not None and candle["close"] < ema

    def describe(self) -> str:
        return f"Price below EMA({self.period})"


class PriceAboveBollinger(Rule):
    """Price above the upper Bollinger Band."""
    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std

    def evaluate(self, candle, indicators, portfolio) -> bool:
        bb = indicators.bollinger(self.period, self.num_std)
        return bb is not None and candle["close"] > bb[0]  # upper

    def describe(self) -> str:
        return f"Price above Bollinger upper({self.period}, {self.num_std}σ)"


class PriceBelowBollinger(Rule):
    """Price below the lower Bollinger Band."""
    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std

    def evaluate(self, candle, indicators, portfolio) -> bool:
        bb = indicators.bollinger(self.period, self.num_std)
        return bb is not None and candle["close"] < bb[2]  # lower

    def describe(self) -> str:
        return f"Price below Bollinger lower({self.period}, {self.num_std}σ)"


class MACDCrossAbove(Rule):
    """MACD line crosses above signal line."""
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self._prev_hist: float | None = None

    def evaluate(self, candle, indicators, portfolio) -> bool:
        macd = indicators.macd(self.fast, self.slow, self.signal)
        if macd is None:
            return False
        hist = macd[2]
        crossed = self._prev_hist is not None and self._prev_hist <= 0 and hist > 0
        self._prev_hist = hist
        return crossed

    def describe(self) -> str:
        return f"MACD({self.fast},{self.slow},{self.signal}) crosses above signal"


class MACDCrossBelow(Rule):
    """MACD line crosses below signal line."""
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self._prev_hist: float | None = None

    def evaluate(self, candle, indicators, portfolio) -> bool:
        macd = indicators.macd(self.fast, self.slow, self.signal)
        if macd is None:
            return False
        hist = macd[2]
        crossed = self._prev_hist is not None and self._prev_hist >= 0 and hist < 0
        self._prev_hist = hist
        return crossed

    def describe(self) -> str:
        return f"MACD({self.fast},{self.slow},{self.signal}) crosses below signal"


class MACDAboveZero(Rule):
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def evaluate(self, candle, indicators, portfolio) -> bool:
        macd = indicators.macd(self.fast, self.slow, self.signal)
        return macd is not None and macd[0] > 0

    def describe(self) -> str:
        return f"MACD line > 0"


class MACDBelowZero(Rule):
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def evaluate(self, candle, indicators, portfolio) -> bool:
        macd = indicators.macd(self.fast, self.slow, self.signal)
        return macd is not None and macd[0] < 0

    def describe(self) -> str:
        return f"MACD line < 0"


class VolumeAboveAvg(Rule):
    """Current volume > N-period average volume * multiplier."""
    def __init__(self, period: int = 20, multiplier: float = 1.5):
        self.period = period
        self.multiplier = multiplier

    def evaluate(self, candle, indicators, portfolio) -> bool:
        if indicators.size < self.period:
            return False
        vols = [c["volume"] for c in indicators.history[-self.period:]]
        avg_vol = sum(vols) / len(vols)
        return candle["volume"] > avg_vol * self.multiplier

    def describe(self) -> str:
        return f"Volume > {self.multiplier}x avg({self.period})"


class ATRAbove(Rule):
    """ATR above a threshold (useful for volatility filters)."""
    def __init__(self, threshold_pct: float = 0.03, period: int = 14):
        self.threshold_pct = threshold_pct
        self.period = period

    def evaluate(self, candle, indicators, portfolio) -> bool:
        atr = indicators.atr(self.period)
        if atr is None:
            return False
        return (atr / candle["close"]) > self.threshold_pct

    def describe(self) -> str:
        return f"ATR({self.period})/price > {self.threshold_pct:.1%}"


# ======================================================================
# RuleBasedStrategy
# ======================================================================

class RuleBasedStrategy(Strategy):
    """Strategy built from composable buy/sell rules.

    All buy_rules must be True to trigger a buy (AND logic).
    All sell_rules must be True to trigger a sell (AND logic).
    """

    def __init__(
        self,
        name: str = "Custom Strategy",
        description: str = "",
        buy_rules: list[Rule] | None = None,
        sell_rules: list[Rule] | None = None,
        size_pct: float = 0.95,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ):
        super().__init__(name=name, description=description)
        self.buy_rules = buy_rules or []
        self.sell_rules = sell_rules or []
        self.size_pct = size_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    def setup(self, params: dict) -> None:
        self.size_pct = params.get("size_pct", self.size_pct)
        self.stop_loss_pct = params.get("stop_loss_pct", self.stop_loss_pct)
        self.take_profit_pct = params.get("take_profit_pct", self.take_profit_pct)

    def on_candle(self, candle: dict, indicators, portfolio) -> list[Order]:
        symbol = candle["symbol"]
        orders: list[Order] = []

        has_pos = portfolio.has_position(symbol)

        # Check buy rules (all must be true)
        if not has_pos and self.buy_rules:
            if all(r.evaluate(candle, indicators, portfolio) for r in self.buy_rules):
                orders.append(
                    self.buy(
                        symbol=symbol,
                        size_pct=self.size_pct,
                        stop_loss_pct=self.stop_loss_pct,
                        take_profit_pct=self.take_profit_pct,
                    )
                )

        # Check sell rules (all must be true)
        if has_pos and self.sell_rules:
            if all(r.evaluate(candle, indicators, portfolio) for r in self.sell_rules):
                orders.append(self.sell(symbol=symbol))

        # Even if not triggered, rules with crossover state still need updating
        # (crossover rules track prev values internally via evaluate())
        if not self.buy_rules or has_pos:
            for r in self.buy_rules:
                if hasattr(r, '_prev_fast') or hasattr(r, '_prev_hist'):
                    r.evaluate(candle, indicators, portfolio)
        if not self.sell_rules or not has_pos:
            for r in self.sell_rules:
                if hasattr(r, '_prev_fast') or hasattr(r, '_prev_hist'):
                    r.evaluate(candle, indicators, portfolio)

        return orders

    def describe_rules(self) -> str:
        """Return a human-readable description of all rules."""
        lines = [f"Strategy: {self.name}"]
        if self.description:
            lines.append(f"  {self.description}")
        lines.append("")
        lines.append("  BUY when ALL of:")
        for r in self.buy_rules:
            lines.append(f"    • {r.describe()}")
        lines.append("")
        lines.append("  SELL when ALL of:")
        for r in self.sell_rules:
            lines.append(f"    • {r.describe()}")
        if self.stop_loss_pct:
            lines.append(f"\n  Stop-loss: {self.stop_loss_pct:.1%}")
        if self.take_profit_pct:
            lines.append(f"  Take-profit: {self.take_profit_pct:.1%}")
        return "\n".join(lines)
