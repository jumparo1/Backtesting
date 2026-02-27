import json
import time
from pathlib import Path

import requests

from config.settings import (
    CACHE_DIR,
    COINGECKO_RATE_LIMIT,
    EXCLUDED_COIN_IDS,
    TOP_N_COINS,
)

COIN_LIST_FILE = CACHE_DIR / "top_coins.json"

COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Hardcoded fallback: ~125 real tradeable altcoins by mcap (Feb 2026).
# No stablecoins, gold-pegged, RWA fund tokens, or junk.
# Format: (coingecko_id, symbol, name)
_FALLBACK_TOP_COINS = [
    # Top 10
    ("bitcoin", "BTC", "Bitcoin"),
    ("ethereum", "ETH", "Ethereum"),
    ("ripple", "XRP", "XRP"),
    ("binancecoin", "BNB", "BNB"),
    ("solana", "SOL", "Solana"),
    ("dogecoin", "DOGE", "Dogecoin"),
    ("cardano", "ADA", "Cardano"),
    ("tron", "TRX", "TRON"),
    ("the-open-network", "TON", "Toncoin"),
    ("chainlink", "LINK", "Chainlink"),
    # 11-20
    ("avalanche-2", "AVAX", "Avalanche"),
    ("sui", "SUI", "Sui"),
    ("stellar", "XLM", "Stellar"),
    ("shiba-inu", "SHIB", "Shiba Inu"),
    ("hedera-hashgraph", "HBAR", "Hedera"),
    ("polkadot", "DOT", "Polkadot"),
    ("bitcoin-cash", "BCH", "Bitcoin Cash"),
    ("hyperliquid", "HYPE", "Hyperliquid"),
    ("litecoin", "LTC", "Litecoin"),
    ("uniswap", "UNI", "Uniswap"),
    # 21-30
    ("leo-token", "LEO", "LEO Token"),
    ("near", "NEAR", "NEAR Protocol"),
    ("aptos", "APT", "Aptos"),
    ("internet-computer", "ICP", "Internet Computer"),
    ("aave", "AAVE", "Aave"),
    ("pepe", "PEPE", "Pepe"),
    ("ethereum-classic", "ETC", "Ethereum Classic"),
    ("render-token", "RENDER", "Render"),
    ("monero", "XMR", "Monero"),
    ("cosmos", "ATOM", "Cosmos"),
    # 31-40
    ("mantle", "MNT", "Mantle"),
    ("crypto-com-chain", "CRO", "Cronos"),
    ("vechain", "VET", "VeChain"),
    ("filecoin", "FIL", "Filecoin"),
    ("arbitrum", "ARB", "Arbitrum"),
    ("kaspa", "KAS", "Kaspa"),
    ("okb", "OKB", "OKB"),
    ("celestia", "TIA", "Celestia"),
    ("fantom", "FTM", "Fantom"),
    ("algorand", "ALGO", "Algorand"),
    # 41-50
    ("bonk", "BONK", "Bonk"),
    ("optimism", "OP", "Optimism"),
    ("injective-protocol", "INJ", "Injective"),
    ("stacks", "STX", "Stacks"),
    ("immutable-x", "IMX", "Immutable"),
    ("theta-token", "THETA", "Theta Network"),
    ("sei-network", "SEI", "Sei"),
    ("the-graph", "GRT", "The Graph"),
    ("floki", "FLOKI", "FLOKI"),
    ("maker", "MKR", "Maker"),
    # 51-60
    ("matic-network", "POL", "Polygon"),
    ("pyth-network", "PYTH", "Pyth Network"),
    ("worldcoin-wld", "WLD", "Worldcoin"),
    ("jupiter-exchange-solana", "JUP", "Jupiter"),
    ("gala", "GALA", "Gala"),
    ("lido-dao", "LDO", "Lido DAO"),
    ("flow", "FLOW", "Flow"),
    ("the-sandbox", "SAND", "The Sandbox"),
    ("axie-infinity", "AXS", "Axie Infinity"),
    ("decentraland", "MANA", "Decentraland"),
    # 61-70
    ("tezos", "XTZ", "Tezos"),
    ("eos", "EOS", "EOS"),
    ("kucoin-shares", "KCS", "KuCoin Token"),
    ("bittensor", "TAO", "Bittensor"),
    ("raydium", "RAY", "Raydium"),
    ("ondo-finance", "ONDO", "Ondo"),
    ("quant-network", "QNT", "Quant"),
    ("neo", "NEO", "Neo"),
    ("iota", "IOTA", "IOTA"),
    ("arweave", "AR", "Arweave"),
    # 71-80
    ("chiliz", "CHZ", "Chiliz"),
    ("enjincoin", "ENJ", "Enjin Coin"),
    ("dydx", "DYDX", "dYdX"),
    ("pendle", "PENDLE", "Pendle"),
    ("woo-network", "WOO", "WOO"),
    ("curve-dao-token", "CRV", "Curve DAO"),
    ("1inch", "1INCH", "1inch"),
    ("kava", "KAVA", "Kava"),
    ("mina-protocol", "MINA", "Mina"),
    ("zilliqa", "ZIL", "Zilliqa"),
    # 81-90
    ("celo", "CELO", "Celo"),
    ("pancakeswap-token", "CAKE", "PancakeSwap"),
    ("compound-governance-token", "COMP", "Compound"),
    ("synthetix-network-token", "SNX", "Synthetix"),
    ("fetch-ai", "FET", "Fetch.ai"),
    ("ocean-protocol", "OCEAN", "Ocean Protocol"),
    ("mask-network", "MASK", "Mask Network"),
    ("loopring", "LRC", "Loopring"),
    ("iotex", "IOTX", "IoTeX"),
    ("conflux-token", "CFX", "Conflux"),
    # 91-100
    ("rocket-pool", "RPL", "Rocket Pool"),
    ("thorchain", "RUNE", "THORChain"),
    ("gmx", "GMX", "GMX"),
    ("blur", "BLUR", "Blur"),
    ("helium", "HNT", "Helium"),
    ("eigenlayer", "EIGEN", "EigenLayer"),
    ("ethena", "ENA", "Ethena"),
    ("jito-governance-token", "JTO", "Jito"),
    ("wormhole", "W", "Wormhole"),
    ("echelon-prime", "PRIME", "Echelon Prime"),
    # 101-125 (buffer — next-ranked real altcoins)
    ("grass", "GRASS", "Grass"),
    ("official-trump", "TRUMP", "Official Trump"),
    ("sonic-svm", "SONIC", "Sonic SVM"),
    ("pudgy-penguins", "PENGU", "Pudgy Penguins"),
    ("mantra-dao", "OM", "MANTRA"),
    ("pi-network", "PI", "Pi Network"),
    ("story-protocol", "IP", "Story"),
    ("berachain", "BERA", "Berachain"),
    ("dash", "DASH", "Dash"),
    ("zcash", "ZEC", "Zcash"),
    ("decred", "DCR", "Decred"),
    ("nexo", "NEXO", "Nexo"),
    ("bitget-token", "BGB", "Bitget Token"),
    ("gatechain-token", "GT", "GateToken"),
    ("huobi-token", "HTX", "HTX Token"),
    ("whitebit", "WBT", "WhiteBIT Token"),
    ("flare-networks", "FLR", "Flare"),
    ("xdce-crowd-sale", "XDC", "XDC Network"),
    ("morpho-network", "MORPHO", "Morpho"),
    ("astar", "ASTR", "Astar"),
    ("sky-mavis", "SKY", "Sky"),
]


