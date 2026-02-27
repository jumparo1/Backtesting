"""
CRT + CISD Strategy — Candle Range Theory + Change in State of Delivery.

A 3-candle price-action pattern that identifies liquidity grabs and
structural shifts for high-RR entries.

Pattern (3 consecutive candles):
  C1 (Setup)        — establishes a range; its high/low are liquidity pools.
  C2 (Manipulation) — sweeps beyond C1's extreme to grab liquidity.
  C3 (Expansion)    — price reverses in the opposite direction of the sweep.

LONG setup  (Bullish CRT):
  • C2 wick sweeps below C1 low  (sell-side liquidity grabbed)
  • C2 body (open-close) inside C1 body  (inside candle)
  • C2 closes green (close > open)  — bullish rejection
  • Enter long at C3 open
  • SL = C2 low (natural invalidation)
  • TP = entry + 2.5 × risk  (2.5R)

SELL signal (Bearish CRT):
  • C2 wick sweeps above C1 high  (buy-side liquidity grabbed)
  • C2 body inside C1 body
  • C2 closes red (close < open)  — bearish rejection
  • Close any open long position

Note: The engine is long-only. Bearish CRT patterns act as EXIT signals
(close longs) rather than short entries. Based on ICT Power of 3 (AMD).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy

from strategies.base import Strategy
from engine.order import Order, OrderSide


@dataclass
class CandleSnapshot:
    """Lightweight snapshot of a single candle."""
    timestamp: object
    open: float
    high: float
    low: float
    close: float
    volume: float


def _snap(candle: dict) -> CandleSnapshot:
    return CandleSnapshot(
        timestamp=candle.get("timestamp"),
        open=candle["open"],
        high=candle["high"],
        low=candle["low"],
        close=candle["close"],
        volume=candle.get("volume", 0),
    )


class CRTCISDStrategy(Strategy):
    """CRT + CISD — enter on bullish liquidity sweeps, exit on bearish ones.

    Parameters (via setup()):
        rr_target   — reward-to-risk multiple for take-profit (default 2.5)
        size_pct    — fraction of available cash to deploy (default 0.95)
        require_close_inside — C2 must close inside C1 range (default True)
        min_sweep_pct — minimum sweep depth as % of C1 range (default 0.0)
    """

    def __init__(self):
        super().__init__(
            name="CRT + CISD",
            description=(
                "Candle Range Theory — enter long when C2 sweeps below C1 low "
                "(sell-side liquidity grab), exit when C2 sweeps above C1 high "
                "(buy-side grab). TP at 2.5R, SL at C2 low."
            ),
        )
        # Tuneable parameters
        self.rr_target: float = 2.5
        self.size_pct: float = 0.95
        self.require_close_inside: bool = True
        self.min_sweep_pct: float = 0.0  # e.g. 0.10 = wick must be ≥10% of C1 range

        # Internal state
        self._prev: CandleSnapshot | None = None   # C1
        self._curr: CandleSnapshot | None = None   # C2 candidate
        self._signal_sl: float | None = None        # SL level from last signal

    def setup(self, params: dict) -> None:
        self.rr_target = float(params.get("rr_target", self.rr_target))
        self.size_pct = float(params.get("size_pct", self.size_pct))
        self.require_close_inside = bool(params.get("require_close_inside", self.require_close_inside))
        self.min_sweep_pct = float(params.get("min_sweep_pct", self.min_sweep_pct))

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def on_candle(self, candle: dict, indicators, portfolio) -> list[Order]:
        snap = _snap(candle)
        symbol = candle["symbol"]
        orders: list[Order] = []

        if self._prev is not None and self._curr is not None:
            c1 = self._prev
            c2 = self._curr  # the candle that just completed

            has_position = portfolio.has_position(symbol)

            # --- BEARISH CRT: C2 sweeps C1 high → close longs -----------
            if has_position and self._is_bearish_crt(c1, c2):
                orders.append(self.sell(symbol))

            # --- BULLISH CRT: C2 sweeps C1 low → enter long -------------
            if not has_position and self._is_bullish_crt(c1, c2):
                # Calculate dynamic SL/TP based on C1/C2 structure
                sl_level = c2.low
                # Use C2 close as proxy for C3 open (entry price)
                est_entry = c2.close
                risk = est_entry - sl_level
                if risk > 0 and est_entry > 0:
                    sl_pct = risk / est_entry
                    tp_pct = (self.rr_target * risk) / est_entry
                    orders.append(
                        self.buy(
                            symbol,
                            size_pct=self.size_pct,
                            stop_loss_pct=sl_pct,
                            take_profit_pct=tp_pct,
                        )
                    )

        # Shift window: current becomes previous
        self._prev = self._curr
        self._curr = snap

        return orders

    def _is_bullish_crt(self, c1: CandleSnapshot, c2: CandleSnapshot) -> bool:
        """Bullish CRT: C2 wick sweeps below C1 low, body inside C1, closes green."""
        # C2 wick must have swept below C1 low (liquidity grab)
        if c2.low >= c1.low:
            return False

        # C2 body (open-close) must be inside C1 body (open-close)
        # This is the ICT "inside candle" rule — body inside body
        c1_body_hi = max(c1.open, c1.close)
        c1_body_lo = min(c1.open, c1.close)
        c2_body_hi = max(c2.open, c2.close)
        c2_body_lo = min(c2.open, c2.close)

        if self.require_close_inside:
            if c2_body_hi > c1_body_hi or c2_body_lo < c1_body_lo:
                return False

        # C2 must close green (close > open) — bullish rejection
        if c2.close <= c2.open:
            return False

        # Optional: minimum sweep depth as % of C1 range
        c1_range = c1.high - c1.low
        if c1_range > 0 and self.min_sweep_pct > 0:
            sweep_depth = c1.low - c2.low
            if sweep_depth / c1_range < self.min_sweep_pct:
                return False

        return True

    def _is_bearish_crt(self, c1: CandleSnapshot, c2: CandleSnapshot) -> bool:
        """Bearish CRT: C2 wick sweeps above C1 high, body inside C1, closes red."""
        # C2 wick must have swept above C1 high (liquidity grab)
        if c2.high <= c1.high:
            return False

        # C2 body must be inside C1 body
        c1_body_hi = max(c1.open, c1.close)
        c1_body_lo = min(c1.open, c1.close)
        c2_body_hi = max(c2.open, c2.close)
        c2_body_lo = min(c2.open, c2.close)

        if self.require_close_inside:
            if c2_body_hi > c1_body_hi or c2_body_lo < c1_body_lo:
                return False

        # C2 must close red (close < open) — bearish rejection
        if c2.close >= c2.open:
            return False

        # Optional: minimum sweep depth
        c1_range = c1.high - c1.low
        if c1_range > 0 and self.min_sweep_pct > 0:
            sweep_depth = c2.high - c1.high
            if sweep_depth / c1_range < self.min_sweep_pct:
                return False

        return True

    # ------------------------------------------------------------------
    # Description (used by web_server for response)
    # ------------------------------------------------------------------

    def describe_rules(self) -> str:
        lines = [
            f"Strategy: {self.name}",
            f"  {self.description}",
            "",
            "  ENTER LONG when:",
            "    • C2 low < C1 low (sell-side liquidity sweep)",
            "    • C2 closes back above C1 low (rejection)",
            f"    • SL at C2 low | TP at {self.rr_target}R",
            "",
            "  EXIT (close long) when:",
            "    • C2 high > C1 high (buy-side liquidity sweep)",
            "    • C2 closes back below C1 high (bearish CRT)",
            "",
            f"  Position size: {self.size_pct:.0%} of capital",
        ]
        if self.min_sweep_pct > 0:
            lines.append(f"  Min sweep depth: {self.min_sweep_pct:.0%} of C1 range")
        return "\n".join(lines)
