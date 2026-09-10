// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — ACRV Token Contract
// Chain: Base (Coinbase L2)
// =============================================================================
// Hard-capped ERC-20 token awarded to winning Acervator bots.
//
// Key invariants:
//   • MAX_SUPPLY  = 10,000,000 ACRV (10_000_000 * 10^18 wei)
//   • Only the CompetitionRegistry may mint new tokens
//   • Tokens can never be burned — supply monotonically increases
//   • The registry address is written once by setRegistry and never again
//
// These invariants make ACRV provably scarce on-chain.
// CompetitionRegistry caps Ekthelius-tier awards at 21.
//
// Deployment order. ACRV takes no constructor argument, so the three
// contracts no longer form a circular construction sequence:
//   1. ACRV()                                 registry unset, minting impossible
//   2. CompetitionRegistry(acrv, feeds)       acrv is immutable there
//   3. ACRV.setRegistry(registry)             locked from this call onward
//   4. AcervatorTrophy(registry)              registry is immutable there
// =============================================================================
pragma solidity 0.8.36;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

contract ACRV is ERC20, Ownable2Step, Pausable {

    // ── Constants ─────────────────────────────────────────────────────────────

    uint256 public constant MAX_SUPPLY = 10_000_000 * 10**18;  // 10M ACRV

    // ── State ─────────────────────────────────────────────────────────────────

    /// The CompetitionRegistry — sole authorized minter.
    /// Zero until setRegistry writes it; unchangeable after that one write.
    address public registry;

    // ── Errors ────────────────────────────────────────────────────────────────

    error OwnershipCannotBeRenounced();

    // ── Events ────────────────────────────────────────────────────────────────

    event TokensMinted(
        address indexed recipient,
        uint256 amount,
        string  competitionId,
        string  tierName,
        uint256 totalSupplyAfter
    );

    event RegistrySet(address indexed registry);

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor()
        ERC20("Acervator Token", "ACRV")
        Ownable(msg.sender)
    {}

    // ── Modifiers ─────────────────────────────────────────────────────────────

    modifier onlyRegistry() {
        require(msg.sender == registry, "ACRV: caller is not the registry");
        _;
    }

    // ── Minter wiring, once ───────────────────────────────────────────────────

    /**
     * @notice Name the CompetitionRegistry as the sole minter, permanently.
     * @dev    Callable once. The second call reverts, so the minter is fixed
     *         for the life of the contract. The target must already hold
     *         code: an externally owned account can never become the minter,
     *         which is the mis-wiring this check exists to refuse.
     *
     *         Before this call registry is the zero address. msg.sender is
     *         never the zero address in a transaction, so onlyRegistry admits
     *         nobody and mint is unreachable until the wiring lands.
     *
     * @param registryAddress The deployed CompetitionRegistry address
     */
    function setRegistry(address registryAddress) external onlyOwner {
        require(registry == address(0),       "ACRV: registry already set");
        require(registryAddress.code.length > 0, "ACRV: registry not a contract");
        registry = registryAddress;
        emit RegistrySet(registryAddress);
    }

    // ── Minting ───────────────────────────────────────────────────────────────

    /**
     * @notice Mint ACRV tokens to a winning bot's wallet.
     * @dev    Called exclusively by CompetitionRegistry after adjudication.
     *         Reverts if minting would exceed MAX_SUPPLY.
     *
     * @param recipient     The bot's wallet address (derived from its public key)
     * @param amount        Token amount in wei (18 decimals)
     * @param competitionId The competition identifier (for event log)
     * @param tierName      Rarity tier name (for event log)
     */
    function mint(
        address recipient,
        uint256 amount,
        string calldata competitionId,
        string calldata tierName
    ) external onlyRegistry whenNotPaused {
        require(recipient != address(0), "ACRV: mint to zero address");
        require(amount > 0,              "ACRV: mint amount must be > 0");
        require(
            totalSupply() + amount <= MAX_SUPPLY,
            "ACRV: mint would exceed MAX_SUPPLY of 10,000,000 ACRV"
        );

        _mint(recipient, amount);

        emit TokensMinted(
            recipient,
            amount,
            competitionId,
            tierName,
            totalSupply()
        );
    }

    // ── Supply queries ────────────────────────────────────────────────────────

    /// Tokens still mintable before hard cap is reached.
    function remainingSupply() external view returns (uint256) {
        return MAX_SUPPLY - totalSupply();
    }

    /// True if the hard cap has been fully minted.
    function capReached() external view returns (bool) {
        return totalSupply() >= MAX_SUPPLY;
    }

    // ── Emergency pause (owner only) ──────────────────────────────────────────

    function pause()   external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    // ── Ownership cannot be abandoned ─────────────────────────────────────────

    /// @notice Refuse to abandon ownership, because unpause is owner-only and a
    ///         pause would then freeze every balance for good.
    function renounceOwnership() public pure override {
        revert OwnershipCannotBeRenounced();
    }

    // ── Transfer hook — block transfers while paused ──────────────────────────

    function _update(address from, address to, uint256 value)
        internal override whenNotPaused
    {
        super._update(from, to, value);
    }
}
