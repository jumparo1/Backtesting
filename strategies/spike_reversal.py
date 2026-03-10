"""
Spike Exhaustion Reversal Strategy — fade parabolic moves.

Enhanced with journal-backed filters: RSI + StochRSI + ZC Momentum + Volume.

Detects unsustainable price spikes and trades the mean-reversion back
toward equilibrium. Uses a confirmation scoring system — spike + wick pattern
is required, then at least 2 of 4 confirmation layers must align.

LONG setup (after spike DOWN):
  Required:
    • Price drops spike_threshold% within lookback candles
    • Candle shows rejection (hammer wick OR green close)
  Confirmation layers (need min_confirms of 4):
    1. RSI(14) < rsi_os (oversold)
    2. StochRSI %K < srsi_os with %K > %D (bullish crossover)
    3. Momentum(ROC) recovering (current > previous)
    4. Volume > vol_mult × 20-period average

EXIT (spike UP with position):
  Required:
    • Price gains spike_threshold% within lookback candles
  Confirmation (need 2 of 4):
    1. Rejection wick (upper wick > wick_ratio × body)
    2. RSI > rsi_ob (overbought)
    3. StochRSI %K > srsi_ob
    4. Momentum decelerating

Note: Engine is long-only. Bearish spikes generate EXIT signals.
"""

from __future__ import annotations

from strategies.base import Strategy
from engine.order import Order, OrderSide


class SpikeReversalStrategy(Strategy):
    """Spike Exhaustion Reversal — fade parabolic moves with scored confirmation.

    Core: spike detection + wick pattern (always required).
    Confirmation: at least min_confirms of 4 layers must agree.
    Layers: RSI, StochRSI, ZC Momentum, Volume.

    Parameters (via setup()):
        spike_pct       — minimum % move to qualify as a spike (default 0.05 = 5%)
        lookback        — number of candles to measure the spike over (default 5)
        wick_ratio      — min wick-to-body ratio for strong rejection (default 1.5)
        rsi_ob          — RSI overbought threshold for exit (default 65)
        rsi_os          — RSI oversold threshold for entry (default 40)
        srsi_ob         — StochRSI %K overbought threshold (default 75)
        srsi_os         — StochRSI %K oversold threshold (default 30)
        mom_period      — momentum/ROC period for ZC filter (default 10)
        vol_mult        — volume must be > this × 20-period avg (default 1.5)
        min_confirms    — minimum confirmation layers needed (default 2 of 4)
        rr_target       — reward:risk ratio for take-profit (default 2.0)
        size_pct        — fraction of capital to deploy (default 0.95)
    """

    def __init__(self):
        super().__init__(
            name="Spike Exhaustion Reversal",
            description=(
                "Fade parabolic spikes with scored confirmation: "
                "RSI + StochRSI + ZC Momentum + Volume (need 2 of 4). "
                "Enter long after sharp drops, exit on blow-off tops."
            ),
        )
        # Tuneable parameters — calibrated for daily candles
        self.spike_pct: float = 0.03       # 3% move = spike (~99 events/year on BTC)
        self.lookback: int = 5             # measure spike over N candles
        self.wick_ratio: float = 1.5       # wick must be 1.5x body for "strong" signal
        self.rsi_ob: int = 65              # overbought (relaxed from 70)
        self.rsi_os: int = 40              # oversold (relaxed from 30)
        self.srsi_ob: int = 75             # StochRSI overbought
        self.srsi_os: int = 30             # StochRSI oversold (relaxed from 20)
        self.mom_period: int = 10          # momentum/ROC period
        self.vol_mult: float = 1.5         # volume multiplier (relaxed from 2.0)
        self.min_confirms: int = 2         # need at least 2 of 4 confirmations
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
        self.min_confirms = int(params.get("min_confirms", self.min_confirms))
        self.rr_target = float(params.get("rr_target", self.rr_target))
        self.size_pct = float(params.get("size_pct", self.size_pct))

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def on_candle(self, candle: dict, indicators, portfolio) -> list[Order]:
        symbol = candle["symbol"]
        orders: list[Order] = []

        # Need enough history for all indicators
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

        # Volume check
        vol_ok = False
        if indicators.size >= 21:
            vols = [c.get("volume", 0) for c in hist[-21:-1]]
            avg_vol = sum(vols) / len(vols) if vols else 0
            cur_vol = candle.get("volume", 0)
            vol_ok = avg_vol > 0 and cur_vol > self.vol_mult * avg_vol

        # ── BEARISH SPIKE (spike up → exit longs) ═══════════════════
        if has_position and pct_change > self.spike_pct:
            exit_score = 0

            # Layer 1: Rejection wick
            if upper_wick > self.wick_ratio * body_safe:
                exit_score += 1

            # Layer 2: RSI overbought
            if rsi is not None and rsi > self.rsi_ob:
                exit_score += 1

            # Layer 3: StochRSI overbought
            if srsi is not None and srsi[0] > self.srsi_ob:
                exit_score += 1

            # Layer 4: Momentum decelerating
            if (mom_cur is not None and mom_prev is not None
                    and mom_cur < mom_prev):
                exit_score += 1

            # Exit if spike detected + enough confirmation
            if exit_score >= self.min_confirms:
                orders.append(self.sell(symbol))

        # ── BULLISH SPIKE (spike down → enter long) ═════════════════
        if not has_position and pct_change < -self.spike_pct:
            # Core requirement: candle shows some rejection from below
            # Either a hammer wick OR a green close (bullish rejection)
            has_hammer = lower_wick > self.wick_ratio * body_safe
            is_green = cur_close > cur_open
            has_rejection = has_hammer or is_green

            if not has_rejection:
                return orders

            # Score confirmation layers (need min_confirms of 4)
            entry_score = 0

            # Layer 1: RSI oversold
            if rsi is not None and rsi < self.rsi_os:
                entry_score += 1

            # Layer 2: StochRSI oversold + bullish crossover (%K > %D)
            if srsi is not None:
                k, d = srsi
                if k < self.srsi_os and k > d:
                    entry_score += 1

            # Layer 3: Momentum recovering (selling pressure easing)
            if (mom_cur is not None and mom_prev is not None
                    and mom_cur > mom_prev):
                entry_score += 1

            # Layer 4: Volume spike (capitulation volume)
            if vol_ok:
                entry_score += 1

            if entry_score >= self.min_confirms:
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
            f"  ENTER LONG (after spike DOWN >{self.spike_pct:.0%} in {self.lookback} candles):",
            "    Required: candle rejection (hammer wick OR green close)",
            f"    Then {self.min_confirms} of 4 confirmations must align:",
            f"      1. RSI(14) < {self.rsi_os} (oversold)",
            f"      2. StochRSI %K < {self.srsi_os} + %K > %D (bullish cross)",
            f"      3. Momentum({self.mom_period}) recovering (ZC filter)",
            f"      4. Volume > {self.vol_mult}x 20-period average",
            f"    • SL at spike low | TP at {self.rr_target}R",
            "",
            f"  EXIT (spike UP >{self.spike_pct:.0%} in {self.lookback} candles):",
            f"    {self.min_confirms} of 4 confirmations:",
            f"      1. Rejection wick (upper wick > {self.wick_ratio}x body)",
            f"      2. RSI(14) > {self.rsi_ob} (overbought)",
            f"      3. StochRSI %K > {self.srsi_ob}",
            "      4. Momentum decelerating",
            "",
            f"  Position size: {self.size_pct:.0%} of capital",
        ])
