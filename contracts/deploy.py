"""
deploy.py — Deploy ACRV Contracts to Base
==========================================
Deploys ACRV.sol, CompetitionRegistry.sol and AcervatorTrophy.sol to Base
Sepolia (testnet) or Base Mainnet.

Prerequisites:
    forge build
    pip install -e ".[contracts]"

`forge build` comes first and is not optional. This script deploys the
artifacts Foundry wrote under `out/`, so the bytecode that reaches the chain
is the bytecode `foundry.toml` declares and the analyzers read. It runs no
compiler of its own.

web3 and eth-account are an OPT-IN extra. Issue #94 made `pyproject.toml`
the one place a package name lives, and issue #92 put these in it. This
file names no package, so the set it needs and the set that installs
cannot drift apart.

Usage:
    # Testnet (Base Sepolia — do this first)
    python deploy.py --network sepolia --key 0xYOUR_PRIVATE_KEY

    # Mainnet (after testnet validated)
    python deploy.py --network mainnet --key 0xYOUR_PRIVATE_KEY

    # Using environment variable (recommended)
    export ACERVATOR_PRIVATE_KEY=0x...
    python deploy.py --network sepolia

After deployment, update base_config.py with the returned contract addresses.

Get test ETH: https://www.coinbase.com/faucets/base-ethereum-goerli-faucet
              https://faucet.quicknode.com/base/sepolia
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.competition.base_config import BASE_MAINNET, BASE_SEPOLIA

if TYPE_CHECKING:
    from web3.types import TxReceipt

# Issue #92. What stood here was `install_deps()`. It held the package
# names ["web3", "eth-account", "py-solc-x"] as a literal list and ran
# `pip install --break-system-packages` on each one that would not
# import, into whatever interpreter happened to be running. That is two
# defects in six lines: a ninth hand-copied dependency list of the kind
# issue #94 removed from eight files, and a script that mutates the
# operator's live environment without being asked. The live Acervator
# runs from that environment.
#
# The two imports below are now GUARDED. Each sits inside `try:` with
# an `except ImportError` that names the extra and stops. The script
# states what to install; it does not install it.
MISSING_EXTRA = """
  {}

  The Base-chain deployment tools are an OPT-IN extra and are not
  part of an Acervator install. Add them, and nothing else, with:

      pip install -e ".[contracts]"

  The package names come from pyproject.toml, which is the one
  dependency source. Do not install them by hand.
"""

MISSING_ARTIFACT = """
  Foundry artifact not found: {}

  Build the contracts before deploying:

      forge build

  This script deploys what `forge build` wrote. `foundry.toml` fixes the
  compiler version, the EVM target, the optimizer and the IR pipeline, so
  the deployed bytecode is the bytecode the analyzers read. Compiling here
  with different settings would put unanalyzed bytecode on a chain.
