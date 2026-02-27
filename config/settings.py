from pathlib import Path
from datetime import datetime, timedelta

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Ensure directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Date range
END_DATE = datetime.utcnow()
START_DATE = END_DATE - timedelta(days=5 * 365)

# Default timeframe
DEFAULT_TIMEFRAME = "1d"

# Number of top coins to fetch
TOP_N_COINS = 100

# Coins to exclude from the top-N list (CoinGecko IDs).
# Covers stablecoins, gold-pegged, wrapped fiat, RWA fund tokens, and
# anything that isn't a real tradeable altcoin.
EXCLUDED_COIN_IDS = {
    # USD stablecoins
    "tether", "usd-coin", "dai", "trueusd", "paxos-standard",
    "binance-usd", "frax", "usdd", "gemini-dollar", "paypal-usd",
    "first-digital-usd", "ethena-usde", "usual-usd", "gho",
    "ripple-usd", "tether-eurt", "eurc", "usd1-wlfi", "usdai",
    "usdtb", "binance-staked-sol",
    # Gold / commodity pegged
    "tether-gold", "pax-gold",
    # Wrapped / bridged duplicates
    "wrapped-bitcoin", "wrapped-steth", "wrapped-eeth",
    "binance-peg-ethereum",
    # RWA fund tokens
    "ondo-us-dollar-yield", "backed-fi", "hashnote-usyc",
    "mountain-protocol-usdm",
}

# Backward compat alias
STABLECOIN_IDS = EXCLUDED_COIN_IDS

# Symbols to skip when cleaning cached data (not real tradeable altcoins)
EXCLUDED_SYMBOLS = {
    # Stablecoins / pegged
    "TUSD", "EURC", "RLUSD", "USD1", "USDAI", "USDTB", "BFUSD", "GHO",
    # Gold-pegged
    "PAXG", "XAUT",
    # Micro memes / junk / unfetchable
    "PIPPIN", "KITE", "PUMP", "RAIN", "WLFI",
    # Exchange-exclusive / tiny cap
    "FTN", "BDX",
}

# API rate limits
COINGECKO_RATE_LIMIT = 0.7  # seconds between requests (free tier ~30/min)
BINANCE_RATE_LIMIT = 0.1

# Backtesting defaults
DEFAULT_STARTING_CAPITAL = 10_000.0
DEFAULT_FEE_PCT = 0.001        # 0.1%
DEFAULT_SLIPPAGE_PCT = 0.001   # 0.1%
