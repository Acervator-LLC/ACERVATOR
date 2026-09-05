"""
crypto_assets.py — Cryptocurrency asset database v1.1
======================================================
Maintains metadata for supported cryptocurrencies including:
  • Logo/icon URLs (from CoinGecko and CryptoCompare CDNs)
  • White paper summaries and reference links
  • Internal descriptions derived from official documentation
  • CoinGecko IDs for price/market data lookups

Logo caching: logos are downloaded once and cached in
``resources/logos/`` for offline use.
"""

from __future__ import annotations

from ..core.safe_url import SafeRequest, safe_urlopen
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.assets")

LOGO_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "logos"


# Asset descriptor
@dataclass
class CryptoAsset:
    """Metadata for a cryptocurrency."""

    symbol: str  # e.g. "BTC"
    name: str
    coingecko_id: str = ""  # e.g. "bitcoin"
    logo_url: str = ""
    logo_fallback_url: str = ""
    whitepaper_url: str = ""
    website: str = ""
    description: str = ""
    consensus: str = ""  # e.g. "Proof of Work"
    max_supply: str = ""  # formatted, e.g. "21,000,000"
    launch_year: int = 0
    category: str = ""  # e.g. "Currency", "Smart Contract Platform"


ASSETS: dict[str, CryptoAsset] = {}


def _register(symbol: str, **kwargs) -> None:
    ASSETS[symbol] = CryptoAsset(symbol=symbol, **kwargs)


# --- Major cryptocurrencies with whitepaper-derived descriptions -----------

_register(
    "BTC",
    name="Bitcoin",
    coingecko_id="bitcoin",
    logo_url="https://assets.coingecko.com/coins/images/1/small/bitcoin.png",
    whitepaper_url="https://bitcoin.org/bitcoin.pdf",
    website="https://bitcoin.org",
    description=(
        "A peer-to-peer electronic cash system enabling online payments to be sent "
        "directly between parties without a financial institution. Uses proof-of-work "
        "to record transactions on a public distributed ledger (blockchain). The "
        "network timestamps transactions by hashing them into an ongoing chain of "
        "hash-based proof-of-work, forming a record that cannot be changed without "
        "redoing the proof-of-work. Introduced in 2008 by Satoshi Nakamoto."
    ),
    consensus="Proof of Work (SHA-256)",
    max_supply="21,000,000",
    launch_year=2009,
    category="Currency",
)

_register(
    "ETH",
    name="Ethereum",
    coingecko_id="ethereum",
    logo_url="https://assets.coingecko.com/coins/images/279/small/ethereum.png",
    whitepaper_url="https://ethereum.org/en/whitepaper/",
    website="https://ethereum.org",
    description=(
        "A decentralised platform that runs smart contracts — applications that "
        "run exactly as programmed without possibility of downtime, censorship, "
        "fraud, or third-party interference. Provides a Turing-complete virtual "
        "machine (EVM) and a native cryptocurrency (Ether) used as gas to power "
        "computations. Transitioned from Proof of Work to Proof of Stake in 2022 "
        "(The Merge). Proposed by Vitalik Buterin in 2013."
    ),
    consensus="Proof of Stake",
    max_supply="Unlimited (deflationary post-EIP-1559)",
    launch_year=2015,
    category="Smart Contract Platform",
)

_register(
    "BNB",
    name="BNB",
    coingecko_id="binancecoin",
    logo_url="https://assets.coingecko.com/coins/images/825/small/bnb-icon2_2x.png",
    whitepaper_url="https://github.com/bnb-chain/whitepaper",
    website="https://www.bnbchain.org",
    description=(
        "Native token of BNB Chain (formerly Binance Smart Chain). Used for "
        "transaction fees, staking, and governance. BNB Chain is an EVM-compatible "
        "blockchain using Proof of Staked Authority (PoSA) consensus combining "
        "delegated PoS and PoA for fast block times and low fees."
    ),
    consensus="Proof of Staked Authority",
    max_supply="200,000,000 (with quarterly burns)",
    launch_year=2017,
    category="Exchange Token / Smart Contract Platform",
)