def fetch_top_coins(n: int = TOP_N_COINS, source: str = "fallback") -> list[dict]:
    """Get top N tradeable altcoins.

    Args:
        n: Number of coins to return.
        source: "fallback" (curated list, default) or "coingecko" (live API).
            The curated fallback is preferred because CoinGecko's ranking
            includes stablecoins, RWA fund tokens, and other non-tradeable
            assets that pollute the list.

    Returns a list of dicts with keys: id, symbol, name, market_cap_rank.
    """
    if source == "coingecko":
        return _fetch_from_coingecko(n)
    return _build_fallback_list(n)


def _fetch_from_coingecko(n: int) -> list[dict]:
    """Fetch from CoinGecko API with exclusion filtering."""
    coins = []
    per_page = 250
    page = 1
    max_retries = 3

    while len(coins) < n:
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
        }

        for attempt in range(max_retries):
            try:
                resp = requests.get(COINGECKO_MARKETS_URL, params=params, timeout=30)
            except requests.RequestException as e:
                print(f"  Request error: {e}")
                resp = None
                break
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.ok:
                break
        else:
            resp = None

        if resp is None or not resp.ok:
            print("  CoinGecko unavailable, using curated fallback list.")
            return _build_fallback_list(n)

        batch = resp.json()
        if not batch:
            break

        for coin in batch:
            if coin["id"] in EXCLUDED_COIN_IDS:
                continue
            coins.append({
                "id": coin["id"],
                "symbol": coin["symbol"].upper(),
                "name": coin["name"],
                "market_cap_rank": coin.get("market_cap_rank"),
            })
            if len(coins) >= n:
                break

        if len(coins) >= n:
            break

        page += 1
        time.sleep(COINGECKO_RATE_LIMIT)

    return coins[:n]


def _build_fallback_list(n: int) -> list[dict]:
    """Build coin list from curated fallback data."""
    coins = []
    for rank, (coin_id, symbol, name) in enumerate(_FALLBACK_TOP_COINS, 1):
        coins.append({
            "id": coin_id,
            "symbol": symbol,
            "name": name,
            "market_cap_rank": rank,
        })
        if len(coins) >= n:
            break
    return coins


def save_coin_list(coins: list[dict]) -> None:
    """Save coin list to local JSON cache."""
    COIN_LIST_FILE.write_text(json.dumps(coins, indent=2))
    print(f"Saved {len(coins)} coins to {COIN_LIST_FILE}")


def load_coin_list() -> list[dict]:
    """Load coin list from local JSON cache."""
    if not COIN_LIST_FILE.exists():
        raise FileNotFoundError(
            f"Coin list not found at {COIN_LIST_FILE}. Run fetch_top_coins() first."
        )
    return json.loads(COIN_LIST_FILE.read_text())


def get_coin_list(force_refresh: bool = False) -> list[dict]:
    """Get top coins — from cache if available, otherwise build and cache.

    Uses the curated fallback list by default (no CoinGecko dependency).
    Pass force_refresh=True to rebuild from the fallback list.
    """
    if not force_refresh and COIN_LIST_FILE.exists():
        return load_coin_list()

    print(f"Building top {TOP_N_COINS} coin list (curated)...")
    coins = fetch_top_coins()
    save_coin_list(coins)
    return coins
