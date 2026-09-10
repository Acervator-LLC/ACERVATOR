// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — Quintessence invariants
// =============================================================================
// forge drives QuintessenceHandler with random call sequences and checks every
// invariant_ function after them.
//
// The law is four buckets:
//
//   walletsTotal + heldTotal + platonicTotal + embeddedTotal
//       == totalEverMinted <= SUPPLY_CAP
//
// embeddedTotal is what a thing in the world holds. embedFromPlatonic draws it
// out of platonicTotal, embedFromWallet out of a wallet, releaseFromEmbedded
// returns part of it to a wallet, and releaseAllToPlatonic returns all of it to
// platonicTotal. None of the four mints a unit, so each wrapper below records its
// own bucket deltas and a counting invariant reads them. A wrapper that only
// called the function would leave the fourth bucket unread, and every invariant
// would pass on a law that moved nothing into it.
//
// QuintessenceHandler is the registry, so it is the only caller that reaches
// distil, respawn, executeTransfer, embedFromPlatonic, releaseFromEmbedded and
// releaseAllToPlatonic. Each QuintessenceActor is an ordinary holder, and
// embedFromWallet is holder-called. QuintessenceIntruder holds code and is not
// the registry, so every call it makes to the six registry functions must be
// refused.
//
// A counting invariant asserts its attempt counter is above zero before it reads
// its refusal counter, so a path no sequence reached fails instead of passing on
// an absence.
//
// targetContracts names QuintessenceHandler alone. Without it forge also drives
// Quintessence, QuintessenceActor and WalletSet directly, using the handler's
// and the actors' own addresses as senders, so a direct respawn or a direct
// authorizeTransfer credits a wallet that never passed through WalletSet.add
// and recordedWalletSum under-reports a walletsTotal that is correct.
// =============================================================================
pragma solidity 0.8.36;

import {Quintessence} from "../../contracts/Quintessence.sol";

interface Vm {
    function warp(uint256 newTimestamp) external;
}

contract WalletSet {
    address[] public wallets;
    mapping(address => bool) public isKnown;

    function add(address wallet) external {
        if (wallet != address(0) && !isKnown[wallet]) {
            isKnown[wallet] = true;
            wallets.push(wallet);
        }
    }

    function count() external view returns (uint256) {
        return wallets.length;
    }
}

contract QuintessenceActor {
    Quintessence private _quint;
    WalletSet private _walletSet;

    function bind(Quintessence quint, WalletSet walletSet) external {
        require(address(_quint) == address(0), "Actor: already bound");
        _quint = quint;
        _walletSet = walletSet;
        walletSet.add(address(this));
    }

    function spend(address heldAddress, uint256 amount) external {
        _quint.spend(heldAddress, amount);
    }

    function authorizeTransfer(address recipient, uint256 amount) external {
        _walletSet.add(recipient);
        _quint.authorizeTransfer(recipient, amount);
    }

    function cancelTransfer() external {
        _quint.cancelTransfer();
    }

    function embedFromWallet(uint256 amount, uint256 embeddedAmount) external {
        _quint.embedFromWallet(amount, embeddedAmount);
    }
}

contract QuintessenceIntruder {
    Quintessence private _quint;

    uint256 public attempts;
    uint256 public successes;
    uint256 public refusals;

    function bind(Quintessence quint) external {
        require(address(_quint) == address(0), "Intruder: already bound");
        _quint = quint;
    }

    function tryDistil(address wallet, uint256 amount) external {
        attempts += 1;
        try _quint.distil(wallet, amount) {
            successes += 1;
        } catch {
            refusals += 1;
        }
    }

    function tryRespawn(address wallet, uint256 amount) external {
        attempts += 1;
        try _quint.respawn(wallet, amount) {
            successes += 1;
        } catch {
            refusals += 1;
        }
    }

    function tryExecuteTransfer(address sender, uint256 skillLevel) external {
        attempts += 1;
        try _quint.executeTransfer(sender, skillLevel) {
            successes += 1;
        } catch {
            refusals += 1;
        }
    }

    function tryEmbedFromPlatonic(uint256 amount) external {
        attempts += 1;
        try _quint.embedFromPlatonic(amount) {
            successes += 1;
        } catch {
            refusals += 1;
        }
    }

    function tryReleaseFromEmbedded(address wallet, uint256 amount, uint256 recoveredAmount)
        external
    {
        attempts += 1;
        try _quint.releaseFromEmbedded(wallet, amount, recoveredAmount) {
            successes += 1;
        } catch {
            refusals += 1;
        }
    }

    function tryReleaseAllToPlatonic(uint256 amount) external {
        attempts += 1;
        try _quint.releaseAllToPlatonic(amount) {
            successes += 1;
        } catch {
            refusals += 1;
        }
    }
}