_register(
    "SOL",
    name="Solana",
    coingecko_id="solana",
    logo_url="https://assets.coingecko.com/coins/images/4128/small/solana.png",
    whitepaper_url="https://solana.com/solana-whitepaper.pdf",
    website="https://solana.com",
    description=(
        "High-performance blockchain using Proof of History (PoH) combined with "
        "Proof of Stake for sub-second finality and high throughput. PoH creates "
        "a historical record proving that an event occurred at a specific moment, "
        "enabling validators to agree on time ordering without communication overhead."
    ),
    consensus="Proof of History + Proof of Stake",
    max_supply="Unlimited (inflationary with decreasing rate)",
    launch_year=2020,
    category="Smart Contract Platform",
)

_register(
    "XRP",
    name="XRP",
    coingecko_id="ripple",
    logo_url="https://assets.coingecko.com/coins/images/44/small/xrp-symbol-white-128.png",
    whitepaper_url="https://ripple.com/files/ripple_consensus_whitepaper.pdf",
    website="https://xrpl.org",
    description=(
        "Digital asset for payments on the XRP Ledger. Uses the Ripple Protocol "
        "Consensus Algorithm (RPCA) where designated validators agree on transaction "
        "ordering without mining. Designed for fast, low-cost cross-border payments "
        "with 3-5 second settlement times."
    ),
    consensus="Federated Byzantine Agreement (RPCA)",
    max_supply="100,000,000,000",
    launch_year=2012,
    category="Payments",
)

_register(
    "ADA",
    name="Cardano",
    coingecko_id="cardano",
    logo_url="https://assets.coingecko.com/coins/images/975/small/cardano.png",
    whitepaper_url="https://iohk.io/en/research/library/",
    website="https://cardano.org",
    description=(
        "Research-driven blockchain platform using the Ouroboros Proof of Stake "
        "protocol, the first provably secure PoS protocol peer-reviewed by "
        "academic cryptographers. Built in layers: the Cardano Settlement Layer "
        "(CSL) for transactions and the Cardano Computation Layer (CCL) for "
        "smart contracts via Plutus."
    ),
    consensus="Ouroboros Proof of Stake",
    max_supply="45,000,000,000",
    launch_year=2017,
    category="Smart Contract Platform",
)

_register(
    "DOGE",
    name="Dogecoin",
    coingecko_id="dogecoin",
    logo_url="https://assets.coingecko.com/coins/images/5/small/dogecoin.png",
    whitepaper_url="",
    website="https://dogecoin.com",
    description=(
        "Originally created as a lighthearted alternative to Bitcoin featuring "
        "the Shiba Inu meme. Uses Scrypt proof-of-work algorithm with merged "
        "mining alongside Litecoin. Inflationary supply with 5 billion new "
        "DOGE minted annually. Has become widely used for tipping and micropayments."
    ),
    consensus="Proof of Work (Scrypt, merged-mined with LTC)",
    max_supply="Unlimited (inflationary)",
    launch_year=2013,
    category="Currency / Meme",
)

_register(
    "AVAX",
    name="Avalanche",
    coingecko_id="avalanche-2",
    logo_url="https://assets.coingecko.com/coins/images/12559/small/Avalanche_Circle_RedWhite_Trans.png",
    whitepaper_url="https://www.avalabs.org/whitepapers",
    website="https://www.avax.network",
    description=(
        "Blazingly fast smart contracts platform using the Avalanche consensus "
        "protocol — a novel family of consensus protocols based on repeated random "
        "subsampling that achieves near-instant finality. Supports multiple "
        "interoperable blockchains (subnets) with customisable virtual machines."
    ),
    consensus="Avalanche Consensus (Snowball)",
    max_supply="720,000,000",
    launch_year=2020,
    category="Smart Contract Platform",
)

_register(
    "DOT",
    name="Polkadot",
    coingecko_id="polkadot",
    logo_url="https://assets.coingecko.com/coins/images/12171/small/polkadot.png",
    whitepaper_url="https://polkadot.network/whitepaper/",
    website="https://polkadot.network",
    description=(
        "Heterogeneous multi-chain architecture enabling cross-chain transfers "
        "of any data or asset type. The Relay Chain provides shared security "
        "and consensus; parachains are specialised blockchains that connect to it. "
        "Uses Nominated Proof of Stake (NPoS) and GRANDPA/BABE finality gadgets."
    ),
    consensus="Nominated Proof of Stake",
    max_supply="Unlimited (inflationary, ~10% per year)",
    launch_year=2020,
    category="Interoperability",
)

