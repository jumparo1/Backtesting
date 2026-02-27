"""
Base indicator interface.

Indicators operate on a rolling window of OHLCV data (as a list of dicts)
and return the current computed value. They are designed for candle-by-candle
evaluation with no look-ahead — only past and current data is visible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class IndicatorEngine:
    """Manages indicator computations over a growing candle history.

    Feed candles one at a time via `push(candle)`. Then query any indicator
    by name. Results are computed from the full history up to the current bar.

    Candle format: dict with keys {timestamp, open, high, low, close, volume}.
    """

    history: list[dict] = field(default_factory=list)

    def push(self, candle: dict) -> None:
        """Append a new candle to the history."""
        self.history.append(candle)

    def reset(self) -> None:
        """Clear all history."""
        self.history.clear()

    @property
    def size(self) -> int:
        return len(self.history)

    # ------------------------------------------------------------------
    # Price helpers
    # ------------------------------------------------------------------

    def _closes(self, n: int | None = None) -> list[float]:
        """Return the last `n` close prices (or all if n is None)."""
        if n is None:
            return [c["close"] for c in self.history]
        return [c["close"] for c in self.history[-n:]]

    def _highs(self, n: int | None = None) -> list[float]:
        if n is None:
            return [c["high"] for c in self.history]
        return [c["high"] for c in self.history[-n:]]

    def _lows(self, n: int | None = None) -> list[float]:
        if n is None:
            return [c["low"] for c in self.history]
        return [c["low"] for c in self.history[-n:]]

    # ------------------------------------------------------------------
    # Moving Averages
    # ------------------------------------------------------------------

    def sma(self, period: int) -> float | None:
        """Simple Moving Average over the last `period` closes."""
        if self.size < period:
            return None
        return sum(self._closes(period)) / period

    def ema(self, period: int) -> float | None:
        """Exponential Moving Average over closes.

        Uses the standard smoothing factor k = 2 / (period + 1).
        Computes from the beginning of history so the result stabilises
        after `period` bars.
        """
        if self.size < period:
            return None
        closes = self._closes()
        k = 2.0 / (period + 1)
        # Seed with SMA of first `period` values
        ema_val = sum(closes[:period]) / period
        for price in closes[period:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val

    # ------------------------------------------------------------------
    # Momentum
    # ------------------------------------------------------------------

    def rsi(self, period: int = 14) -> float | None:
        """Relative Strength Index (Wilder's smoothing)."""
        # Need period + 1 closes to get `period` changes
        if self.size < period + 1:
            return None
        closes = self._closes()
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        # Seed averages with simple mean of first `period` changes
        gains = [max(c, 0) for c in changes[:period]]
        losses = [max(-c, 0) for c in changes[:period]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        # Wilder smoothing for remaining changes
        for c in changes[period:]:
            avg_gain = (avg_gain * (period - 1) + max(c, 0)) / period
            avg_loss = (avg_loss * (period - 1) + max(-c, 0)) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def macd(
        self, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[float, float, float] | None:
        """MACD line, signal line, and histogram.

        Returns (macd_line, signal_line, histogram) or None if insufficient data.
        """
        if self.size < slow + signal:
            return None

        closes = self._closes()

        def _ema_series(data: list[float], period: int) -> list[float]:
            k = 2.0 / (period + 1)
            result = [sum(data[:period]) / period]
            for val in data[period:]:
                result.append(val * k + result[-1] * (1 - k))
            return result

        fast_ema = _ema_series(closes, fast)
        slow_ema = _ema_series(closes, slow)

        # Align: slow_ema starts at index 0, fast_ema is longer
        offset = slow - fast
        macd_line_series = [
            fast_ema[offset + i] - slow_ema[i] for i in range(len(slow_ema))
        ]

        signal_ema = _ema_series(macd_line_series, signal)
        macd_val = macd_line_series[-1]
        signal_val = signal_ema[-1]
        histogram = macd_val - signal_val
        return (macd_val, signal_val, histogram)

    # ------------------------------------------------------------------
    # Volatility
    # ------------------------------------------------------------------

    def bollinger(
        self, period: int = 20, num_std: float = 2.0
    ) -> tuple[float, float, float] | None:
        """Bollinger Bands: (upper, middle, lower)."""
        if self.size < period:
            return None
        closes = self._closes(period)
        middle = sum(closes) / period
        variance = sum((c - middle) ** 2 for c in closes) / period
        std = math.sqrt(variance)
        return (middle + num_std * std, middle, middle - num_std * std)

    def atr(self, period: int = 14) -> float | None:
        """Average True Range."""
        if self.size < period + 1:
            return None

        trs: list[float] = []
        for i in range(1, self.size):
            h = self.history[i]["high"]
            l = self.history[i]["low"]
            pc = self.history[i - 1]["close"]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)

        # Wilder smoothing: seed with simple average, then smooth
        atr_val = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr_val = (atr_val * (period - 1) + tr) / period
        return atr_val