"""

# Deployment order. ACRV takes no constructor argument, CompetitionRegistry
# takes the token address, the trophy takes the registry address, and
# ACRV.setRegistry names the minter once. Nothing needs an address that does
# not exist yet, so the three contracts no longer form a cycle.
DEPLOY_ARTIFACTS = {
    "ACRV": "ACRV.sol/ACRV.json",
    "CompetitionRegistry": "CompetitionRegistry.sol/CompetitionRegistry.json",
    "AcervatorTrophy": "AcervatorTrophy.sol/AcervatorTrophy.json",
}


def load_artifacts(repo_root: Path) -> dict:
    """Read the ABI and creation bytecode Foundry wrote for each contract.

    Returns {contract_name: {"abi": [...], "bin": "0x..."}} for the three
    contracts this script deploys. Raises SystemExit naming `forge build`
    when an artifact is absent or carries no bytecode.
    """
    out_dir = repo_root / "out"
    artifacts = {}
    for name, relative in DEPLOY_ARTIFACTS.items():
        path = out_dir / relative
        if not path.is_file():
            raise SystemExit(MISSING_ARTIFACT.format(path))
        payload = json.loads(path.read_text(encoding="utf-8"))
        bytecode = payload.get("bytecode", {}).get("object", "")
        if not bytecode or bytecode == "0x":
            raise SystemExit(MISSING_ARTIFACT.format(path))
        artifacts[name] = {"abi": payload["abi"], "bin": bytecode}
    return artifacts


def deploy(network: str, private_key: str, repo_root: Path) -> None:
    """Deploy the three contracts in an order no immutable field forbids.

    Steps, in sequence: ACRV with no argument, CompetitionRegistry holding
    the token address, ACRV.setRegistry naming the registry as sole minter,
    then AcervatorTrophy holding the registry address. The setRegistry call
    is the one wiring step, and a second call to it reverts.
    """
    # Guarded for the reason written above MISSING_EXTRA.
    try:
        from eth_account import Account
        from web3 import Web3
    except ImportError as exc:
        raise SystemExit(MISSING_EXTRA.format(exc)) from exc

    cfg = BASE_SEPOLIA if network == "sepolia" else BASE_MAINNET
    print("\n  ══════════════════════════════════════")
    print("  Acervator Contract Deployment")
    print(f"  Network: {cfg.name}")
    print(f"  Chain ID: {cfg.chain_id}")
    print("  ══════════════════════════════════════")

    # Connect
    w3 = Web3(Web3.HTTPProvider(cfg.rpc_url))
    if not w3.is_connected():
        print(f"  ERROR: Cannot connect to {cfg.rpc_url}")
        sys.exit(1)

    account = Account.from_key(private_key)
    balance = w3.eth.get_balance(account.address)
    eth_bal = w3.from_wei(balance, "ether")
    print(f"\n  Deployer: {account.address}")
    print(f"  ETH balance: {eth_bal:.6f}")

    if float(eth_bal) < 0.001 and network != "mainnet":
        print("\n  WARNING: Low ETH balance. Get test ETH from:")
        print("  https://www.coinbase.com/faucets/base-ethereum-goerli-faucet")

    artifacts = load_artifacts(repo_root)

    def send(name: str, tx: dict) -> TxReceipt:
        """Sign, broadcast and await one transaction; raise on a failed receipt."""
        tx.setdefault("from", account.address)
        tx["nonce"] = w3.eth.get_transaction_count(account.address)
        tx["chainId"] = cfg.chain_id
        signed = account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None)
        if raw is None:
            raw = signed.rawTransaction  # web3 below 6.0 spells it this way
        tx_hash = w3.eth.send_raw_transaction(raw)
        print(f"  Tx: {cfg.explorer_url}/tx/{tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] != 1:
            message = f"{name} failed"
            raise RuntimeError(message)
        return receipt

    def deploy_contract(name: str, *args: object) -> str:
        print(f"\n  Deploying {name}...")
        contract = w3.eth.contract(
            abi=artifacts[name]["abi"], bytecode=artifacts[name]["bin"]
        )
        receipt = send(name, contract.constructor(*args).build_transaction({}))
        addr = receipt["contractAddress"]
        if addr is None:
            message = f"{name} receipt carries no contract address"
            raise RuntimeError(message)
        print(f"  {name} deployed: {cfg.explorer_url}/address/{addr}")
        return addr

    # STEP 1 — ACRV. No constructor argument, so no wrong minter can be
    # baked in. `registry` is zero and mint is unreachable until step 3.
    acrv_addr = deploy_contract("ACRV")

    # STEP 2 — CompetitionRegistry, holding the token address in an
    # immutable field. The token exists, so nothing is predicted.
    btc_feed = cfg.chainlink_btc_usd or "0x" + "0" * 40
    eth_feed = cfg.chainlink_eth_usd or "0x" + "0" * 40
    reg_addr = deploy_contract("CompetitionRegistry", acrv_addr, btc_feed, eth_feed)

    # STEP 3 — name the registry as ACRV's sole minter. One call, then
    # locked: a second call reverts, and the contract refuses any target
    # that holds no code, so a wallet can never become the minter.
    print("\n  Wiring ACRV.setRegistry...")
    acrv = w3.eth.contract(
        address=w3.to_checksum_address(acrv_addr), abi=artifacts["ACRV"]["abi"]
    )
    send("ACRV.setRegistry", acrv.functions.setRegistry(reg_addr).build_transaction({}))
    wired = acrv.functions.registry().call()
    if wired.lower() != reg_addr.lower():
        message = f"ACRV.registry is {wired}, expected {reg_addr}"
        raise RuntimeError(message)
    print(f"  ACRV minter locked to: {wired}")

    # STEP 4 — AcervatorTrophy, holding the registry address in an
    # immutable field. Tier SVGs are uploaded afterwards by setTierSvg.
    trophy_addr = deploy_contract("AcervatorTrophy", reg_addr)

    # Summary
    print("\n  ══════════════════════════════════════")
    print("  DEPLOYMENT COMPLETE")
    print("  ──────────────────────────────────────")
    print(f"  ACRV Token:          {acrv_addr}")
    print(f"  CompetitionRegistry: {reg_addr}")
    print(f"  AcervatorTrophy:     {trophy_addr}")
    print(f"  Network:             {cfg.name}")
    print("  ══════════════════════════════════════")
    print("\n  Update src/competition/base_config.py:")
    prefix = "BASE_SEPOLIA" if network == "sepolia" else "BASE_MAINNET"
    print(f'  {prefix}.acrv_address     = "{acrv_addr}"')
    print(f'  {prefix}.registry_address = "{reg_addr}"')

    # Write deployment record
    record = {
        "network": cfg.name,
        "chain_id": cfg.chain_id,
        "deployer": account.address,
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "acrv_address": acrv_addr,
        "registry_address": reg_addr,
        "trophy_address": trophy_addr,
        "btc_feed": btc_feed,
        "eth_feed": eth_feed,
    }
    record_path = repo_root / "deployment_record.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"\n  Deployment record saved: {record_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy ACRV contracts to Base")
    parser.add_argument(
        "--network",
        choices=["sepolia", "mainnet"],
        default="sepolia",
        help="Target network (default: sepolia)",
    )
    parser.add_argument(
        "--key", default=None, help="Private key (or set ACERVATOR_PRIVATE_KEY env var)"
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root with foundry.toml and out/; default: this file's parent",
    )
    args = parser.parse_args()

    key = args.key or os.environ.get("ACERVATOR_PRIVATE_KEY")
    if not key:
        print("ERROR: Private key required.")
        print("  --key 0x...  or  export ACERVATOR_PRIVATE_KEY=0x...")
        sys.exit(1)

    root = (
        Path(args.repo_root)
        if args.repo_root
        else Path(__file__).resolve().parent.parent
    )

    if args.network == "mainnet":
        confirm = input(
            "\n  WARNING: Deploying to BASE MAINNET. This costs real ETH.\n"
            "  Type 'DEPLOY MAINNET' to confirm: "
        )
        if confirm.strip() != "DEPLOY MAINNET":
            print("  Deployment cancelled.")
            sys.exit(0)

    deploy(args.network, key, root)
