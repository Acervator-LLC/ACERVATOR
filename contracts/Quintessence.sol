// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — Quintessence
// Chain: Base (Coinbase L2)
// =============================================================================
// The Proof-of-Accumulation entry currency. Balances and nine movements, with
// no ERC-20 surface: a holder cannot move units by a wallet call alone, so the
// ERC-20 transfer and approve functions are absent rather than reverting.
//
// Fixed at construction and unchangeable afterwards:
//   • SUPPLY_CAP = 33,000,000 Quintessence (33_000_000 * 10^18 base units)
//   • REGISTRY is the only address that may distil, respawn, or execute a
//     transfer a holder has already authorized
//   • no owner, no pause, no upgrade hook, no burn, no setter of any kind
//
// Quintessence rests in exactly four places, and the four always sum to
// totalEverMinted:
//
//   walletsTotal + heldTotal + platonicTotal + embeddedTotal
//       == totalEverMinted <= SUPPLY_CAP
//
// embeddedTotal is what a thing in the world holds intrinsically. No wallet call
// reaches it, so it does not circulate, and it is inside SUPPLY_CAP like every
// other bucket. It is drawn out of platonicTotal, never out of a new mint.
//
// The movements are named for the buckets they move between, not for what is
// holding the units, so a material, an item and a creature share one path.
//
// The nine movements are the nine src/competition/quintessence_ledger.py
// applies off-chain, with the same buckets on each side:
//
//   distil                REGISTRY credits a wallet and raises totalEverMinted
//   spend                 a holder moves own units to a held address, where they rest
//   transfer              a holder authorizes, REGISTRY executes, recipient credited
//   bleed                 walletsTotal to platonicTotal, on a transfer or an embed
//   respawn               REGISTRY moves platonicTotal units into a wallet
//   embedFromPlatonic     REGISTRY moves platonicTotal units into embeddedTotal
//   embedFromWallet       a holder moves own units into embeddedTotal, the rest bleeds
//   releaseFromEmbedded   REGISTRY moves embeddedTotal units into a wallet, rest to platonic
//   releaseAllToPlatonic  REGISTRY moves embeddedTotal units into platonicTotal only
//
// heldTotal is terminal: no function moves units out of a held address. A
// withdrawal from one would make spend a transfer that pays no bleed.
//
// Nothing reduces totalEverMinted, and nothing reduces the sum of the four
// buckets, so no unit can be destroyed.
// =============================================================================
pragma solidity 0.8.36;

