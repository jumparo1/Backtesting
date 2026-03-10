"""
Mean Reversion Long Strategy — journal-backed support bounce entries.

Reverse-engineered from 30 real trades (sample-data.csv):
  MR Long: 100% WR (8W/0L) — the user's highest-edge setup.

Pattern (what the winning trades share):
  • Price pulls back to support zone (EMA or demand area)
  • RSI dips to oversold territory (confirmation of stretched move)
  • Candle shows rejection from below (hammer / lower wick dominance)
  • Entry on the bounce, SL below support, TP at mean/resistance

Journal keyword signals (appear in winners only):
  "retest", "ema", "reversion", "bounce", "rejection", "support"

Anti-signals (appear in losers only):
  "fomo", "2 candles close" — avoid chasing momentum longs.

Implementation:
  ENTRY when ALL conditions met:
    1. Price pulls back below EMA 21 (mean-reversion opportunity)
    2. RSI(14) < 40 (stretched but not extreme — room to bounce)
    3. Candle shows hammer pattern (lower wick > 1.5x body)
    4. Price bounces: close > EMA 21 (confirmation of support holding)
    OR simplified: price touches/crosses below lower Bollinger and bounces

  EXIT when:
    1. RSI(14) > 65 (approaching overbought — take profit zone)
    2. OR price reaches upper Bollinger band
    3. OR take-profit hit (RR target)

  SL: Below the swing low (hammer low)
  TP: 2R default (can adjust)
"""

from __future__ import annotations

from strategies.base import Strategy
from engine.order import Order, OrderSide


class MRLongStrategy(Strategy):
    """Mean Reversion Long — buy support bounces, sell at mean/resistance.

    Parameters (via setup()):
        ema_period   — EMA period for mean reference (default 21)
        rsi_entry    — RSI must be below this to enter (default 40)
        rsi_exit     — RSI above this triggers exit (default 65)
        wick_ratio   — min lower-wick-to-body ratio for hammer (default 1.5)
        bb_period    — Bollinger Band period (default 20)
        bb_std       — Bollinger Band std devs (default 2.0)
        rr_target    — reward:risk ratio for TP (default 2.0)
        size_pct     — fraction of capital to deploy (default 0.95)
        use_bb       — also check Bollinger lower band touch (default True)
    """

    def __init__(self):
        super().__init__(
            name="MR Long (Journal Edge)",
            description=(
                "Mean Reversion Long — enter on support bounces (EMA pullback "
                "+ oversold RSI + hammer candle), exit at mean/overbought. "
                "Reverse-engineered from trading journal: 100% WR on 8 trades."
            ),
        )
        # Tuneable parameters
        self.ema_period: int = 21
        self.rsi_entry: int = 40
        self.rsi_exit: int = 65
        self.wick_ratio: float = 1.5
        self.bb_period: int = 20
        self.bb_std: float = 2.0
        self.rr_target: float = 2.0
        self.size_pct: float = 0.95
        self.use_bb: bool = True

    def setup(self, params: dict) -> None:
        self.ema_period = int(params.get("ema_period", self.ema_period))
        self.rsi_entry = int(params.get("rsi_entry", self.rsi_entry))
        self.rsi_exit = int(params.get("rsi_exit", self.rsi_exit))
        self.wick_ratio = float(params.get("wick_ratio", self.wick_ratio))
        self.bb_period = int(params.get("bb_period", self.bb_period))
        self.bb_std = float(params.get("bb_std", self.bb_std))
        self.rr_target = float(params.get("rr_target", self.rr_target))
        self.size_pct = float(params.get("size_pct", self.size_pct))
        self.use_bb = bool(params.get("use_bb", self.use_bb))

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def on_candle(self, candle: dict, indicators, portfolio) -> list[Order]:
        symbol = candle["symbol"]
        orders: list[Order] = []

        # Need enough history for indicators
        min_bars = max(self.ema_period, self.bb_period, 15) + 1
        if indicators.size < min_bars:
            return orders

        cur_close = candle["close"]
        cur_open = candle["open"]
        cur_high = candle["high"]
        cur_low = candle["low"]

        has_position = portfolio.has_position(symbol)

        # Indicators
        ema = indicators.ema(self.ema_period)
        rsi = indicators.rsi(14)
        bb = indicators.bollinger(self.bb_period, self.bb_std) if self.use_bb else None

        if ema is None or rsi is None:
            return orders

        # === EXIT CONDITIONS ===
        if has_position:
            should_exit = False

            # RSI overbought exit
            if rsi > self.rsi_exit:
                should_exit = True

            # Upper Bollinger band exit
            if bb is not None:
                upper_bb = bb[0]
                if cur_close >= upper_bb:
                    should_exit = True

            if should_exit:
                orders.append(self.sell(symbol))

        # === ENTRY CONDITIONS ===
        if not has_position:
            # Candle analysis: hammer pattern (lower wick dominance)
            body = abs(cur_close - cur_open)
            lower_wick = min(cur_close, cur_open) - cur_low
            body_safe = max(body, cur_close * 0.001)
            has_hammer = lower_wick > self.wick_ratio * body_safe

            # Must close green (bullish rejection)
            is_green = cur_close > cur_open

            # RSI oversold (stretched for a bounce)
            rsi_ready = rsi < self.rsi_entry

            # Price interacted with mean (EMA pullback)
            # The low dipped to or below EMA, but close is back above
            ema_touch = cur_low <= ema and cur_close > ema

            # Optional: Bollinger lower band touch
            bb_touch = True
            if self.use_bb and bb is not None:
                lower_bb = bb[2]
                # Price touched or went below lower BB
                bb_touch = cur_low <= lower_bb * 1.01  # 1% tolerance

            # ENTRY: EMA pullback + oversold RSI + hammer + green close
            if rsi_ready and has_hammer and is_green and ema_touch:
                # Stronger signal if also touching lower BB
                if not self.use_bb or bb_touch:
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
            "  ENTER LONG when ALL conditions met:",
            f"    • Price low dips to/below EMA({self.ema_period}), close bounces above",
            f"    • RSI(14) < {self.rsi_entry} (oversold / stretched)",
            f"    • Hammer candle (lower wick > {self.wick_ratio}x body)",
            "    • Candle closes green (bullish rejection)",
            f"    • {'Lower BB touch required' if self.use_bb else 'No Bollinger filter'}",
            f"    • SL at candle low | TP at {self.rr_target}R",
            "",
            "  EXIT when:",
            f"    • RSI(14) > {self.rsi_exit} (approaching overbought)",
            f"    • {'OR price hits upper Bollinger Band' if self.use_bb else ''}",
            "    • OR take-profit / stop-loss hit",
            "",
            f"  Position size: {self.size_pct:.0%} of capital",
            "",
            "  Journal edge: MR Long = 100% WR (8W/0L)",
            "  Win keywords: retest, ema, reversion, bounce, rejection, support",
        ])