_register(
    "LINK",
    name="Chainlink",
    coingecko_id="chainlink",
    logo_url="https://assets.coingecko.com/coins/images/877/small/chainlink-new-logo.png",
    whitepaper_url="https://chain.link/whitepaper",
    website="https://chain.link",
    description=(
        "Decentralised oracle network that connects smart contracts to real-world "
        "data, events, and payments. Provides tamper-proof inputs and outputs for "
        "complex smart contracts via a network of independent node operators who "
        "are incentivised to provide accurate data through staking mechanisms."
    ),
    consensus="Oracle Network (off-chain computation)",
    max_supply="1,000,000,000",
    launch_year=2017,
    category="Oracle",
)

# Additional assets with descriptions
for sym, name, cgid, cat, desc in [
    (
        "MATIC",
        "Polygon",
        "matic-network",
        "Layer 2",
        "Ethereum scaling solution using sidechains for fast, low-cost transactions.",
    ),
    (
        "UNI",
        "Uniswap",
        "uniswap",
        "DEX",
        "Decentralized exchange protocol enabling automated token swaps on Ethereum.",
    ),
    (
        "LTC",
        "Litecoin",
        "litecoin",
        "Currency",
        "Peer-to-peer cryptocurrency forked from Bitcoin with faster block times.",
    ),
    (
        "ATOM",
        "Cosmos",
        "cosmos",
        "Interoperability",
        "Hub connecting independent blockchains via IBC protocol for cross-chain communication.",
    ),
    (
        "XLM",
        "Stellar",
        "stellar",
        "Payments",
        "Open network for moving money and tokenized assets with near-instant settlement.",
    ),
    (
        "ALGO",
        "Algorand",
        "algorand",
        "Smart Contract Platform",
        "Pure proof-of-stake blockchain with instant finality and low fees.",
    ),
    (
        "FIL",
        "Filecoin",
        "filecoin",
        "Storage",
        "Decentralized storage network where users rent unused hard drive space.",
    ),
    (
        "NEAR",
        "NEAR Protocol",
        "near",
        "Smart Contract Platform",
        "Sharded proof-of-stake blockchain designed for developer-friendly dApp creation.",
    ),
    (
        "APT",
        "Aptos",
        "aptos",
        "Smart Contract Platform",
        "Layer 1 blockchain using Move language, built by former Meta/Diem engineers.",
    ),
    (
        "ARB",
        "Arbitrum",
        "arbitrum",
        "Layer 2",
        "Optimistic rollup scaling Ethereum with lower fees and faster transactions.",
    ),
    (
        "OP",
        "Optimism",
        "optimism",
        "Layer 2",
        "Optimistic rollup for Ethereum scaling with retroactive public goods funding.",
    ),
    (
        "SUI",
        "Sui",
        "sui",
        "Smart Contract Platform",
        "Layer 1 blockchain using Move language with object-centric data model.",
    ),
    (
        "INJ",
        "Injective",
        "injective-protocol",
        "DeFi",
        "Decentralized exchange protocol optimized for cross-chain derivatives trading.",
    ),
    (
        "AAVE",
        "Aave",
        "aave",
        "DeFi / Lending",
        "Decentralized lending protocol where users earn interest or borrow assets.",
    ),
    (
        "MKR",
        "Maker",
        "maker",
        "DeFi / Stablecoin",
        "Governance token for MakerDAO, the protocol behind the DAI stablecoin.",
    ),
    (
        "CRV",
        "Curve",
        "curve-dao-token",
        "DEX",
        "DEX optimized for stablecoin and pegged-asset swaps with minimal slippage.",
    ),
    (
        "RUNE",
        "THORChain",
        "thorchain",
        "DEX / Cross-chain",
        "Decentralized liquidity protocol enabling native cross-chain swaps.",
    ),
    (
        "FTM",
        "Fantom",
        "fantom",
        "Smart Contract Platform",
        "DAG-based smart contract platform with fast finality and low fees.",
    ),
    (
        "SAND",
        "The Sandbox",
        "the-sandbox",
        "Gaming / Metaverse",
        "Virtual world where players build, own, and monetize gaming experiences.",
    ),
    (
        "MANA",
        "Decentraland",
        "decentraland",
        "Gaming / Metaverse",
        "Virtual reality platform powered by Ethereum where users buy and build on land.",
    ),
    (
        "GRT",
        "The Graph",
        "the-graph",
        "Data Indexing",
        "Indexing protocol for querying blockchain data, the Google of Web3.",
    ),
    (
        "RENDER",
        "Render",
        "render-token",
        "GPU Computing",
        "Distributed GPU rendering network connecting artists with GPU providers.",
    ),
    (
        "TIA",
        "Celestia",
        "celestia",
        "Data Availability",
        "Modular blockchain providing data availability layer for rollups.",
    ),
    (
        "SEI",
        "Sei",
        "sei-network",
        "Smart Contract Platform",
        "Layer 1 blockchain optimized for DeFi trading with built-in order matching.",
    ),
    (
        "PEPE",
        "Pepe",
        "pepe",
        "Meme",
        "Meme coin inspired by Pepe the Frog. Community-driven, no utility beyond speculation.",
    ),
    (
        "WIF",
        "dogwifhat",
        "dogwifhat",
        "Meme",
        "Solana-based meme coin featuring a Shiba Inu wearing a hat.",
    ),
    (
        "SHIB",
        "Shiba Inu",
        "shiba-inu",
        "Meme",
        "Ethereum meme token with ShibaSwap DEX and growing ecosystem.",
    ),
    (
        "BONK",
        "Bonk",
        "bonk",
        "Meme",
        "Solana-based meme coin. Community airdrop token, dust-priced with high volatility.",
    ),
    (
        "FLOKI",
        "Floki",
        "floki",
        "Meme",
        "Meme coin with utility ambitions including NFT gaming and DeFi products.",
    ),
    (
        "JUP",
        "Jupiter",
        "jupiter-exchange-solana",
        "DEX",
        "Solana DEX aggregator routing trades through multiple liquidity sources.",
    ),
]:
    _register(
        sym,
        name=name,
        coingecko_id=cgid,
        logo_url=f"https://assets.coingecko.com/coins/images/1/small/{cgid}.png",
        logo_fallback_url=f"https://www.cryptocompare.com/media/img/cc_icons/{sym}.png",
        category=cat,
        description=desc,
    )


