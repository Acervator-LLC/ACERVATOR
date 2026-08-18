// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — ACRV Token Contract
// Chain: Base (Coinbase L2)
// =============================================================================
// Hard-capped ERC-20 token awarded to winning Acervator bots.
//
// Key invariants (immutable after deployment):
//   • MAX_SUPPLY  = 10,000,000 ACRV (10_000_000 * 10^18 wei)
//   • Only the CompetitionRegistry may mint new tokens
//   • Tokens can never be burned — supply monotonically increases
//   • The registry address is set once at construction and cannot change
//
// These invariants make ACRV provably scarce on-chain.
// The Ekthelius tier (21 tokens max) is enforced in the registry contract.
// =============================================================================
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

contract ACRV is ERC20, Ownable, Pausable {

    // ── Constants ─────────────────────────────────────────────────────────────

    uint256 public constant MAX_SUPPLY = 10_000_000 * 10**18;  // 10M ACRV

    // ── State ─────────────────────────────────────────────────────────────────

    /// The CompetitionRegistry — sole authorized minter.
    /// Set once at construction; immutable thereafter.
    address public immutable registry;

    // ── Events ────────────────────────────────────────────────────────────────

    event TokensMinted(
        address indexed recipient,
        uint256 amount,
        string  competitionId,
        string  tierName,
        uint256 totalSupplyAfter
    );

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor(address _registry)
        ERC20("Acervator Token", "ACRV")
        Ownable(msg.sender)
    {
        require(_registry != address(0), "ACRV: registry cannot be zero address");
        registry = _registry;
    }

    // ── Modifiers ─────────────────────────────────────────────────────────────

    modifier onlyRegistry() {
        require(msg.sender == registry, "ACRV: caller is not the registry");
        _;
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

    // ── Transfer hook — block transfers while paused ──────────────────────────

    function _update(address from, address to, uint256 value)
        internal override whenNotPaused
    {
        super._update(from, to, value);
    }
}
