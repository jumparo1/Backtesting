"""
Spike Exhaustion Reversal Strategy — fade parabolic moves.

Enhanced with journal-backed filters: RSI + StochRSI + ZC Momentum + Volume.

Detects unsustainable price spikes and trades the mean-reversion back
toward equilibrium. Four-layer confirmation filter reduces false signals.

LONG setup (after spike DOWN):
  • Price drops spike_threshold% within lookback candles
  • Hammer candle (lower wick > wick_ratio × body)
  • RSI < rsi_oversold (momentum stretched)
  • StochRSI %K < srsi_os AND %K crosses above %D (momentum turning up)
  • ROC momentum crosses from negative to positive (ZC bullish)
  • Volume on capitulation candle > vol_multiplier × 20-period average
  • Enter long on close of hammer candle
  • SL at spike low, TP at RR × risk

EXIT (spike UP with position):
  • Price gains spike_threshold% within lookback candles
  • Rejection candle (upper wick > wick_ratio × body)
  • RSI > rsi_overbought
  • StochRSI %K > srsi_ob (momentum exhausted at top)
  • OR ROC momentum crosses from positive to negative (ZC bearish)

Note: Engine is long-only. Bearish spikes generate EXIT signals.
"""

from __future__ import annotations

from strategies.base import Strategy
from engine.order import Order, OrderSide