# Asset manager
class AssetManager:
    """
    Access cryptocurrency metadata and manage logo caching.
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self._cache_dir = cache_dir or LOGO_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get_asset(self, symbol: str) -> Optional[CryptoAsset]:
        """Look up asset by ticker symbol (case-insensitive)."""
        return ASSETS.get(symbol.upper())

    def list_assets(self) -> list[CryptoAsset]:
        """Return all known assets."""
        return list(ASSETS.values())

    def search(self, query: str) -> list[CryptoAsset]:
        """Search assets by symbol or name (case-insensitive)."""
        q = query.lower()
        return [
            a for a in ASSETS.values() if q in a.symbol.lower() or q in a.name.lower()
        ]

    def get_logo_path(self, symbol: str) -> Optional[Path]:
        """Return local cached logo path, or None if not cached."""
        sym = symbol.upper()
        for ext in ("png", "svg", "jpg"):
            path = self._cache_dir / f"{sym}.{ext}"
            if path.exists():
                return path
        return None

    def download_logo(self, symbol: str) -> Optional[Path]:
        """Download logo to cache if not already present. Returns cached path."""
        cached = self.get_logo_path(symbol)
        if cached:
            return cached

        url = self.get_logo_url(symbol)
        if not url:
            return None

        try:
            dest = self._cache_dir / f"{symbol.upper()}.png"
            req = SafeRequest(url)
            req.add_header("User-Agent", "Acervator/2.8")
            with safe_urlopen(req, timeout=10) as resp:
                data = resp.read()
            if len(data) > 100:  # Valid image
                dest.write_bytes(data)
                logger.info("Cached logo for %s (%d bytes)", symbol, len(data))
                return dest
        except Exception as exc:
            logger.debug("Logo download failed for %s: %s", symbol, exc)
        return None

    def get_logo_url(self, symbol: str) -> str:
        """Return the best logo URL for an asset."""
        asset = self.get_asset(symbol)
        if asset:
            return asset.logo_url or asset.logo_fallback_url
        return f"https://www.cryptocompare.com/media/img/cc_icons/{symbol.upper()}.png"

    def get_description(self, symbol: str) -> str:
        """Return the whitepaper-derived description for an asset."""
        asset = self.get_asset(symbol)
        return asset.description if asset else ""

    def get_whitepaper_url(self, symbol: str) -> str:
        """Return the whitepaper URL for an asset."""
        asset = self.get_asset(symbol)
        return asset.whitepaper_url if asset else ""