contract Quintessence {

    // ── Constants ─────────────────────────────────────────────────────────────

    /// Base units per whole Quintessence, matching the 18 every ERC-20 here uses.
    uint256 public constant ONE_QUINTESSENCE = 10**18;

    uint8 public constant DECIMALS = 18;

    uint256 public constant SUPPLY_CAP = 33_000_000 * 10**18;

    uint256 public constant MIN_TRANSFER_SKILL_LEVEL = 1;
    uint256 public constant MAX_TRANSFER_SKILL_LEVEL = 10;

    /// bleedAmount is 8% of amount at skill level 1, falling to 4% at level 10.
    uint256 public constant BLEED_NUMERATOR_AT_LEVEL_1 = 7_200;
    uint256 public constant BLEED_NUMERATOR_STEP_PER_LEVEL = 400;
    uint256 public constant BLEED_DENOMINATOR = 90_000;

    /// transferSeconds is amount / (10 x skillLevel) hours, floored at one hour.
    uint256 public constant MIN_TRANSFER_SECONDS = 3_600;
    uint256 public constant TRANSFER_SECONDS_PER_WHOLE = 360;

    // ── State ─────────────────────────────────────────────────────────────────

    /// The Proof-of-Accumulation registry: the only distil, respawn and
    /// executeTransfer caller. Written once at construction.
    address public immutable REGISTRY;

    /// What each participant wallet holds and can spend.
    mapping(address => uint256) public balance;

    /// What rests at each held address after a spend. Never debited.
    mapping(address => uint256) public heldBalance;

    /// Per wallet, per held address, everything that wallet has ever spent into it.
    mapping(address => mapping(address => uint256)) public spentInto;

    uint256 public walletsTotal;
    uint256 public heldTotal;
    uint256 public platonicTotal;

    /// What things in the world hold intrinsically. No wallet call spends it.
    uint256 public embeddedTotal;

    uint256 public totalEverMinted;

    /// One authorized transfer per sender, which serialises a split transfer.
    struct PendingTransfer {
        address recipient;
        uint256 amount;
        uint256 authorizedAt;
    }

    mapping(address => PendingTransfer) public pendingTransfer;

    // ── Events ────────────────────────────────────────────────────────────────

    event Distilled(address indexed wallet, uint256 amount, uint256 totalEverMintedAfter);

    event Spent(address indexed wallet, address indexed heldAddress, uint256 amount);

    event TransferAuthorized(
        address indexed sender,
        address indexed recipient,
        uint256 amount,
        uint256 authorizedAt
    );

    event TransferCancelled(address indexed sender, address indexed recipient, uint256 amount);

    event Transferred(address indexed sender, address indexed recipient, uint256 received);

    event Bled(address indexed sender, uint256 amount, uint256 platonicTotalAfter);

    event Respawned(address indexed wallet, uint256 amount, uint256 platonicTotalAfter);

    event EmbeddedFromPlatonic(
        uint256 amount,
        uint256 embeddedTotalAfter,
        uint256 platonicTotalAfter
    );

    event EmbeddedFromWallet(
        address indexed wallet,
        uint256 amount,
        uint256 embedded,
        uint256 bled
    );

    event ReleasedFromEmbedded(
        address indexed wallet,
        uint256 amount,
        uint256 recovered,
        uint256 returned
    );

    event ReleasedAllToPlatonic(uint256 amount, uint256 platonicTotalAfter);

    // ── Constructor ───────────────────────────────────────────────────────────

    /**
     * @notice Name the Proof-of-Accumulation registry, permanently.
     * @param registryAddress The contract allowed to distil, respawn and execute
     *        a transfer. It must already hold code, so no wallet can take the
     *        role. A wrong address costs a redeployment and no Quintessence,
     *        because genesis mints none.
     */
    constructor(address registryAddress) {
        require(registryAddress.code.length > 0, "Quint: registry no code");
        REGISTRY = registryAddress;
    }

    // ── Modifiers ─────────────────────────────────────────────────────────────

    modifier onlyRegistry() {
        require(msg.sender == REGISTRY, "Quint: caller not registry");
        _;
    }

    // ── distil ────────────────────────────────────────────────────────────────

    /**
     * @notice Credit a wallet and raise totalEverMinted, refusing a mint past
     *         SUPPLY_CAP.
     * @param wallet The wallet credited.
     * @param amount Base units to mint.
     */
    function distil(address wallet, uint256 amount) external onlyRegistry {
        require(wallet != address(0), "Quint: wallet is zero");
        require(amount > 0, "Quint: amount is zero");
        require(totalEverMinted + amount <= SUPPLY_CAP, "Quint: supply cap reached");

        totalEverMinted += amount;
        balance[wallet] += amount;
        walletsTotal += amount;

        emit Distilled(wallet, amount, totalEverMinted);
    }

    // ── spend ─────────────────────────────────────────────────────────────────

    /**
     * @notice Move the caller's own units to a held address, where they rest.
     * @param heldAddress The held address credited.
     * @param amount Base units to move.
     */
    function spend(address heldAddress, uint256 amount) external {
        require(heldAddress != address(0), "Quint: held is zero");
        require(amount > 0, "Quint: amount is zero");
        require(balance[msg.sender] >= amount, "Quint: balance below amount");

        balance[msg.sender] -= amount;
        walletsTotal -= amount;
        heldBalance[heldAddress] += amount;
        heldTotal += amount;
        spentInto[msg.sender][heldAddress] += amount;

        emit Spent(msg.sender, heldAddress, amount);
    }

    // ── transfer, in two calls ────────────────────────────────────────────────

    /// @dev A pendingTransfer amount above zero is the one mark of an
    ///      authorized transfer awaiting cancelTransfer or executeTransfer.
    function _hasTransferInFlight(address sender) private view returns (bool) {
        return pendingTransfer[sender].amount > 0;
    }

    /**
     * @notice Authorize one transfer out of the caller's own wallet.
     * @param recipient The wallet to credit when REGISTRY executes it.
     * @param amount Base units to send, bleed included.
     */
    function authorizeTransfer(address recipient, uint256 amount) external {
        require(recipient != address(0), "Quint: recipient is zero");
        require(recipient != msg.sender, "Quint: recipient is sender");
        require(amount > 0, "Quint: amount is zero");
        require(balance[msg.sender] >= amount, "Quint: balance below amount");
        require(!_hasTransferInFlight(msg.sender), "Quint: transfer in flight");

        pendingTransfer[msg.sender] = PendingTransfer({
            recipient: recipient,
            amount: amount,
            authorizedAt: block.timestamp
        });

        emit TransferAuthorized(msg.sender, recipient, amount, block.timestamp);
    }

    /// @notice Drop the caller's own authorized transfer, moving no units.
    function cancelTransfer() external {
        PendingTransfer memory pending = pendingTransfer[msg.sender];
        require(pending.amount > 0, "Quint: no transfer in flight");

        delete pendingTransfer[msg.sender];

        emit TransferCancelled(msg.sender, pending.recipient, pending.amount);
    }

    /**
     * @notice Execute a transfer the sender authorized, crediting the recipient
     *         and bleeding the rest into platonicTotal.
     * @param sender The wallet that authorized the transfer.
     * @param skillLevel The sender's transfer skill level, which sets the bleed
     *        and the duration. Its bounds hold the bleed at 4% or more.
     */
    function executeTransfer(address sender, uint256 skillLevel) external onlyRegistry {
        PendingTransfer memory pending = pendingTransfer[sender];
        require(pending.amount > 0, "Quint: no transfer in flight");
        require(balance[sender] >= pending.amount, "Quint: balance below amount");
        require(
            block.timestamp >= pending.authorizedAt + transferSeconds(pending.amount, skillLevel),
            "Quint: transfer not yet due"
        );

        uint256 bled = bleedAmount(pending.amount, skillLevel);
        uint256 received = pending.amount - bled;
        require(received > 0, "Quint: bleed takes all");

        delete pendingTransfer[sender];

        balance[sender] -= pending.amount;
        balance[pending.recipient] += received;
        walletsTotal -= bled;
        platonicTotal += bled;

        emit Transferred(sender, pending.recipient, received);
        emit Bled(sender, bled, platonicTotal);
    }

    // ── respawn ───────────────────────────────────────────────────────────────

    /**
     * @notice Move units out of platonicTotal into a wallet, minting nothing.
     * @param wallet The wallet credited.
     * @param amount Base units to respawn.
     */
    function respawn(address wallet, uint256 amount) external onlyRegistry {
        require(wallet != address(0), "Quint: wallet is zero");
        require(amount > 0, "Quint: amount is zero");
        require(platonicTotal >= amount, "Quint: platonic below amount");

        platonicTotal -= amount;
        balance[wallet] += amount;
        walletsTotal += amount;

        emit Respawned(wallet, amount, platonicTotal);
    }

    // ── embed ─────────────────────────────────────────────────────────────────

    /**
     * @notice Move units out of platonicTotal into embeddedTotal, minting nothing.
     * @param amount Base units the thing drawn into the world holds.
     */
    function embedFromPlatonic(uint256 amount) external onlyRegistry {
        require(amount > 0, "Quint: amount is zero");
        require(platonicTotal >= amount, "Quint: platonic below amount");

        platonicTotal -= amount;
        embeddedTotal += amount;

        emit EmbeddedFromPlatonic(amount, embeddedTotal, platonicTotal);
    }

    /**
     * @notice Move the caller's own units into embeddedTotal, the remainder into
     *         platonicTotal.
     * @param amount Base units the caller commits.
     * @param embeddedAmount The part of amount the thing ends up holding. What is
     *        left over bleeds into platonicTotal, so no unit is destroyed.
     */
    function embedFromWallet(uint256 amount, uint256 embeddedAmount) external {
        require(amount > 0, "Quint: amount is zero");
        require(embeddedAmount <= amount, "Quint: embedded above amount");
        require(balance[msg.sender] >= amount, "Quint: balance below amount");

        uint256 bled = amount - embeddedAmount;

        balance[msg.sender] -= amount;
        walletsTotal -= amount;
        embeddedTotal += embeddedAmount;
        platonicTotal += bled;

        emit EmbeddedFromWallet(msg.sender, amount, embeddedAmount, bled);
    }

    // ── release ───────────────────────────────────────────────────────────────

    /**
     * @notice Move units out of embeddedTotal, recoveredAmount into a wallet and
     *         the remainder into platonicTotal.
     * @param wallet The wallet credited with recoveredAmount.
     * @param amount Base units the thing held before it was broken.
     * @param recoveredAmount The part of amount the wallet keeps.
     */
    function releaseFromEmbedded(address wallet, uint256 amount, uint256 recoveredAmount)
        external
        onlyRegistry
    {
        require(wallet != address(0), "Quint: wallet is zero");
        require(amount > 0, "Quint: amount is zero");
        require(recoveredAmount <= amount, "Quint: recovered above amount");
        require(embeddedTotal >= amount, "Quint: embedded below amount");

        uint256 returned = amount - recoveredAmount;

        embeddedTotal -= amount;
        balance[wallet] += recoveredAmount;
        walletsTotal += recoveredAmount;
        platonicTotal += returned;

        emit ReleasedFromEmbedded(wallet, amount, recoveredAmount, returned);
    }

    /**
     * @notice Move units out of embeddedTotal into platonicTotal, crediting nobody.
     * @param amount Base units the thing held before it was broken.
     */
    function releaseAllToPlatonic(uint256 amount) external onlyRegistry {
        require(amount > 0, "Quint: amount is zero");
        require(embeddedTotal >= amount, "Quint: embedded below amount");

        embeddedTotal -= amount;
        platonicTotal += amount;

        emit ReleasedAllToPlatonic(amount, platonicTotal);
    }

    // ── Reads ─────────────────────────────────────────────────────────────────

    /**
     * @notice Return the bleed on amount at skillLevel, rounded up so every
     *         executed transfer bleeds at least one base unit.
     * @param amount Base units sent.
     * @param skillLevel The sender's transfer skill level.
     * @return The base units that join platonicTotal.
     */
    function bleedAmount(uint256 amount, uint256 skillLevel) public pure returns (uint256) {
        uint256 numerator = BLEED_NUMERATOR_AT_LEVEL_1
            - BLEED_NUMERATOR_STEP_PER_LEVEL * (_checkedSkillLevel(skillLevel) - MIN_TRANSFER_SKILL_LEVEL);
        return (amount * numerator + BLEED_DENOMINATOR - 1) / BLEED_DENOMINATOR;
    }

    /**
     * @notice Return how long a transfer of amount takes at skillLevel.
     * @param amount Base units sent.
     * @param skillLevel The sender's transfer skill level.
     * @return Seconds between authorizeTransfer and the earliest executeTransfer.
     */
    function transferSeconds(uint256 amount, uint256 skillLevel) public pure returns (uint256) {
        uint256 required = amount * TRANSFER_SECONDS_PER_WHOLE
            / (ONE_QUINTESSENCE * _checkedSkillLevel(skillLevel));
        return required < MIN_TRANSFER_SECONDS ? MIN_TRANSFER_SECONDS : required;
    }

    /// @notice Return the base units still mintable under SUPPLY_CAP.
    function remainingEverMintable() external view returns (uint256) {
        return SUPPLY_CAP - totalEverMinted;
    }

    /**
     * @notice Return the four bucket totals, totalEverMinted, SUPPLY_CAP, and
     *         whether the conservation law and the cap hold at this block.
     * @return wallets walletsTotal
     * @return held heldTotal
     * @return platonic platonicTotal
     * @return embedded embeddedTotal
     * @return everMinted totalEverMinted
     * @return cap SUPPLY_CAP
     * @return isBalanced wallets plus held plus platonic plus embedded equals everMinted
     * @return isWithinCap everMinted is at most cap
     */
    function conservation()
        external
        view
        returns (
            uint256 wallets,
            uint256 held,
            uint256 platonic,
            uint256 embedded,
            uint256 everMinted,
            uint256 cap,
            bool isBalanced,
            bool isWithinCap
        )
    {
        wallets = walletsTotal;
        held = heldTotal;
        platonic = platonicTotal;
        embedded = embeddedTotal;
        everMinted = totalEverMinted;
        cap = SUPPLY_CAP;
        isBalanced = wallets + held + platonic + embedded == everMinted;
        isWithinCap = everMinted <= cap;
    }

    // ── Internals ─────────────────────────────────────────────────────────────

    function _checkedSkillLevel(uint256 skillLevel) private pure returns (uint256) {
        require(skillLevel >= MIN_TRANSFER_SKILL_LEVEL, "Quint: skill below minimum");
        require(skillLevel <= MAX_TRANSFER_SKILL_LEVEL, "Quint: skill above maximum");
        return skillLevel;
    }
}
