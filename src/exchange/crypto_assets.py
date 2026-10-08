"""
crypto_assets.py — Cryptocurrency asset database
=================================================
Maintains metadata for supported cryptocurrencies including:
  • Logo/icon URLs (from CoinGecko and CryptoCompare CDNs)
  • White paper summaries and reference links
  • Internal descriptions derived from official documentation
  • CoinGecko IDs for price/market data lookups

Logo caching: logos are downloaded once and cached in
``resources/logos/`` for offline use.

``AssetManager.logo_answer`` reads that cache through ``LogoCache``, walking
``logo_candidates`` once per asset and answering a reason rather than a path
when no address serves an image. ``organisation_url`` answers the coin index's
kept ``site``, then the asset's ``website``, only after the scheme is allowed.
"""

from __future__ import annotations

from ..core.asset_logos import LOGO_CACHE_DIR, LogoAnswer, LogoCache
from ..core.safe_url import openable_url
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger("acervator.assets")

#: The two addresses one coin's own picture is looked up through. The list is
#: keyed on nothing and names every coin's id; the market records name the
#: picture each id serves. Neither is a venue and neither takes a key.
COIN_LIST_URL = "https://api.coingecko.com/api/v3/coins/list"
COIN_MARKETS_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&per_page={size}&page=1&ids={ids}"
)

#: The ``per_page`` one ``COIN_MARKETS_URL`` read asks for.
COIN_MARKETS_PAGE = 250

#: The most characters one ``COIN_MARKETS_URL`` may carry; a longer one answers
#: 403 with no body. Measured 2026-09-30 against ``api.coingecko.com``: 2,010
#: characters answered 200 and 123,677 bytes, 2,309 answered 403.
COIN_MARKETS_URL_LIMIT = 2000

#: One coin's own record, the only one of the three carrying the project's
#: homepage. ``COIN_MARKETS_URL`` answers 26 fields and none of them is a site,
#: so a site costs one read per coin id. Neither is a venue and neither takes a key.
COIN_DETAIL_URL = "https://api.coingecko.com/api/v3/coins/{id}"

#: The file under the logo cache holding one looked-up picture address per
#: ticker, written by ``logo_library.build_coin_index``.
COIN_INDEX_NAME = "coin_index.json"
COIN_INDEX_VERSION = 1
COIN_INDEX_VERSION_KEY = "version"
COIN_INDEX_ASSETS_KEY = "assets"
COIN_INDEX_IMAGE_KEY = "image"
COIN_INDEX_REASON_KEY = "reason"
COIN_INDEX_ID_KEY = "coin_id"
COIN_INDEX_CHOSEN_KEY = "chosen_by"
COIN_INDEX_SITE_KEY = "site"
COIN_INDEX_SITE_REASON_KEY = "site_reason"
#: The project name recorded for one ticker, which ``choose_coin`` settles a
#: shared ticker by and ``coin_candidates`` looks a coin id up under.
COIN_INDEX_NAME_KEY = "name"

#: The only scheme a site is written at and read back at. ``openable_url``
#: allows http as well, and a browser is only ever handed an https address.
COIN_SITE_SCHEMES: tuple[str, ...] = ("https",)

COIN_INDEX_READ_LOG = "crypto assets: %s will not parse: %s"

#: The icon address keyed on the ticker alone, so a symbol no ``ASSETS`` entry
#: names still resolves an address. It carries no CoinGecko image id and needs
#: no lookup, which is what makes it the one address an unlisted asset has.
#: Read live once, 2026-09-26, for the symbol ONDO: it answered 6,186 bytes of
#: HTML and no failure code, so ``image_extension`` refuses that body.
# OVERTAKEN, the sentence above reading "One symbol is not every symbol, and the
# address is kept for the rest": read live for six tickers on 2026-09-26 -- ONDO,
# PEPE, LTC, UNI, AAVE and ATOM -- and all six answered the same 6,186-byte HTML
# page. The address is kept, and 451 of the 542 logo-library targets hold no other
# one, so each is recorded unresolved by name rather than left silent.
SYMBOL_ICON_URL = "https://www.cryptocompare.com/media/img/cc_icons/{symbol}.png"


