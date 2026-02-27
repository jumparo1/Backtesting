#!/usr/bin/env python3
"""
Fetch historical OHLCV data for the top 100 altcoins.

Usage:
    python fetch_data.py                # Fetch all, skip already cached
    python fetch_data.py --refresh      # Re-fetch everything
    python fetch_data.py --coins 10     # Only top 10
    python fetch_data.py --timeframe 4h # Use 4h candles instead of 1d
"""

import argparse
import sys
import time

from config.coins import get_coin_list
from config.settings import DEFAULT_TIMEFRAME, TOP_N_COINS
from data.fetcher import fetch_ohlcv
from data.preprocessor import clean_ohlcv, get_data_summary
from data.storage import has_cached_data, save_ohlcv


def main():
    parser = argparse.ArgumentParser(description="Fetch OHLCV data for top altcoins")
    parser.add_argument("--coins", type=int, default=TOP_N_COINS, help="Number of top coins to fetch")
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="Candle timeframe (1d, 4h, 1h)")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch even if cached")
    parser.add_argument("--refresh-list", action="store_true", help="Re-fetch coin list from CoinGecko")
    args = parser.parse_args()

    # Step 1: Get coin list
    print(f"=== Fetching top {args.coins} altcoin list ===")
    coins = get_coin_list(force_refresh=args.refresh_list)
    coins = coins[: args.coins]
    print(f"Got {len(coins)} coins\n")

    # Step 2: Download OHLCV for each coin
    success = 0
    skipped = 0
    failed = []

    for i, coin in enumerate(coins, 1):
        symbol = coin["symbol"]
        coin_id = coin["id"]
        tag = f"[{i}/{len(coins)}]"

        if not args.refresh and has_cached_data(symbol, args.timeframe):
            print(f"{tag} {symbol} — cached, skipping")
            skipped += 1
            continue

        print(f"{tag} {symbol} ({coin_id}) — fetching...", end=" ", flush=True)

        df = fetch_ohlcv(symbol, coin_id, timeframe=args.timeframe)

        if df is None or df.empty:
            print("FAILED (no data)")
            failed.append(symbol)
            continue

        df = clean_ohlcv(df, timeframe=args.timeframe)
        save_ohlcv(df, symbol, args.timeframe)
        summary = get_data_summary(df)
        print(f"OK — {summary['rows']} candles, {summary['start'][:10]} to {summary['end'][:10]}")
        success += 1

    # Summary
    print(f"\n=== Done ===")
    print(f"  Fetched:  {success}")
    print(f"  Skipped:  {skipped} (already cached)")
    print(f"  Failed:   {len(failed)}")
    if failed:
        print(f"  Failed coins: {', '.join(failed)}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
