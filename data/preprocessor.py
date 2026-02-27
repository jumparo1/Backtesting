"""
Data preprocessor — clean gaps, forward-fill, validate OHLCV integrity.
"""

import pandas as pd


def clean_ohlcv(df: pd.DataFrame, timeframe: str = "1d") -> pd.DataFrame:
    """Clean and validate an OHLCV DataFrame.

    Steps:
    1. Drop rows with all-NaN price data.
    2. Sort by timestamp.
    3. Remove duplicate timestamps.
    4. Reindex to a complete time grid and forward-fill small gaps.
    5. Drop any remaining rows that still have NaN prices.
    """
    required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        raise ValueError(f"Missing columns: {missing}")

    df = df.copy()

    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Drop rows where all OHLC values are NaN
    df = df.dropna(subset=["open", "high", "low", "close"], how="all")

    # Sort and deduplicate
    df = df.sort_values("timestamp").drop_duplicates(subset="timestamp").reset_index(drop=True)

    if df.empty:
        return df

    # Reindex to fill gaps in the time series
    freq_map = {"1d": "D", "4h": "4h", "1h": "h"}
    freq = freq_map.get(timeframe)
    if freq:
        full_range = pd.date_range(
            start=df["timestamp"].iloc[0],
            end=df["timestamp"].iloc[-1],
            freq=freq,
            tz="UTC",
        )
        df = df.set_index("timestamp").reindex(full_range)
        df.index.name = "timestamp"
        # Forward-fill gaps up to 3 periods
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].ffill(limit=3)
        df["volume"] = df["volume"].fillna(0)
        df = df.dropna(subset=["close"]).reset_index()

    return df


def get_data_summary(df: pd.DataFrame) -> dict:
    """Return a quick summary of the OHLCV data."""
    if df.empty:
        return {"rows": 0}
    return {
        "rows": len(df),
        "start": str(df["timestamp"].iloc[0]),
        "end": str(df["timestamp"].iloc[-1]),
        "missing_close": int(df["close"].isna().sum()),
        "min_close": float(df["close"].min()),
        "max_close": float(df["close"].max()),
    }
