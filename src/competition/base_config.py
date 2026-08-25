"""
base_config.py — Base (Coinbase L2) Chain Configuration
=========================================================
Chain IDs, RPC endpoints, contract addresses, and ABIs for ACRV deployment.

Networks:
  Base Mainnet: chain_id=8453  — production
  Base Sepolia: chain_id=84532 — testnet (deploy here first)

Usage:
    from src.competition.base_config import BASE_SEPOLIA, BASE_MAINNET
    cfg = BASE_SEPOLIA   # use testnet during development
    cfg = BASE_MAINNET   # production
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BaseNetworkConfig:
    name: str
    chain_id: int
    rpc_url: str
    explorer_url: str
    is_testnet: bool

    # Chainlink price feeds on Base
    # Mainnet:  https://docs.chain.link/data-feeds/price-feeds/addresses?network=base
    # Sepolia:  https://docs.chain.link/data-feeds/price-feeds/addresses?network=base&page=1&testnetPage=1
    chainlink_btc_usd: str = ""
    chainlink_eth_usd: str = ""

    # Contract addresses — populated after deployment
    acrv_address: str = ""
    registry_address: str = ""

    # Gas settings for Base
    max_fee_per_gas_gwei: float = 0.005  # Base is very cheap
    max_priority_fee_per_gas_gwei: float = 0.001


# ── Network definitions ───────────────────────────────────────────────────────

BASE_MAINNET = BaseNetworkConfig(
    name="Base Mainnet",
    chain_id=8453,
    rpc_url="https://mainnet.base.org",
    explorer_url="https://basescan.org",
    is_testnet=False,
    # Chainlink feeds — Base mainnet
    chainlink_btc_usd="0x64c911996D3c6aC71f9b455B1E8E7266BcbD848F",
    chainlink_eth_usd="0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
    # Contract addresses — fill in after deployment
    acrv_address="",
    registry_address="",
)

BASE_SEPOLIA = BaseNetworkConfig(
    name="Base Sepolia (Testnet)",
    chain_id=84532,
    rpc_url="https://sepolia.base.org",
    explorer_url="https://sepolia.basescan.org",
    is_testnet=True,
    # Chainlink feeds — Base Sepolia
    chainlink_btc_usd="",  # limited on testnet
    chainlink_eth_usd="0x4aDC67696bA383F43DD60A9e78F2C97Fbbfc7cb1",
    # Contract addresses — filled in after deployment
    acrv_address="",
    registry_address="",
)


# ── Contract ABIs (minimal — only functions called by Python) ─────────────────

ACRV_ABI = [
    # ERC-20 standard
    {
        "name": "name",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "string"}],
    },
    {
        "name": "symbol",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "string"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint8"}],
    },
    {
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    # ACRV-specific
    {
        "name": "MAX_SUPPLY",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "name": "remainingSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "name": "capReached",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "bool"}],
    },
    {
        "name": "registry",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "address"}],
    },
    # Minting (registry-only, included for ABI completeness)
    {
        "name": "mint",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "competitionId", "type": "string"},
            {"name": "tierName", "type": "string"},
        ],
        "outputs": [],
    },
    # Events
    {
        "name": "TokensMinted",
        "type": "event",
        "inputs": [
            {"name": "recipient", "type": "address", "indexed": True},
            {"name": "amount", "type": "uint256", "indexed": False},
            {"name": "competitionId", "type": "string", "indexed": False},
            {"name": "tierName", "type": "string", "indexed": False},
            {"name": "totalSupplyAfter", "type": "uint256", "indexed": False},
        ],
    },
    {
        "name": "Transfer",
        "type": "event",
        "inputs": [
            {"name": "from", "type": "address", "indexed": True},
            {"name": "to", "type": "address", "indexed": True},
            {"name": "value", "type": "uint256", "indexed": False},
        ],
    },
]

REGISTRY_ABI = [
    # Lifecycle
    {
        "name": "openCompetition",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "id", "type": "string"},
            {"name": "symbol", "type": "string"},
            {"name": "season", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "registerBot",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "compId", "type": "string"},
            {"name": "configHash", "type": "bytes32"},
            {"name": "capitalUSD", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "activateCompetition",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "compId", "type": "string"}],
        "outputs": [],
    },
    {
        "name": "closeForSubmission",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "compId", "type": "string"},
            {"name": "marketRegime", "type": "string"},
        ],
        "outputs": [],
    },
    {
        "name": "submitResult",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "compId", "type": "string"},
            {"name": "merkleRoot", "type": "bytes32"},
            {"name": "startValueCents", "type": "int256"},
            {"name": "finalValueCents", "type": "int256"},
            {"name": "tradeCount", "type": "uint32"},
        ],
        "outputs": [],
    },
    {
        "name": "adjudicate",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "compId", "type": "string"},
            {"name": "winnerWallet", "type": "address"},
            {"name": "tierName", "type": "string"},
            {"name": "tokenAmount", "type": "uint256"},
        ],
        "outputs": [],
    },
    # Views
    {
        "name": "getParticipantCount",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "compId", "type": "string"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "name": "getSubmission",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "compId", "type": "string"},
            {"name": "wallet", "type": "address"},
        ],
        "outputs": [
            {
                "type": "tuple",
                "components": [
                    {"name": "merkleRoot", "type": "bytes32"},
                    {"name": "startingValueCents", "type": "int256"},
                    {"name": "finalValueCents", "type": "int256"},
                    {"name": "advantageCents", "type": "int256"},
                    {"name": "advantageBps", "type": "int32"},
                    {"name": "tradeCount", "type": "uint32"},
                    {"name": "submittedAt", "type": "uint256"},
                    {"name": "submitted", "type": "bool"},
                ],
            }
        ],
    },
    {
        "name": "remainingEkthelius",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "name": "remainingGrandAccumulator",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "name": "currentSeason",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "name": "totalCompetitions",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "name": "getLatestPrice",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "symbol", "type": "string"}],
        "outputs": [
            {"name": "price", "type": "int256"},
            {"name": "updatedAt", "type": "uint256"},
        ],
    },
    # Events
    {
        "name": "CompetitionOpened",
        "type": "event",
        "inputs": [
            {"name": "id", "type": "string", "indexed": True},
            {"name": "symbol", "type": "string", "indexed": False},
            {"name": "season", "type": "uint256", "indexed": False},
        ],
    },
    {
        "name": "ResultSubmitted",
        "type": "event",
        "inputs": [
            {"name": "compId", "type": "string", "indexed": True},
            {"name": "wallet", "type": "address", "indexed": True},
            {"name": "merkleRoot", "type": "bytes32", "indexed": False},
            {"name": "advantageBps", "type": "int32", "indexed": False},
        ],
    },
    {
        "name": "Adjudicated",
        "type": "event",
        "inputs": [
            {"name": "compId", "type": "string", "indexed": True},
            {"name": "winner", "type": "address", "indexed": True},
            {"name": "tier", "type": "string", "indexed": False},
            {"name": "tokensAwarded", "type": "uint256", "indexed": False},
            {"name": "season", "type": "uint256", "indexed": False},
        ],
    },
]
