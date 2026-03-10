"""
Spike Exhaustion Reversal Strategy — fade parabolic moves.

Detects unsustainable price spikes (both up and down) and trades
the mean-reversion back toward equilibrium.

SHORT setup (after spike UP):
  • Price gains spike_threshold% within lookback candles
  • Current candle has rejection wick (upper wick > wick_ratio × body)
  • RSI > rsi_overbought
  • Volume on spike candle > vol_multiplier × 20-period average
  • Enter short on close of rejection candle
  • SL at spike high + buffer
  • TP1 at 50% retrace, TP2 at 78.6% retrace

LONG setup (after spike DOWN — mirror):
  • Price drops spike_threshold% within lookback candles
  • Current candle has hammer wick (lower wick > wick_ratio × body)
  • RSI < rsi_oversold
  • Volume on capitulation candle > vol_multiplier × 20-period average
  • Enter long on close of hammer candle
  • SL at spike low - buffer
  • TP at 50% retrace of the drop

Note: Engine is long-only. Bearish spikes (spike up) generate EXIT signals
for open longs. Bullish signals (spike down + hammer) generate ENTRIES.
"""

from __future__ import annotations

from dataclasses import dataclass
from strategies.base import Strategy
from engine.order import Order, OrderSide


class SpikeReversalStrategy(Strategy):
    """Spike Exhaustion Reversal — fade parabolic moves with mean-reversion entries.

    Parameters (via setup()):
        spike_pct       — minimum % move to qualify as a spike (default 0.15 = 15%)
        lookback        — number of candles to measure the spike over (default 5)
        wick_ratio      — min wick-to-body ratio for rejection candle (default 1.5)
        rsi_ob          — RSI overbought threshold for short signals (default 70)
        rsi_os          — RSI oversold threshold for long signals (default 30)
        vol_mult        — volume must be > this × 20-period avg (default 2.0)
        rr_target       — reward:risk ratio for take-profit (default 2.0)
        size_pct        — fraction of capital to deploy (default 0.95)
    """

    def __init__(self):
        super().__init__(
            name="Spike Exhaustion Reversal",
            description=(
                "Fade parabolic spikes — enter long after capitulation drops "
                "(hammer + oversold RSI + volume spike), exit on blow-off tops "
                "(rejection wick + overbought RSI). Mean-reversion to VWAP/EMA."
            ),
        )
        # Tuneable parameters
        self.spike_pct: float = 0.15       # 15% move = spike
        self.lookback: int = 5             # measure spike over N candles
        self.wick_ratio: float = 1.5       # wick must be 1.5x body
        self.rsi_ob: int = 70              # overbought
        self.rsi_os: int = 30              # oversold
        self.vol_mult: float = 2.0         # volume multiplier
        self.rr_target: float = 2.0        # R:R for TP
        self.size_pct: float = 0.95

    def setup(self, params: dict) -> None:
        self.spike_pct = float(params.get("spike_pct", self.spike_pct))
        self.lookback = int(params.get("lookback", self.lookback))
        self.wick_ratio = float(params.get("wick_ratio", self.wick_ratio))
        self.rsi_ob = int(params.get("rsi_ob", self.rsi_ob))
        self.rsi_os = int(params.get("rsi_os", self.rsi_os))
        self.vol_mult = float(params.get("vol_mult", self.vol_mult))
        self.rr_target = float(params.get("rr_target", self.rr_target))
        self.size_pct = float(params.get("size_pct", self.size_pct))

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def on_candle(self, candle: dict, indicators, portfolio) -> list[Order]:
        symbol = candle["symbol"]
        orders: list[Order] = []

        # Need enough history for lookback + volume average
        if indicators.size < max(self.lookback + 1, 21):
            return orders

        cur_close = candle["close"]
        cur_open = candle["open"]
        cur_high = candle["high"]
        cur_low = candle["low"]

        has_position = portfolio.has_position(symbol)

        # Get the close from `lookback` candles ago
        hist = indicators.history
        ref_close = hist[-(self.lookback + 1)]["close"]

        # Calculate spike magnitude
        pct_change = (cur_close - ref_close) / ref_close if ref_close > 0 else 0

        # Current candle body and wicks
        body = abs(cur_close - cur_open)
        upper_wick = cur_high - max(cur_close, cur_open)
        lower_wick = min(cur_close, cur_open) - cur_low
        body_safe = max(body, cur_close * 0.001)  # avoid division by zero

        # RSI
        rsi = indicators.rsi(14)

        # Volume check: current volume vs 20-period average
        vol_ok = False
        if indicators.size >= 21:
            vols = [c.get("volume", 0) for c in hist[-21:-1]]
            avg_vol = sum(vols) / len(vols) if vols else 0
            cur_vol = candle.get("volume", 0)
            vol_ok = avg_vol > 0 and cur_vol > self.vol_mult * avg_vol

        # === BEARISH SPIKE (spike up → exit longs) ===
        if has_position and pct_change > self.spike_pct:
            # Rejection candle: long upper wick
            has_rejection = upper_wick > self.wick_ratio * body_safe
            rsi_hot = rsi is not None and rsi > self.rsi_ob

            if has_rejection and rsi_hot:
                orders.append(self.sell(symbol))

        # === BULLISH SPIKE (spike down → enter long) ===
        if not has_position and pct_change < -self.spike_pct:
            # Hammer candle: long lower wick
            has_hammer = lower_wick > self.wick_ratio * body_safe
            rsi_cold = rsi is not None and rsi < self.rsi_os

            if has_hammer and rsi_cold and vol_ok:
                # SL at the spike low, TP at RR × risk
                sl_level = cur_low
                est_entry = cur_close
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

        return orders

    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------

    def describe_rules(self) -> str:
        return "\n".join([
            f"Strategy: {self.name}",
            f"  {self.description}",
            "",
            "  ENTER LONG (after spike DOWN) when:",
            f"    • Price drops >{self.spike_pct:.0%} in {self.lookback} candles",
            f"    • Hammer candle (lower wick > {self.wick_ratio}x body)",
            f"    • RSI(14) < {self.rsi_os} (oversold)",
            f"    • Volume > {self.vol_mult}x 20-period average",
            f"    • SL at spike low | TP at {self.rr_target}R",
            "",
            "  EXIT (close long on spike UP) when:",
            f"    • Price gains >{self.spike_pct:.0%} in {self.lookback} candles",
            f"    • Rejection candle (upper wick > {self.wick_ratio}x body)",
            f"    • RSI(14) > {self.rsi_ob} (overbought)",
            "",
            f"  Position size: {self.size_pct:.0%} of capital",
        ])