contract QuintessenceHandler {
    uint256 private constant ACTOR_COUNT = 4;
    uint256 private constant ONE_WHOLE = 10**18;

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    Quintessence public quint;
    QuintessenceIntruder public intruder;
    WalletSet public walletSet;
    QuintessenceActor[ACTOR_COUNT] public actors;

    uint256 public highEverMinted;
    uint256 public highBucketSum;

    uint256 public capAttempts;
    uint256 public capSuccesses;

    uint256 public unauthorizedExecuteAttempts;
    uint256 public unauthorizedExecuteSuccesses;

    uint256 public beforeDueAttempts;
    uint256 public beforeDueSuccesses;

    uint256 public transfersExecuted;
    uint256 public transfersBleedingFourPercentOrMore;

    uint256 public embedFromPlatonicAttempts;
    uint256 public embedFromPlatonicConserving;

    uint256 public embedFromWalletAttempts;
    uint256 public embedFromWalletConserving;

    uint256 public releaseFromEmbeddedAttempts;
    uint256 public releaseFromEmbeddedConserving;

    uint256 public releaseAllToPlatonicAttempts;
    uint256 public releaseAllToPlatonicConserving;

    uint256 public embeddedMovementAttempts;
    uint256 public embeddedMovementsMintingNothing;

    uint256 public distilCalls;
    uint256 public spendCalls;
    uint256 public authorizeCalls;
    uint256 public executeCalls;
    uint256 public respawnCalls;
    uint256 public cancelCalls;
    uint256 public embedFromPlatonicCalls;
    uint256 public embedFromWalletCalls;
    uint256 public releaseFromEmbeddedCalls;
    uint256 public releaseAllToPlatonicCalls;

    constructor() {
        walletSet = new WalletSet();
        for (uint256 i = 0; i < ACTOR_COUNT; ++i) {
            actors[i] = new QuintessenceActor();
        }
    }

    function bind(Quintessence quintessence, QuintessenceIntruder quintessenceIntruder) external {
        require(address(quint) == address(0), "Handler: already bound");
        quint = quintessence;
        intruder = quintessenceIntruder;
        for (uint256 i = 0; i < ACTOR_COUNT; ++i) {
            actors[i].bind(quintessence, walletSet);
        }
    }

    function distil(uint256 actorSeed, uint256 amount) external {
        uint256 room = quint.remainingEverMintable();
        if (room == 0) {
            return;
        }
        quint.distil(_actor(actorSeed), (amount % room) + 1);
        distilCalls += 1;
        _snapshot();
    }

    function distilToTheCap(uint256 actorSeed) external {
        uint256 room = quint.remainingEverMintable();
        if (room == 0) {
            return;
        }
        quint.distil(_actor(actorSeed), room);
        distilCalls += 1;
        _snapshot();
    }

    function tryDistilPastCap(uint256 actorSeed) external {
        capAttempts += 1;
        uint256 over = quint.remainingEverMintable() + 1;
        try quint.distil(_actor(actorSeed), over) {
            capSuccesses += 1;
        } catch {
            _snapshot();
        }
        _snapshot();
    }

    function spend(uint256 actorSeed, uint256 heldSeed, uint256 amount) external {
        QuintessenceActor actor = actors[actorSeed % ACTOR_COUNT];
        uint256 walletHolds = quint.balance(address(actor));
        if (walletHolds == 0) {
            return;
        }
        address heldAddress = address(uint160(uint256(keccak256(abi.encode(heldSeed))) | 1));
        actor.spend(heldAddress, (amount % walletHolds) + 1);
        spendCalls += 1;
        _snapshot();
    }

    function authorizeTransfer(uint256 senderSeed, uint256 recipientSeed, uint256 amount) external {
        QuintessenceActor actor = actors[senderSeed % ACTOR_COUNT];
        address recipient = _actor(recipientSeed + 1);
        uint256 walletHolds = quint.balance(address(actor));
        (, uint256 pendingAmount,) = quint.pendingTransfer(address(actor));
        if (walletHolds < 2 || pendingAmount != 0 || recipient == address(actor)) {
            return;
        }
        actor.authorizeTransfer(recipient, (amount % (walletHolds - 1)) + 2);
        authorizeCalls += 1;
        _snapshot();
    }

    function cancelTransfer(uint256 senderSeed) external {
        QuintessenceActor actor = actors[senderSeed % ACTOR_COUNT];
        (, uint256 pendingAmount,) = quint.pendingTransfer(address(actor));
        if (pendingAmount == 0) {
            return;
        }
        actor.cancelTransfer();
        cancelCalls += 1;
        _snapshot();
    }

    function executeTransfer(uint256 senderSeed, uint256 skillLevel) external {
        address sender = _actor(senderSeed);
        (, uint256 pendingAmount, uint256 authorizedAt) = quint.pendingTransfer(sender);
        if (pendingAmount == 0) {
            return;
        }
        uint256 level = (skillLevel % quint.MAX_TRANSFER_SKILL_LEVEL()) + 1;
        uint256 due = authorizedAt + quint.transferSeconds(pendingAmount, level);
        if (block.timestamp < due) {
            VM.warp(due);
        }
        uint256 platonicBefore = quint.platonicTotal();
        quint.executeTransfer(sender, level);
        uint256 bled = quint.platonicTotal() - platonicBefore;
        transfersExecuted += 1;
        if (bled * 25 >= pendingAmount) {
            transfersBleedingFourPercentOrMore += 1;
        }
        executeCalls += 1;
        _snapshot();
    }

    function tryExecuteBeforeDue(uint256 senderSeed) external {
        QuintessenceActor actor = actors[senderSeed % ACTOR_COUNT];
        (, uint256 pendingAmount,) = quint.pendingTransfer(address(actor));
        if (pendingAmount != 0) {
            actor.cancelTransfer();
            cancelCalls += 1;
        }
        uint256 walletHolds = quint.balance(address(actor));
        if (walletHolds < 2) {
            return;
        }
        address recipient = _actor(senderSeed + 1);
        if (recipient == address(actor)) {
            return;
        }
        actor.authorizeTransfer(recipient, walletHolds);
        authorizeCalls += 1;
        beforeDueAttempts += 1;
        try quint.executeTransfer(address(actor), 10) {
            beforeDueSuccesses += 1;
        } catch {
            _snapshot();
        }
        _snapshot();
    }

    function tryExecuteWithoutAuthorization(uint256 senderSeed) external {
        address sender = _actor(senderSeed);
        (, uint256 pendingAmount,) = quint.pendingTransfer(sender);
        if (pendingAmount != 0) {
            return;
        }
        unauthorizedExecuteAttempts += 1;
        try quint.executeTransfer(sender, 1) {
            unauthorizedExecuteSuccesses += 1;
        } catch {
            _snapshot();
        }
        _snapshot();
    }

    function respawn(uint256 actorSeed, uint256 amount) external {
        uint256 platonic = quint.platonicTotal();
        if (platonic == 0) {
            return;
        }
        quint.respawn(_actor(actorSeed), (amount % platonic) + 1);
        respawnCalls += 1;
        _snapshot();
    }

    /// Draw base units out of platonicTotal into embeddedTotal and record the
    /// delta of every bucket the movement is allowed to touch.
    function embedFromPlatonic(uint256 amount) external {
        uint256 platonicBefore = quint.platonicTotal();
        if (platonicBefore == 0) {
            return;
        }
        uint256 drawn = (amount % platonicBefore) + 1;
        uint256 embeddedBefore = quint.embeddedTotal();
        uint256 walletsBefore = quint.walletsTotal();
        uint256 mintedBefore = quint.totalEverMinted();

        quint.embedFromPlatonic(drawn);

        embedFromPlatonicAttempts += 1;
        embeddedMovementAttempts += 1;
        if (
            quint.platonicTotal() == platonicBefore - drawn
                && quint.embeddedTotal() == embeddedBefore + drawn
                && quint.walletsTotal() == walletsBefore
        ) {
            embedFromPlatonicConserving += 1;
        }
        if (quint.totalEverMinted() == mintedBefore) {
            embeddedMovementsMintingNothing += 1;
        }
        embedFromPlatonicCalls += 1;
        _snapshot();
    }

    /// Spend an actor's own units into embeddedTotal, the rest into
    /// platonicTotal, and record the delta of every bucket.
    function embedFromWallet(uint256 actorSeed, uint256 amount, uint256 embeddedSeed) external {
        QuintessenceActor actor = actors[actorSeed % ACTOR_COUNT];
        uint256 walletHolds = quint.balance(address(actor));
        if (walletHolds == 0) {
            return;
        }
        uint256 spent = (amount % walletHolds) + 1;
        uint256 embedded = embeddedSeed % (spent + 1);
        uint256 walletsBefore = quint.walletsTotal();
        uint256 embeddedBefore = quint.embeddedTotal();
        uint256 platonicBefore = quint.platonicTotal();
        uint256 mintedBefore = quint.totalEverMinted();

        actor.embedFromWallet(spent, embedded);

        embedFromWalletAttempts += 1;
        embeddedMovementAttempts += 1;
        if (
            quint.walletsTotal() == walletsBefore - spent
                && quint.embeddedTotal() == embeddedBefore + embedded
                && quint.platonicTotal() == platonicBefore + (spent - embedded)
        ) {
            embedFromWalletConserving += 1;
        }
        if (quint.totalEverMinted() == mintedBefore) {
            embeddedMovementsMintingNothing += 1;
        }
        embedFromWalletCalls += 1;
        _snapshot();
    }

    /// Take units out of embeddedTotal, recovering part into a wallet and
    /// returning the rest to platonicTotal, and record every bucket delta.
    function releaseFromEmbedded(uint256 actorSeed, uint256 amount, uint256 recoveredSeed)
        external
    {
        uint256 embeddedBefore = quint.embeddedTotal();
        if (embeddedBefore == 0) {
            return;
        }
        uint256 released = (amount % embeddedBefore) + 1;
        uint256 recovered = recoveredSeed % (released + 1);
        uint256 walletsBefore = quint.walletsTotal();
        uint256 platonicBefore = quint.platonicTotal();
        uint256 mintedBefore = quint.totalEverMinted();

        quint.releaseFromEmbedded(_actor(actorSeed), released, recovered);

        releaseFromEmbeddedAttempts += 1;
        embeddedMovementAttempts += 1;
        if (
            quint.embeddedTotal() == embeddedBefore - released
                && quint.walletsTotal() == walletsBefore + recovered
                && quint.platonicTotal() == platonicBefore + (released - recovered)
        ) {
            releaseFromEmbeddedConserving += 1;
        }
        if (quint.totalEverMinted() == mintedBefore) {
            embeddedMovementsMintingNothing += 1;
        }
        releaseFromEmbeddedCalls += 1;
        _snapshot();
    }

    /// Take units out of embeddedTotal recovering none, and record that every one
    /// of them reached platonicTotal and no wallet was credited.
    function releaseAllToPlatonic(uint256 amount) external {
        uint256 embeddedBefore = quint.embeddedTotal();
        if (embeddedBefore == 0) {
            return;
        }
        uint256 released = (amount % embeddedBefore) + 1;
        uint256 platonicBefore = quint.platonicTotal();
        uint256 walletsBefore = quint.walletsTotal();
        uint256 mintedBefore = quint.totalEverMinted();

        quint.releaseAllToPlatonic(released);

        releaseAllToPlatonicAttempts += 1;
        embeddedMovementAttempts += 1;
        if (
            quint.embeddedTotal() == embeddedBefore - released
                && quint.platonicTotal() == platonicBefore + released
                && quint.walletsTotal() == walletsBefore
        ) {
            releaseAllToPlatonicConserving += 1;
        }
        if (quint.totalEverMinted() == mintedBefore) {
            embeddedMovementsMintingNothing += 1;
        }
        releaseAllToPlatonicCalls += 1;
        _snapshot();
    }

    function intruderDistil(uint256 actorSeed, uint256 amount) external {
        intruder.tryDistil(_actor(actorSeed), (amount % ONE_WHOLE) + 1);
        _snapshot();
    }

    function intruderRespawn(uint256 actorSeed, uint256 amount) external {
        intruder.tryRespawn(_actor(actorSeed), (amount % ONE_WHOLE) + 1);
        _snapshot();
    }

    function intruderExecuteTransfer(uint256 senderSeed, uint256 skillLevel) external {
        intruder.tryExecuteTransfer(_actor(senderSeed), (skillLevel % 10) + 1);
        _snapshot();
    }

    function intruderEmbedFromPlatonic(uint256 amount) external {
        intruder.tryEmbedFromPlatonic((amount % ONE_WHOLE) + 1);
        _snapshot();
    }

    function intruderReleaseFromEmbedded(uint256 actorSeed, uint256 amount) external {
        uint256 released = (amount % ONE_WHOLE) + 1;
        intruder.tryReleaseFromEmbedded(_actor(actorSeed), released, released);
        _snapshot();
    }

    function intruderReleaseAllToPlatonic(uint256 amount) external {
        intruder.tryReleaseAllToPlatonic((amount % ONE_WHOLE) + 1);
        _snapshot();
    }

    /// Sum over every wallet WalletSet has recorded, which is every wallet a
    /// distil, transfer, respawn or release in this run could have credited.
    function recordedWalletSum() external view returns (uint256 total) {
        uint256 recorded = walletSet.count();
        for (uint256 i = 0; i < recorded; ++i) {
            total += quint.balance(walletSet.wallets(i));
        }
    }

    function _actor(uint256 seed) private view returns (address) {
        return address(actors[seed % ACTOR_COUNT]);
    }

    function _snapshot() private {
        uint256 everMinted = quint.totalEverMinted();
        if (everMinted > highEverMinted) {
            highEverMinted = everMinted;
        }
        uint256 bucketSum = quint.walletsTotal() + quint.heldTotal() + quint.platonicTotal()
            + quint.embeddedTotal();
        if (bucketSum > highBucketSum) {
            highBucketSum = bucketSum;
        }
    }
}