class SpikeReversalStrategy(Strategy):
    """Spike Exhaustion Reversal — fade parabolic moves with 4-layer confirmation.

    Filters: RSI + StochRSI + Zero-Crossing Momentum + Volume Spike.

    Parameters (via setup()):
        spike_pct       — minimum % move to qualify as a spike (default 0.15 = 15%)
        lookback        — number of candles to measure the spike over (default 5)
        wick_ratio      — min wick-to-body ratio for rejection candle (default 1.5)
        rsi_ob          — RSI overbought threshold for exit (default 70)
        rsi_os          — RSI oversold threshold for entry (default 30)
        srsi_ob         — StochRSI %K overbought threshold (default 80)
        srsi_os         — StochRSI %K oversold threshold (default 20)
        mom_period      — momentum/ROC period for ZC filter (default 10)
        vol_mult        — volume must be > this × 20-period avg (default 2.0)
        rr_target       — reward:risk ratio for take-profit (default 2.0)
        size_pct        — fraction of capital to deploy (default 0.95)
    """

    def __init__(self):
        super().__init__(
            name="Spike Exhaustion Reversal",
            description=(
                "Fade parabolic spikes with 4-layer confirmation: "
                "RSI + StochRSI + ZC Momentum + Volume. "
                "Enter long after capitulation drops, exit on blow-off tops."
            ),
        )
        # Tuneable parameters
        self.spike_pct: float = 0.15       # 15% move = spike
        self.lookback: int = 5             # measure spike over N candles
        self.wick_ratio: float = 1.5       # wick must be 1.5x body
        self.rsi_ob: int = 70              # RSI overbought
        self.rsi_os: int = 30              # RSI oversold
        self.srsi_ob: int = 80             # StochRSI overbought
        self.srsi_os: int = 20             # StochRSI oversold
        self.mom_period: int = 10          # momentum/ROC period
        self.vol_mult: float = 2.0         # volume multiplier
        self.rr_target: float = 2.0        # R:R for TP
        self.size_pct: float = 0.95

    def setup(self, params: dict) -> None:
        self.spike_pct = float(params.get("spike_pct", self.spike_pct))
        self.lookback = int(params.get("lookback", self.lookback))
        self.wick_ratio = float(params.get("wick_ratio", self.wick_ratio))
        self.rsi_ob = int(params.get("rsi_ob", self.rsi_ob))
        self.rsi_os = int(params.get("rsi_os", self.rsi_os))
        self.srsi_ob = int(params.get("srsi_ob", self.srsi_ob))
        self.srsi_os = int(params.get("srsi_os", self.srsi_os))
        self.mom_period = int(params.get("mom_period", self.mom_period))
        self.vol_mult = float(params.get("vol_mult", self.vol_mult))
        self.rr_target = float(params.get("rr_target", self.rr_target))
        self.size_pct = float(params.get("size_pct", self.size_pct))

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def on_candle(self, candle: dict, indicators, portfolio) -> list[Order]:
        symbol = candle["symbol"]
        orders: list[Order] = []

        # Need enough history for all indicators
        # StochRSI needs ~35+ bars, momentum needs mom_period+2
        min_bars = max(self.lookback + 1, 21, 36, self.mom_period + 2)
        if indicators.size < min_bars:
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

        # ── Indicator stack ──────────────────────────────────────────
        rsi = indicators.rsi(14)
        srsi = indicators.stoch_rsi(14, 14, 3, 3)  # (%K, %D)
        mom_cur = indicators.momentum(self.mom_period)
        mom_prev = indicators.momentum_prev(self.mom_period)

        # Volume check: current volume vs 20-period average
        vol_ok = False
        if indicators.size >= 21:
            vols = [c.get("volume", 0) for c in hist[-21:-1]]
            avg_vol = sum(vols) / len(vols) if vols else 0
            cur_vol = candle.get("volume", 0)
            vol_ok = avg_vol > 0 and cur_vol > self.vol_mult * avg_vol

        # ── BEARISH SPIKE (spike up → exit longs) ═══════════════════
        if has_position and pct_change > self.spike_pct:
            # Rejection candle: long upper wick
            has_rejection = upper_wick > self.wick_ratio * body_safe
            rsi_hot = rsi is not None and rsi > self.rsi_ob

            # StochRSI overbought confirmation
            srsi_hot = srsi is not None and srsi[0] > self.srsi_ob

            # ZC momentum turning negative (bearish crossover)
            mom_turning_down = (
                mom_cur is not None and mom_prev is not None
                and mom_cur < mom_prev  # momentum decelerating
            )

            # Exit requires: rejection wick + RSI hot + (SRSI hot OR momentum turning)
            if has_rejection and rsi_hot and (srsi_hot or mom_turning_down):
                orders.append(self.sell(symbol))

        # ── BULLISH SPIKE (spike down → enter long) ═════════════════
        if not has_position and pct_change < -self.spike_pct:
            # Hammer candle: long lower wick
            has_hammer = lower_wick > self.wick_ratio * body_safe
            rsi_cold = rsi is not None and rsi < self.rsi_os

            # StochRSI oversold + %K crossing above %D (momentum turning up)
            srsi_cold = False
            srsi_cross_up = False
            if srsi is not None:
                k, d = srsi
                srsi_cold = k < self.srsi_os
                srsi_cross_up = k > d  # %K above %D = bullish momentum shift

            # ZC momentum filter: momentum crossing from negative toward positive
            # After a spike down, momentum is very negative. We want it to be
            # starting to recover (current > previous = decelerating selling)
            mom_recovering = (
                mom_cur is not None and mom_prev is not None
                and mom_cur > mom_prev  # selling pressure easing
            )

            # ENTRY requires ALL:
            #   1. Hammer candle
            #   2. RSI oversold
            #   3. StochRSI oversold with bullish crossover (%K > %D)
            #   4. Momentum recovering (ZC filter)
            #   5. Volume spike
            if (has_hammer and rsi_cold and vol_ok
                    and srsi_cold and srsi_cross_up
                    and mom_recovering):
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
            "  ENTER LONG (after spike DOWN) — ALL required:",
            f"    1. Price drops >{self.spike_pct:.0%} in {self.lookback} candles",
            f"    2. Hammer candle (lower wick > {self.wick_ratio}x body)",
            f"    3. RSI(14) < {self.rsi_os} (oversold)",
            f"    4. StochRSI %K < {self.srsi_os} AND %K > %D (bullish crossover)",
            f"    5. Momentum({self.mom_period}) recovering (ZC filter: current > previous)",
            f"    6. Volume > {self.vol_mult}x 20-period average",
            f"    • SL at spike low | TP at {self.rr_target}R",
            "",
            "  EXIT (close long on spike UP) when:",
            f"    • Price gains >{self.spike_pct:.0%} in {self.lookback} candles",
            f"    • Rejection candle (upper wick > {self.wick_ratio}x body)",
            f"    • RSI(14) > {self.rsi_ob} (overbought)",
            f"    • StochRSI %K > {self.srsi_ob} OR momentum decelerating",
            "",
            f"  Position size: {self.size_pct:.0%} of capital",
        ])
