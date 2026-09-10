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
//   • The governance address is written once by setGovernance and never again
//
// These invariants make ACRV provably scarce on-chain.
// CompetitionRegistry caps Ekthelius-tier awards at 21.
//
// This contract holds no owner. setRegistry and setGovernance are deployment
// wiring, admitted once each from the address that deployed the contract and
// refused on every later call. Nothing else here is privileged: there is no
// pause, no unpause, no ownership handover and no renounce.
//
// Governance.isHalted is the one gate on movement. Three of the five elected
// halt council members halt this token for seven days, and the window closes by
// itself, because _update reads a timestamp and no call lifts a halt.
//
// Deployment order. ACRV takes no constructor argument, so the contracts do not
// form a circular construction sequence:
//   1. ACRV()                                 registry unset, minting impossible
//   2. CompetitionRegistry(acrv, feeds)       acrv is immutable there
//   3. ACRV.setRegistry(registry)             locked from this call onward
//   4. AcervatorTrophy(registry)              registry is immutable there
//   5. Quintessence(registry)                 registry is immutable there
//   6. Governance(quint, registry, trophy, acrv)
//   7. ACRV.setGovernance(governance)         locked from this call onward
// =============================================================================
pragma solidity 0.8.36;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IHaltSource} from "./Governance.sol";

contract ACRV is ERC20 {

    // ── Constants ─────────────────────────────────────────────────────────────

    uint256 public constant MAX_SUPPLY = 10_000_000 * 10**18;  // 10M ACRV

    // ── State ─────────────────────────────────────────────────────────────────

    /// The address that deployed this contract, and the only caller of the two
    /// one-shot wiring functions below.
    address public immutable DEPLOYER;

    /// The CompetitionRegistry — sole authorized minter.
    /// Zero until setRegistry writes it; unchangeable after that one write.
    address public registry;

    /// The Governance contract read by _update. Zero until setGovernance writes it.
    address public governance;

    // ── Events ────────────────────────────────────────────────────────────────

    event TokensMinted(
        address indexed recipient,
        uint256 amount,
        string  competitionId,
        string  tierName,
        uint256 totalSupplyAfter
    );

    event RegistrySet(address indexed registry);

    event GovernanceSet(address indexed governance);

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor() ERC20("Acervator Token", "ACRV") {
        DEPLOYER = msg.sender;
    }

    // ── Modifiers ─────────────────────────────────────────────────────────────

    modifier onlyRegistry() {
        require(msg.sender == registry, "ACRV: caller is not the registry");
        _;
    }

    modifier onlyDeployer() {
        require(msg.sender == DEPLOYER, "ACRV: caller is not the deployer");
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
    function setRegistry(address registryAddress) external onlyDeployer {
        require(registry == address(0),       "ACRV: registry already set");
        require(registryAddress.code.length > 0, "ACRV: registry not a contract");
        registry = registryAddress;
        emit RegistrySet(registryAddress);
    }

    // ── Halt wiring, once ─────────────────────────────────────────────────────

    /**
     * @notice Name the Governance contract whose halt _update reads, permanently.
     * @dev    Callable once, by the deployer, on an address that already holds
     *         code. Until it lands no halt can reach this token, and no council
     *         exists to raise one, because Governance seats the council.
     *
     * @param governanceAddress The deployed Governance address
     */
    function setGovernance(address governanceAddress) external onlyDeployer {
        require(governance == address(0), "ACRV: governance already set");
        require(governanceAddress.code.length > 0, "ACRV: governance not a contract");
        governance = governanceAddress;
        emit GovernanceSet(governanceAddress);
    }

    /// @notice Return whether the halt council has this token halted right now.
    function isHalted() public view returns (bool) {
        address source = governance;
        if (source == address(0)) {
            return false;
        }
        return IHaltSource(source).isHalted(address(this));
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
    ) external onlyRegistry {
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

    // ── Transfer hook — refuse movement while the halt council's halt stands ──

    /// @dev Every mint and every transfer routes through this hook, so one halt
    ///      stops both. isHalted reads a timestamp in Governance, which expires.
    function _update(address from, address to, uint256 value) internal override {
        require(!isHalted(), "ACRV: halted by the halt council");
        super._update(from, to, value);
    }
}