contract QuintessenceConservationTest {
    /// 0.00000001 Quintessence in base units, the poorest ore value.
    uint256 private constant ORE_LOW = 10_000_000_000;

    /// 0.00000005 Quintessence in base units, the richest ore value.
    uint256 private constant ORE_HIGH = 50_000_000_000;

    /// 0.00000003, the part of ORE_HIGH that embedFromWallet embeds in setUp.
    uint256 private constant ORE_EMBEDDED_FROM_WALLET = 30_000_000_000;

    /// 0.000000017, the part releaseFromEmbedded recovers in setUp.
    uint256 private constant ORE_RECOVERED = 17_000_000_000;

    /// 0.000000033, what the five ore-scale movements in setUp leave in the platonic.
    uint256 private constant ORE_PLATONIC_GAIN = 33_000_000_000;

    Quintessence public quint;
    QuintessenceHandler public handler;
    QuintessenceIntruder public intruder;

    function setUp() public {
        handler = new QuintessenceHandler();
        intruder = new QuintessenceIntruder();
        quint = new Quintessence(address(handler));
        handler.bind(quint, intruder);
        intruder.bind(quint);

        handler.distil(0, 1_000 * 10**18);
        handler.tryDistilPastCap(0);
        handler.tryExecuteWithoutAuthorization(0);
        handler.intruderDistil(0, 1);
        handler.intruderRespawn(0, 1);
        handler.intruderExecuteTransfer(0, 1);
        handler.intruderEmbedFromPlatonic(1);
        handler.intruderReleaseFromEmbedded(0, 1);
        handler.intruderReleaseAllToPlatonic(1);
        handler.tryExecuteBeforeDue(0);
        handler.authorizeTransfer(0, 0, 500 * 10**18);
        handler.executeTransfer(0, 1);
        uint256 platonicBeforeOre = quint.platonicTotal();
        uint256 walletsBeforeOre = quint.walletsTotal();

        handler.embedFromPlatonic(ORE_LOW - 1);
        require(quint.embeddedTotal() == ORE_LOW, "setUp: the platonic embed was not 0.00000001");

        handler.embedFromWallet(1, ORE_HIGH - 1, ORE_EMBEDDED_FROM_WALLET);
        require(
            quint.embeddedTotal() == ORE_LOW + ORE_EMBEDDED_FROM_WALLET,
            "setUp: the wallet embed was not 0.00000003"
        );

        handler.releaseFromEmbedded(
            1,
            ORE_LOW + ORE_EMBEDDED_FROM_WALLET - 1,
            ORE_RECOVERED
        );
        require(quint.embeddedTotal() == 0, "setUp: the release left units embedded");

        handler.embedFromPlatonic(ORE_LOW - 1);
        handler.releaseAllToPlatonic(ORE_LOW - 1);
        require(quint.embeddedTotal() == 0, "setUp: the full release left units embedded");

        require(
            quint.platonicTotal() == platonicBeforeOre + ORE_PLATONIC_GAIN,
            "setUp: the ore-scale movements did not balance to 0.000000033 in the platonic"
        );
        require(
            quint.walletsTotal() == walletsBeforeOre - ORE_PLATONIC_GAIN,
            "setUp: the ore-scale movements did not take 0.000000033 out of the wallets"
        );
    }

    /// @notice forge drives only the handler, whose wrappers record every wallet.
    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    /// @notice A failure means the four buckets no longer hold every unit minted.
    function invariant_fourBucketsEqualTotalEverMinted() public view {
        require(
            quint.walletsTotal() + quint.heldTotal() + quint.platonicTotal()
                + quint.embeddedTotal() == quint.totalEverMinted(),
            "buckets do not equal totalEverMinted"
        );
    }

    /// @notice A failure means walletsTotal no longer equals what the wallets hold.
    function invariant_walletsTotalEqualsSumOfBalances() public view {
        require(
            handler.recordedWalletSum() == quint.walletsTotal(),
            "walletsTotal does not equal the wallet balances"
        );
    }

    /// @notice A failure means more than 33,000,000 Quintessence has been minted.
    function invariant_totalEverMintedWithinCap() public view {
        require(
            quint.totalEverMinted() <= quint.SUPPLY_CAP(),
            "totalEverMinted is above SUPPLY_CAP"
        );
    }

    /// @notice A failure means totalEverMinted fell, so a mint was undone.
    function invariant_totalEverMintedNeverFalls() public view {
        require(
            quint.totalEverMinted() >= handler.highEverMinted(),
            "totalEverMinted fell below a value already seen"
        );
    }

    /// @notice A failure means the four-bucket sum fell, so a unit was destroyed.
    function invariant_noUnitIsDestroyed() public view {
        require(
            quint.walletsTotal() + quint.heldTotal() + quint.platonicTotal()
                + quint.embeddedTotal() >= handler.highBucketSum(),
            "the bucket sum fell below a value already seen"
        );
    }

    /// @notice A failure means embeddedTotal holds units that were never minted.
    function invariant_embeddedTotalIsWithinTotalEverMinted() public view {
        require(
            quint.embeddedTotal() <= quint.totalEverMinted(),
            "embeddedTotal is above totalEverMinted"
        );
    }

    /// @notice A failure means a mint past SUPPLY_CAP succeeded, or none was tried.
    function invariant_capRefusesAMintPastIt() public view {
        require(handler.capAttempts() > 0, "no mint past the cap was attempted");
        require(handler.capSuccesses() == 0, "a mint past SUPPLY_CAP succeeded");
    }

    /// @notice A failure means a non-registry caller moved units, or none tried.
    function invariant_onlyRegistryMovesUnits() public view {
        require(intruder.attempts() > 0, "no non-registry call was attempted");
        require(
            intruder.refusals() == intruder.attempts(),
            "a non-registry caller was not refused"
        );
    }

    /// @notice A failure means a transfer ran before its duration elapsed, or none was tried.
    function invariant_transferRefusedBeforeItsDurationElapsed() public view {
        require(handler.beforeDueAttempts() > 0, "no early executeTransfer was attempted");
        require(
            handler.beforeDueSuccesses() == 0,
            "a transfer ran before its duration elapsed"
        );
    }

    /// @notice A failure means an executed transfer bled under 4%, or none was executed.
    function invariant_everyTransferBleedsFourPercentOrMore() public view {
        require(handler.transfersExecuted() > 0, "no transfer was executed");
        require(
            handler.transfersBleedingFourPercentOrMore() == handler.transfersExecuted(),
            "a transfer bled less than 4% of the amount sent"
        );
    }

    /// @notice A failure means the registry moved a wallet that authorized nothing.
    function invariant_registryCannotMoveAnUnauthorizedWallet() public view {
        require(
            handler.unauthorizedExecuteAttempts() > 0,
            "no unauthorized executeTransfer was attempted"
        );
        require(
            handler.unauthorizedExecuteSuccesses() == 0,
            "the registry moved a wallet that authorized nothing"
        );
    }

    /// @notice A failure means an embed took units from somewhere other than the platonic.
    function invariant_everyEmbedFromPlatonicDrawsOnlyFromThePlatonic() public view {
        require(handler.embedFromPlatonicAttempts() > 0, "no embedFromPlatonic was attempted");
        require(
            handler.embedFromPlatonicConserving() == handler.embedFromPlatonicAttempts(),
            "an embed did not move its units out of platonicTotal into embeddedTotal"
        );
    }

    /// @notice A failure means an embed's units did not all reach embedded or the platonic.
    function invariant_everyEmbedFromWalletMovesEveryUnitItSpends() public view {
        require(handler.embedFromWalletAttempts() > 0, "no embedFromWallet was attempted");
        require(
            handler.embedFromWalletConserving() == handler.embedFromWalletAttempts(),
            "an embed did not move every unit it spent into embeddedTotal or platonicTotal"
        );
    }

    /// @notice A failure means a release's units did not all reach a wallet or the platonic.
    function invariant_everyReleaseMovesEveryUnitItTakesFromEmbedded() public view {
        require(handler.releaseFromEmbeddedAttempts() > 0, "no release was attempted");
        require(
            handler.releaseFromEmbeddedConserving() == handler.releaseFromEmbeddedAttempts(),
            "a release did not move every unit into a wallet or platonicTotal"
        );
    }

    /// @notice A failure means a release recovering nothing lost units instead of returning them.
    function invariant_everyReleaseAllToPlatonicReturnsEveryUnit() public view {
        require(
            handler.releaseAllToPlatonicAttempts() > 0,
            "no releaseAllToPlatonic was attempted"
        );
        require(
            handler.releaseAllToPlatonicConserving() == handler.releaseAllToPlatonicAttempts(),
            "a release recovering nothing did not return every unit to platonicTotal"
        );
    }

    /// @notice A failure means an embed or a release changed totalEverMinted.
    function invariant_noEmbeddedMovementMintsAUnit() public view {
        require(handler.embeddedMovementAttempts() > 0, "no embedded movement was attempted");
        require(
            handler.embeddedMovementsMintingNothing() == handler.embeddedMovementAttempts(),
            "an embedded movement changed totalEverMinted"
        );
    }
}
