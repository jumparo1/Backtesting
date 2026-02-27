"""
Data fetcher for historical OHLCV data.

Strategy:
- CoinGecko: used for top coin list and as OHLCV fallback.
- Binance (via ccxt): primary OHLCV source — free, no key needed,
  has good historical depth for most top coins.
"""

import time
from datetime import datetime

import ccxt
import pandas as pd
import requests

from config.settings import (
    COINGECKO_RATE_LIMIT,
    BINANCE_RATE_LIMIT,
    START_DATE,
    END_DATE,
)

# ---------------------------------------------------------------------------
# Binance fetcher (primary)
# ---------------------------------------------------------------------------

_binance = ccxt.binance({"enableRateLimit": True})

# Map common timeframe strings to ccxt format
TIMEFRAME_MAP = {
    "1d": "1d",
    "4h": "4h",
    "1h": "1h",
}


def _symbol_to_binance_pair(symbol: str) -> str:
    """Convert a symbol like 'BTC' to 'BTC/USDT'."""
    return f"{symbol}/USDT"


def fetch_ohlcv_binance(
    symbol: str,
    timeframe: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame | None:
    """Fetch OHLCV from Binance via ccxt. Returns DataFrame or None on failure."""
    start = start or START_DATE
    end = end or END_DATE
    pair = _symbol_to_binance_pair(symbol)
    tf = TIMEFRAME_MAP.get(timeframe, timeframe)
    since = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    all_candles = []
    try:
        while since < end_ms:
            candles = _binance.fetch_ohlcv(pair, tf, since=since, limit=1000)
            if not candles:
                break
            all_candles.extend(candles)
            # Move past the last candle timestamp
            since = candles[-1][0] + 1
            time.sleep(BINANCE_RATE_LIMIT)
    except ccxt.BadSymbol:
        return None
    except ccxt.BaseError as e:
        print(f"  Binance error for {symbol}: {e}")
        return None

    if not all_candles:
        return None

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    # Filter to date range
    df = df[(df["timestamp"] >= pd.Timestamp(start, tz="UTC")) & (df["timestamp"] <= pd.Timestamp(end, tz="UTC"))]
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# CoinGecko fetcher (fallback)
# ---------------------------------------------------------------------------

COINGECKO_OHLC_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
COINGECKO_MARKET_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"


def fetch_ohlcv_coingecko(
    coin_id: str,
    symbol: str,
    timeframe: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame | None:
    """Fetch OHLCV from CoinGecko market_chart/range endpoint.

    Note: CoinGecko free tier returns daily granularity for ranges > 90 days.
    For sub-day timeframes this fallback won't help — only daily is reliable.
    """
    start = start or START_DATE
    end = end or END_DATE

    params = {
        "vs_currency": "usd",
        "from": int(start.timestamp()),
        "to": int(end.timestamp()),
    }

    try:
        resp = requests.get(
            COINGECKO_MARKET_CHART_URL.format(coin_id=coin_id),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  CoinGecko error for {symbol}: {e}")
        return None

    prices = data.get("prices", [])
    volumes = data.get("total_volumes", [])
    if not prices:
        return None

    df_price = pd.DataFrame(prices, columns=["timestamp", "close"])
    df_vol = pd.DataFrame(volumes, columns=["timestamp", "volume"])
    df = df_price.merge(df_vol, on="timestamp", how="left")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    # CoinGecko market_chart doesn't give OHLC for range, so approximate
    df["open"] = df["close"]
    df["high"] = df["close"]
    df["low"] = df["close"]
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    time.sleep(COINGECKO_RATE_LIMIT)
    return df


# ---------------------------------------------------------------------------
# TradingView fetcher (fallback #1 — via tvdatafeed)
# ---------------------------------------------------------------------------

# Map timeframes to tvdatafeed intervals
_TV_TIMEFRAME_MAP: dict | None = None


def _get_tv_intervals():
    """Lazy-load tvdatafeed intervals to avoid import errors if not installed."""
    global _TV_TIMEFRAME_MAP
    if _TV_TIMEFRAME_MAP is None:
        try:
            from tvDatafeed import Interval
            _TV_TIMEFRAME_MAP = {
                "1d": Interval.in_daily,
                "4h": Interval.in_4_hour,
                "1h": Interval.in_1_hour,
            }
        except ImportError:
            _TV_TIMEFRAME_MAP = {}
    return _TV_TIMEFRAME_MAP


# Symbol mapping for coins that use different tickers on TradingView.
# Use native exchanges for volume data (CRYPTO exchange has zero volume).
_TV_SYMBOL_MAP = {
    "HYPE": ("HYPEUSD",  "COINBASE"),
    "KAS":  ("KASUSDT",  "BYBIT"),       # 902 bars w/ volume
    "PI":   ("PIUSD",    "CRYPTO"),
    "MNT":  ("MNTUSDT",  "BYBIT"),       # 954 bars w/ volume
    "CRO":  ("CROUSDT",  "OKX"),         # 2436 bars w/ volume
    "LEO":  ("LEOUSD",   "BITFINEX"),    # 2473 bars w/ volume
    "BGB":  ("BGBUSD",   "CRYPTO"),
    "OKB":  ("OKBUSDT",  "OKX"),         # 2759 bars w/ volume
    "XDC":  ("XDCUSD",   "CRYPTO"),
    "FLR":  ("FLRUSD",   "CRYPTO"),
    "HTX":  ("HTXUSD",   "CRYPTO"),
    "KCS":  ("KCSUSDT",  "KUCOIN"),      # 3052 bars w/ volume
    "WBT":  ("WBTUSD",   "CRYPTO"),
}

_tv_client = None


def _get_tv_client():
    """Get or create a TvDatafeed client (singleton).

    Uses TV_USERNAME / TV_PASSWORD from .env if available for deeper
    history and more symbols. Falls back to anonymous access.
    """
    global _tv_client
    if _tv_client is None:
        try:
            from tvDatafeed import TvDatafeed
        except ImportError:
            return None

        import os
        from pathlib import Path

        # Load .env if not already in environment
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

        tv_user = os.environ.get("TV_USERNAME", "").strip()
        tv_pass = os.environ.get("TV_PASSWORD", "").strip()

        if tv_user and tv_pass:
            try:
                _tv_client = TvDatafeed(username=tv_user, password=tv_pass)
                print("  TradingView: authenticated session")
            except Exception:
                _tv_client = TvDatafeed()
        else:
            _tv_client = TvDatafeed()
    return _tv_client


def fetch_ohlcv_tradingview(
    symbol: str,
    timeframe: str = "1d",
) -> pd.DataFrame | None:
    """Fetch OHLCV from TradingView via tvdatafeed.

    Tries the symbol map first, then falls back to BINANCE:SYMBOLUSDT.
    Returns DataFrame or None on failure.
    """
    intervals = _get_tv_intervals()
    if not intervals:
        return None  # tvdatafeed not installed

    tv = _get_tv_client()
    if tv is None:
        return None

    interval = intervals.get(timeframe)
    if interval is None:
        return None

    # Try mapped symbol first
    if symbol in _TV_SYMBOL_MAP:
        tv_sym, exchange = _TV_SYMBOL_MAP[symbol]
    else:
        # Default: try BINANCE:SYMBOLUSDT, then CRYPTO:SYMBOLUSD
        tv_sym = f"{symbol}USDT"
        exchange = "BINANCE"

    attempts = [(tv_sym, exchange)]
    # Also try CRYPTO:SYMBOLUSD as fallback
    if exchange != "CRYPTO":
        attempts.append((f"{symbol}USD", "CRYPTO"))

    for sym, exch in attempts:
        try:
            data = tv.get_hist(symbol=sym, exchange=exch, interval=interval, n_bars=5000)
            if data is not None and len(data) > 0:
                df = data.reset_index()
                df = df.rename(columns={"datetime": "timestamp"})
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                df = df[["timestamp", "open", "high", "low", "close", "volume"]]
                df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
                return df
        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Unified fetcher
# ---------------------------------------------------------------------------


def fetch_ohlcv(
    symbol: str,
    coin_id: str,
    timeframe: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame | None:
    """Fetch OHLCV data. Tries Binance → TradingView → CoinGecko.

    Args:
        symbol: Ticker symbol (e.g. "BTC", "ETH").
        coin_id: CoinGecko coin ID (e.g. "bitcoin", "ethereum").
        timeframe: Candle timeframe ("1d", "4h", "1h").
        start: Start datetime (default: 5y ago).
        end: End datetime (default: now).

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume]
        or None if all sources fail.
    """
    # Try Binance first
    df = fetch_ohlcv_binance(symbol, timeframe, start, end)
    if df is not None and len(df) > 0:
        return df

    # Fall back to TradingView
    print(f"  Binance miss for {symbol}, trying TradingView...")
    df = fetch_ohlcv_tradingview(symbol, timeframe)
    if df is not None and len(df) > 0:
        return df

    # Fall back to CoinGecko
    print(f"  TradingView miss for {symbol}, trying CoinGecko...")
    df = fetch_ohlcv_coingecko(coin_id, symbol, timeframe, start, end)
    return df
