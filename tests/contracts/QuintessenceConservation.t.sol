// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — Quintessence invariants
// =============================================================================
// forge drives QuintessenceHandler with random call sequences and checks every
// invariant_ function after them.
//
// QuintessenceHandler is the registry, so it is the only caller that reaches
// distil, respawn and executeTransfer. Each QuintessenceActor is an ordinary
// holder, and QuintessenceIntruder holds code and is not the registry, so every
// call it makes to those three functions must be refused.
//
// A counting invariant asserts its attempt counter is above zero before it reads
// its refusal counter, so a path no sequence reached fails instead of passing on
// an absence.
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

    uint256 public distilCalls;
    uint256 public spendCalls;
    uint256 public authorizeCalls;
    uint256 public executeCalls;
    uint256 public respawnCalls;
    uint256 public cancelCalls;

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

    /// Sum over every wallet WalletSet has recorded, which is every wallet a
    /// distil, transfer or respawn in this run could have credited.
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
        uint256 bucketSum = quint.walletsTotal() + quint.heldTotal() + quint.platonicTotal();
        if (bucketSum > highBucketSum) {
            highBucketSum = bucketSum;
        }
    }
}

contract QuintessenceConservationTest {
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
        handler.tryExecuteBeforeDue(0);
        handler.authorizeTransfer(0, 0, 500 * 10**18);
        handler.executeTransfer(0, 1);
    }

    /// @notice A failure means the three buckets no longer hold every unit minted.
    function invariant_threeBucketsEqualTotalEverMinted() public view {
        require(
            quint.walletsTotal() + quint.heldTotal() + quint.platonicTotal()
                == quint.totalEverMinted(),
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

    /// @notice A failure means the bucket sum fell, so a unit was destroyed.
    function invariant_noUnitIsDestroyed() public view {
        require(
            quint.walletsTotal() + quint.heldTotal() + quint.platonicTotal()
                >= handler.highBucketSum(),
            "the bucket sum fell below a value already seen"
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
}
