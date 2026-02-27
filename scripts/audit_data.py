#!/usr/bin/env python3
"""
Audit cached OHLCV data for quality issues.

Checks each parquet file for:
  - Row count (flags <90 days)
  - Date range coverage
  - Gaps >2 days (missing candles)
  - Zero-volume candles (CoinGecko fallback artifact)
  - Whether symbol is in the excluded list

Usage:
    python scripts/audit_data.py             # Full audit
    python scripts/audit_data.py --clean     # Delete excluded/junk parquet files
    python scripts/audit_data.py --min-rows 365  # Flag coins with <365 rows
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from config.settings import CACHE_DIR, EXCLUDED_SYMBOLS


def audit_parquet(path: Path) -> dict:
    """Audit a single parquet file and return quality metrics."""
    sym = path.stem.replace("_1d", "")
    result = {
        "symbol": sym,
        "file": path.name,
        "excluded": sym in EXCLUDED_SYMBOLS,
    }

    try:
        df = pd.read_parquet(path)
    except Exception as e:
        result["error"] = str(e)
        return result

    rows = len(df)
    result["rows"] = rows

    if rows == 0:
        result["start"] = None
        result["end"] = None
        result["gaps"] = 0
        result["zero_vol"] = 0
        result["zero_vol_pct"] = 0
        return result

    result["start"] = str(df["timestamp"].min())[:10]
    result["end"] = str(df["timestamp"].max())[:10]

    # Gaps > 2 days
    diffs = df["timestamp"].diff().dropna()
    result["gaps"] = int((diffs > pd.Timedelta(days=2)).sum())

    # Zero-volume candles
    zv = int((df["volume"] == 0).sum())
    result["zero_vol"] = zv
    result["zero_vol_pct"] = round(100 * zv / rows, 1)

    return result


def main():
    parser = argparse.ArgumentParser(description="Audit cached OHLCV data quality")
    parser.add_argument("--clean", action="store_true", help="Delete excluded symbol parquet files")
    parser.add_argument("--min-rows", type=int, default=90, help="Minimum rows to be considered valid (default: 90)")
    args = parser.parse_args()

    files = sorted(CACHE_DIR.glob("*_1d.parquet"))
    if not files:
        print("No parquet files found in", CACHE_DIR)
        return 1

    results = [audit_parquet(f) for f in files]

    # Print results sorted by row count
    results.sort(key=lambda r: r.get("rows", 0))

    hdr = f"{'Symbol':<10} {'Rows':>6} {'Start':<12} {'End':<12} {'Gaps>2d':>8} {'ZeroVol':>8} {'ZV%':>6} {'Status'}"
    print(hdr)
    print("-" * len(hdr))

    excluded_files = []
    short_files = []
    bad_quality = []
    good = []

    for r in results:
        sym = r["symbol"]
        rows = r.get("rows", 0)
        start = r.get("start", "N/A") or "N/A"
        end = r.get("end", "N/A") or "N/A"
        gaps = r.get("gaps", 0)
        zv = r.get("zero_vol", 0)
        zvp = r.get("zero_vol_pct", 0)

        # Determine status
        if r.get("excluded"):
            status = "EXCLUDED"
            excluded_files.append(r)
        elif r.get("error"):
            status = f"ERROR: {r['error']}"
        elif rows < args.min_rows:
            status = "SHORT"
            short_files.append(r)
        elif zvp > 90:
            status = "NO VOLUME"
            bad_quality.append(r)
        elif gaps > 5:
            status = "GAPPY"
            bad_quality.append(r)
        else:
            status = "OK"
            good.append(r)

        print(f"{sym:<10} {rows:>6} {start:<12} {end:<12} {gaps:>8} {zv:>8} {zvp:>5.1f}% {status}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Total files:      {len(results)}")
    print(f"  Good:           {len(good)}")
    print(f"  Excluded:       {len(excluded_files)} (stablecoins/gold/junk)")
    print(f"  Short (<{args.min_rows}d):   {len(short_files)}")
    print(f"  Bad quality:    {len(bad_quality)} (no volume or gappy)")

    if excluded_files:
        print(f"\nExcluded symbols: {', '.join(r['symbol'] for r in excluded_files)}")
    if short_files:
        print(f"Short symbols:    {', '.join(r['symbol'] for r in short_files)}")
    if bad_quality:
        print(f"Bad quality:      {', '.join(r['symbol'] for r in bad_quality)}")

    # Clean mode — delete excluded files
    if args.clean:
        to_delete = [r for r in results if r.get("excluded")]
        if not to_delete:
            print("\nNo excluded files to delete.")
        else:
            print(f"\nDeleting {len(to_delete)} excluded parquet files...")
            for r in to_delete:
                path = CACHE_DIR / r["file"]
                path.unlink()
                print(f"  Deleted {r['file']}")
            print("Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
