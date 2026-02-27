from pathlib import Path

import pandas as pd

from config.settings import CACHE_DIR


def _parquet_path(symbol: str, timeframe: str) -> Path:
    """Return the cache file path for a given symbol and timeframe."""
    return CACHE_DIR / f"{symbol}_{timeframe}.parquet"


def save_ohlcv(df: pd.DataFrame, symbol: str, timeframe: str) -> None:
    """Save OHLCV DataFrame to a Parquet file."""
    path = _parquet_path(symbol, timeframe)
    df.to_parquet(path, index=False)


def load_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Load OHLCV DataFrame from Parquet. Returns None if file doesn't exist."""
    path = _parquet_path(symbol, timeframe)
    if not path.exists():
        return None
    return pd.read_parquet(path)


def has_cached_data(symbol: str, timeframe: str) -> bool:
    """Check if cached data exists for a symbol/timeframe."""
    return _parquet_path(symbol, timeframe).exists()


def list_cached_symbols(timeframe: str) -> list[str]:
    """List all symbols that have cached data for a given timeframe."""
    suffix = f"_{timeframe}.parquet"
    return [
        f.stem.replace(suffix.replace(".parquet", ""), "")
        for f in CACHE_DIR.glob(f"*{suffix}")
    ]
