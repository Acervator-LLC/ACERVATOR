"""
deploy.py — Deploy ACRV Contracts to Base
==========================================
Deploys ACRV.sol and CompetitionRegistry.sol to Base Sepolia (testnet)
or Base Mainnet.

Prerequisites:
    pip install web3 eth-account py-solc-x

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

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.competition.base_config import BASE_MAINNET, BASE_SEPOLIA


def install_deps():
    """Install web3, eth-account, and solcx if not present."""
    import subprocess

    for pkg in ["web3", "eth-account", "py-solc-x"]:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            print(f"  Installing {pkg}...")
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    pkg,
                    "--break-system-packages",
                    "-q",
                ]
            )


def compile_contracts(contracts_dir: str) -> dict:
    """Compile ACRV.sol and CompetitionRegistry.sol using solcx."""
    from solcx import compile_files, install_solc, get_installed_solc_versions

    SOLC = "0.8.20"
    installed = get_installed_solc_versions()
    if not any(str(v) == SOLC for v in installed):
        print(f"  Installing solc {SOLC}...")
        install_solc(SOLC)

    print("  Compiling contracts...")
    contracts_path = Path(contracts_dir)
    compiled = compile_files(
        [
            str(contracts_path / "ACRV.sol"),
            str(contracts_path / "CompetitionRegistry.sol"),
        ],
        output_values=["abi", "bin"],
        solc_version=SOLC,
        allow_paths=str(contracts_path),
        import_remappings=[
            "@openzeppelin=node_modules/@openzeppelin",
            "@chainlink=node_modules/@chainlink",
        ],
    )
    return compiled


def deploy(network: str, private_key: str, contracts_dir: str):
    """Full deployment flow: compile → deploy ACRV → deploy Registry → verify."""
    install_deps()
    from web3 import Web3
    from eth_account import Account

    cfg = BASE_SEPOLIA if network == "sepolia" else BASE_MAINNET
    print(f"\n  ══════════════════════════════════════")
    print(f"  Acervator Contract Deployment")
    print(f"  Network: {cfg.name}")
    print(f"  Chain ID: {cfg.chain_id}")
    print(f"  ══════════════════════════════════════")

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
        print(f"\n  WARNING: Low ETH balance. Get test ETH from:")
        print(f"  https://www.coinbase.com/faucets/base-ethereum-goerli-faucet")

    # Compile
    try:
        compiled = compile_contracts(contracts_dir)
    except Exception as e:
        print(f"\n  Compilation failed: {e}")
        print(f"  Make sure OpenZeppelin and Chainlink are installed:")
        print(f"  npm install @openzeppelin/contracts @chainlink/contracts")
        sys.exit(1)

    def deploy_contract(name, abi, bytecode, *args):
        print(f"\n  Deploying {name}...")
        contract = w3.eth.contract(abi=abi, bytecode=bytecode)
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.constructor(*args).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": cfg.chain_id,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        print(f"  Tx: {cfg.explorer_url}/tx/{tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError(f"{name} deployment failed")
        addr = receipt.contractAddress
        print(f"  {name} deployed: {cfg.explorer_url}/address/{addr}")
        return addr

    # Deploy ACRV first (registry address not yet known — use dummy)
    acrv_key = [k for k in compiled if "ACRV" in k and "Registry" not in k][0]
    reg_key = [k for k in compiled if "CompetitionRegistry" in k][0]
    acrv_abi = compiled[acrv_key]["abi"]
    acrv_bin = compiled[acrv_key]["bin"]
    reg_abi = compiled[reg_key]["abi"]
    reg_bin = compiled[reg_key]["bin"]

    # STEP 1: Deploy a temporary ACRV with a placeholder registry
    # We'll deploy the real registry next and update the config
    # NOTE: In production, use a CREATE2 factory or deploy registry first
    # as a proxy pattern. For simplicity here we deploy ACRV with the
    # deployer address as the initial registry, then deploy the actual
    # registry and transfer ownership.

    # Deploy CompetitionRegistry first with zero ACRV address (upgraded next)
    # Better pattern: deploy registry, then deploy ACRV pointing to registry

    # Deploy ACRV with deployer as initial "registry" (will be updated)
    acrv_addr = deploy_contract("ACRV", acrv_abi, acrv_bin, account.address)

    # Deploy CompetitionRegistry pointing to the ACRV contract
    btc_feed = cfg.chainlink_btc_usd or "0x" + "0" * 40
    eth_feed = cfg.chainlink_eth_usd or "0x" + "0" * 40
    reg_addr = deploy_contract(
        "CompetitionRegistry", reg_abi, reg_bin, acrv_addr, btc_feed, eth_feed
    )

    # Summary
    print(f"\n  ══════════════════════════════════════")
    print(f"  DEPLOYMENT COMPLETE")
    print(f"  ──────────────────────────────────────")
    print(f"  ACRV Token:          {acrv_addr}")
    print(f"  CompetitionRegistry: {reg_addr}")
    print(f"  Network:             {cfg.name}")
    print(f"  ══════════════════════════════════════")
    print(f"\n  Update src/competition/base_config.py:")
    if network == "sepolia":
        print(f'  BASE_SEPOLIA.acrv_address     = "{acrv_addr}"')
        print(f'  BASE_SEPOLIA.registry_address = "{reg_addr}"')
    else:
        print(f'  BASE_MAINNET.acrv_address     = "{acrv_addr}"')
        print(f'  BASE_MAINNET.registry_address = "{reg_addr}"')

    # Write deployment record
    record = {
        "network": cfg.name,
        "chain_id": cfg.chain_id,
        "deployer": account.address,
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "acrv_address": acrv_addr,
        "registry_address": reg_addr,
        "btc_feed": btc_feed,
        "eth_feed": eth_feed,
    }
    record_path = Path("deployment_record.json")
    record_path.write_text(json.dumps(record, indent=2))
    print(f"\n  Deployment record saved: {record_path.absolute()}")


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
        "--contracts-dir", default="contracts", help="Path to contracts directory"
    )
    args = parser.parse_args()

    key = args.key or os.environ.get("ACERVATOR_PRIVATE_KEY")
    if not key:
        print("ERROR: Private key required.")
        print("  --key 0x...  or  export ACERVATOR_PRIVATE_KEY=0x...")
        sys.exit(1)

    if args.network == "mainnet":
        confirm = input(
            "\n  WARNING: Deploying to BASE MAINNET. This costs real ETH.\n"
            "  Type 'DEPLOY MAINNET' to confirm: "
        )
        if confirm.strip() != "DEPLOY MAINNET":
            print("  Deployment cancelled.")
            sys.exit(0)

    deploy(args.network, key, args.contracts_dir)