def coin_markets_pages(ids: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    """``ids`` grouped so each group's ``COIN_MARKETS_URL`` fits ``COIN_MARKETS_URL_LIMIT``.

    ``COIN_MARKETS_PAGE`` caps a group as well, since ``per_page`` bounds how many
    records one read answers.
    """
    pages: list[list[str]] = []
    held: list[str] = []
    for one in ids:
        asked = str(one).strip()
        if not asked:
            continue
        joined = ",".join([*held, asked])
        built = COIN_MARKETS_URL.format(size=COIN_MARKETS_PAGE, ids=joined)
        if held and (
            len(built) > COIN_MARKETS_URL_LIMIT or len(held) >= COIN_MARKETS_PAGE
        ):
            pages.append(held)
            held = []
        held.append(asked)
    if held:
        pages.append(held)
    return tuple(tuple(one) for one in pages)


def coin_index_path(cache_dir: Optional[Path] = None) -> Path:
    """``COIN_INDEX_NAME`` under ``cache_dir``, defaulting to ``LOGO_CACHE_DIR``."""
    return (Path(cache_dir) if cache_dir else LOGO_CACHE_DIR) / COIN_INDEX_NAME


def load_coin_index(cache_dir: Optional[Path] = None) -> dict[str, dict]:
    """Every ticker the coin index holds, keyed on the upper-case symbol, empty for none."""
    path = coin_index_path(cache_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning(COIN_INDEX_READ_LOG, path, exc)
        return {}
    assets = raw.get(COIN_INDEX_ASSETS_KEY) if isinstance(raw, dict) else None
    if not isinstance(assets, dict):
        return {}
    return {
        str(name).strip().upper(): row
        for name, row in assets.items()
        if isinstance(row, dict)
    }


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
    # No logo_url: the address these rows carried named CoinGecko image
    # directory 1, BTC's, for every one of them, because the format string
    # substituted cgid into the file name only.
    _register(
        sym,
        name=name,
        coingecko_id=cgid,
        logo_fallback_url=SYMBOL_ICON_URL.format(symbol=sym),
        category=cat,
        description=desc,
    )


# Each coingecko_id below was confirmed against CoinGecko's own record of the
# Coinbase Exchange market for that base, not by matching the ticker symbol.
for sym, name, cgid, cat, desc in [
    (
        "ZEC",
        "Zcash",
        "zcash",
        "Privacy",
        "Privacy coin on a proof-of-work layer 1, shielding transfers with zero-knowledge proofs.",
    ),
    (
        "HYPE",
        "Hyperliquid",
        "hyperliquid",
        "DEX / Derivatives",
        "Exchange token of a derivatives DEX that is its own layer 1 smart contract platform.",
    ),
    (
        "VVV",
        "Venice Token",
        "venice-token",
        "AI",
        "AI application and AI agent token on Base.",
    ),
    (
        "USELESS",
        "Useless Coin",
        "useless-3",
        "Meme",
        "Meme coin on Solana and BNB Chain.",
    ),
    (
        "PUMP",
        "Pump.fun",
        "pump-fun",
        "DEX",
        "Exchange token of a SocialFi automated market maker on Solana.",
    ),
    (
        "TAO",
        "Bittensor",
        "bittensor",
        "AI",
        "Layer 1 smart contract platform for machine-learning work, classed as DePIN.",
    ),
    (
        "AERO",
        "Aerodrome Finance",
        "aerodrome-finance",
        "DEX",
        "Automated market maker DEX on Base, with its own exchange token.",
    ),
    (
        "LIGHTER",
        "Lighter",
        "lighter",
        "DEX / Derivatives",
        "Perpetuals DEX on Ethereum; CoinGecko carries it under the symbol LIT.",
    ),
]:
    # No logo_url: the CoinGecko image id for these is unconfirmed, so
    # get_logo_url falls through to logo_fallback_url.
    _register(
        sym,
        name=name,
        coingecko_id=cgid,
        logo_fallback_url=SYMBOL_ICON_URL.format(symbol=sym),
        category=cat,
        description=desc,
    )


# Asset manager
class AssetManager:
    """
    Access cryptocurrency metadata and manage logo caching.
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        """Hold the logo cache; the directory is made on the first kept file, not here."""
        self._cache_dir = cache_dir or LOGO_CACHE_DIR
        self._logos = LogoCache(self._cache_dir)
        self._coins: Optional[dict[str, dict]] = None

    @property
    def coin_index(self) -> dict[str, dict]:
        """``load_coin_index`` over ``cache_dir``, read once per ``AssetManager``."""
        if self._coins is None:
            self._coins = load_coin_index(self._cache_dir)
        return self._coins

    def coin_index_reason(self, symbol: str) -> str:
        """Why the coin index holds no picture address for ``symbol``, empty when it holds one."""
        row = self.coin_index.get(str(symbol).strip().upper()) or {}
        if str(row.get(COIN_INDEX_IMAGE_KEY) or "").strip():
            return ""
        return str(row.get(COIN_INDEX_REASON_KEY) or "").strip()

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
        return self._logos.kept_path(symbol)

    def logo_candidates(self, symbol: str) -> tuple[str, ...]:
        """Every address ``symbol``'s logo may be served at, best first.

        ``coin_index`` answers first where it holds a looked-up address; a symbol
        no ``ASSETS`` entry names still answers ``SYMBOL_ICON_URL`` on the ticker.
        """
        name = str(symbol).strip().upper()
        if not name:
            return ()
        asset = self.get_asset(name)
        indexed = str(
            (self.coin_index.get(name) or {}).get(COIN_INDEX_IMAGE_KEY) or ""
        ).strip()
        if not indexed and self.coin_index_reason(name):
            return ()
        addresses = [indexed] if indexed else []
        addresses += [asset.logo_url, asset.logo_fallback_url] if asset else []
        addresses.append(SYMBOL_ICON_URL.format(symbol=name))
        seen: list[str] = []
        for one in addresses:
            if one and one not in seen:
                seen.append(one)
        return tuple(seen)

    def logo_answer(self, symbol: str) -> LogoAnswer:
        """``symbol``'s kept logo file, or a ``LogoAnswer`` naming why there is none."""
        return self._logos.resolve(symbol, self.logo_candidates(symbol))

    def organisation_url(self, symbol: str) -> tuple[str, str]:
        """``symbol``'s own site a browser may open, and the reason a refused one is not.

        ``coin_index`` answers first where the fill looked a site up, and the
        ``ASSETS`` record's ``website`` answers for the ten that carry one.
        """
        name = str(symbol).strip().upper()
        indexed = str(
            (self.coin_index.get(name) or {}).get(COIN_INDEX_SITE_KEY) or ""
        ).strip()
        if indexed:
            return openable_url(indexed, allowed_schemes=COIN_SITE_SCHEMES)
        asset = self.get_asset(name)
        return openable_url(asset.website if asset else "")

    def download_logo(self, symbol: str) -> Optional[Path]:
        """Download logo to cache if not already present. Returns cached path."""
        return self.logo_answer(symbol).path

    def get_logo_url(self, symbol: str) -> str:
        """Return the best logo URL for an asset."""
        candidates = self.logo_candidates(symbol)
        return candidates[0] if candidates else ""

    def get_description(self, symbol: str) -> str:
        """Return the whitepaper-derived description for an asset."""
        asset = self.get_asset(symbol)
        return asset.description if asset else ""

    def get_whitepaper_url(self, symbol: str) -> str:
        """Return the whitepaper URL for an asset."""
        asset = self.get_asset(symbol)
        return asset.whitepaper_url if asset else ""
