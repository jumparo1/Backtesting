"""
Core backtesting engine — candle-by-candle loop, no look-ahead bias.

Execution model (from FRAMEWORK.md):
1. Load data for selected coins and timeframe
2. Initialize portfolio with starting balance
3. Iterate candle-by-candle chronologically
4. For each candle: push to indicators -> check stop/TP -> call on_candle() -> queue orders
5. Orders fill at the NEXT candle's open (no look-ahead)
6. Apply slippage and fees on every fill
7. Track all trades in a trade log
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config.settings import (
    DEFAULT_FEE_PCT,
    DEFAULT_SLIPPAGE_PCT,
    DEFAULT_STARTING_CAPITAL,
)
from engine.order import (
    Order,
    OrderSide,
    execute_buy,
    execute_sell,
)
from engine.portfolio import Portfolio
from indicators.base import IndicatorEngine
from metrics.performance import compute_metrics
from strategies.base import Strategy


@dataclass
class BacktestConfig:
    starting_capital: float = DEFAULT_STARTING_CAPITAL
    fee_pct: float = DEFAULT_FEE_PCT
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT


@dataclass
class BacktestResult:
    """Holds everything produced by a backtest run."""

    portfolio: Portfolio
    config: BacktestConfig
    symbol: str
    candle_count: int
    strategy_name: str = ""

    @property
    def trades(self):
        return self.portfolio.trades

    @property
    def equity_curve(self):
        return self.portfolio.equity_curve

    def summary(self) -> dict:
        """Compute full performance metrics via metrics.performance."""
        metrics = compute_metrics(
            trades=self.trades,
            equity_curve=self.equity_curve,
            starting_capital=self.config.starting_capital,
        )
        metrics["symbol"] = self.symbol
        metrics["candles"] = self.candle_count
        metrics["strategy"] = self.strategy_name
        return metrics


def run_backtest(
    strategy: Strategy,
    data: pd.DataFrame,
    symbol: str,
    config: BacktestConfig | None = None,
    params: dict | None = None,
) -> BacktestResult:
    """Run a backtest for a single symbol.

    Args:
        strategy: A Strategy instance.
        data: OHLCV DataFrame with columns [timestamp, open, high, low, close, volume].
        symbol: The ticker symbol (e.g. "BTC").
        config: BacktestConfig (fees, slippage, capital). Uses defaults if None.
        params: Strategy parameters passed to strategy.setup().

    Returns:
        BacktestResult with portfolio, trades, and equity curve.
    """
    config = config or BacktestConfig()
    strategy.setup(params or {})

    portfolio = Portfolio(starting_capital=config.starting_capital)
    indicators = IndicatorEngine()
    pending_orders: list[Order] = []

    rows = data.to_dict("records")

    for i, raw_candle in enumerate(rows):
        candle = {**raw_candle, "symbol": symbol}
        ts = candle.get("timestamp")
        open_price = candle["open"]

        # ----------------------------------------------------------
        # 1. Execute pending orders from the PREVIOUS bar at this
        #    bar's open price (no look-ahead).
        # ----------------------------------------------------------
        for order in pending_orders:
            if order.side == OrderSide.BUY:
                fill = execute_buy(
                    order,
                    fill_price=open_price,
                    available_balance=portfolio.cash,
                    fee_pct=config.fee_pct,
                    slippage_pct=config.slippage_pct,
                )
                if fill:
                    fill.timestamp = ts
                    portfolio.apply_buy(fill, order.stop_loss_pct, order.take_profit_pct)

            elif order.side == OrderSide.SELL:
                pos = portfolio.get_position(order.symbol)
                if pos:
                    fill = execute_sell(
                        symbol=order.symbol,
                        quantity=pos.quantity,
                        fill_price=open_price,
                        fee_pct=config.fee_pct,
                        slippage_pct=config.slippage_pct,
                    )
                    fill.timestamp = ts
                    portfolio.apply_sell(fill)

        pending_orders.clear()

        # ----------------------------------------------------------
        # 2. Check stop-loss / take-profit against this candle's
        #    high and low.
        # ----------------------------------------------------------
        pos = portfolio.get_position(symbol)
        if pos:
            triggered = False
            # Stop-loss: triggered if low <= stop level
            if pos.stop_loss and candle["low"] <= pos.stop_loss:
                fill = execute_sell(
                    symbol=symbol,
                    quantity=pos.quantity,
                    fill_price=pos.stop_loss,
                    fee_pct=config.fee_pct,
                    slippage_pct=config.slippage_pct,
                )
                fill.timestamp = ts
                portfolio.apply_sell(fill)
                triggered = True

            # Take-profit: triggered if high >= TP level
            if not triggered and pos.take_profit and candle["high"] >= pos.take_profit:
                fill = execute_sell(
                    symbol=symbol,
                    quantity=pos.quantity,
                    fill_price=pos.take_profit,
                    fee_pct=config.fee_pct,
                    slippage_pct=config.slippage_pct,
                )
                fill.timestamp = ts
                portfolio.apply_sell(fill)

        # ----------------------------------------------------------
        # 3. Push candle to indicators (strategy sees up to now).
        # ----------------------------------------------------------
        indicators.push(candle)

        # ----------------------------------------------------------
        # 4. Call strategy — collect orders for NEXT bar.
        # ----------------------------------------------------------
        orders = strategy.on_candle(candle, indicators, portfolio)
        if orders:
            if isinstance(orders, Order):
                orders = [orders]
            pending_orders.extend(orders)

        # ----------------------------------------------------------
        # 5. Record equity snapshot.
        # ----------------------------------------------------------
        portfolio.snapshot(ts, {symbol: candle["close"]})

    # Close any remaining open position at last close
    pos = portfolio.get_position(symbol)
    if pos and rows:
        last = rows[-1]
        fill = execute_sell(
            symbol=symbol,
            quantity=pos.quantity,
            fill_price=last["close"],
            fee_pct=config.fee_pct,
            slippage_pct=config.slippage_pct,
        )
        fill.timestamp = last.get("timestamp")
        portfolio.apply_sell(fill)

    return BacktestResult(
        portfolio=portfolio,
        config=config,
        symbol=symbol,
        candle_count=len(rows),
        strategy_name=strategy.name,
    )
