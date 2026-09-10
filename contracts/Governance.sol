// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — Proof-of-Accumulation governance
// Chain: Base (Coinbase L2)
// =============================================================================
// Four issue levels, one vote per eligible address at every level.
//
// A Quintessence holding buys access to a level and never buys weight inside
// it. castVote adds exactly one to forVotes or againstVotes and reads no
// balance. Quorum is a fraction of the eligible voters counted at that level,
// never a fraction of supply.
//
//   level             holding   quorum  approval  delay
//   1 INFORMATIONAL       1 Q      10%    simple   none
//   2 PATCH              25 Q      20%    simple   2 days
//   3 INTERFACE          75 Q      30%       60%   7 days
//   4 CORE              150 Q      40%       67%   30 days
//
// Two separate gates decide a vote:
//
//   holdings         which issue levels an address may vote on
//   event activity   whether that address has a live vote at all
//
// Trading does not make a vote live. recordEventAction is the only call that
// refreshes an address's activity clock, and only the Quintessence registry
// reaches it. Quintessence.distil raises a balance and touches no clock.
//
// The franchise is a second number beside the balance and it moves no
// Quintessence. franchiseOf is never below the address's current balance:
//
//   franchiseOf(a) >= Quintessence.balance(a), for every address, always
//
// A balance that rises carries the franchise up with it in the same block. A
// balance that falls leaves the franchise at its remembered ceiling until the
// address goes dormant, after which the franchise resynchronizes downward toward
// the balance at one ninetieth of the gap a day and reaches it in 90 days. The
// ramp is continuous rather than stepped, so the rate holds between days too.
//
// The halt council is five elected addresses, three of which halt one named
// mechanism for seven days. It reaches no other function here. No release call
// exists: isHalted reads a timestamp, so a halt ends by itself.
//
// Every deployment stays immutable. A change no vote can make is made by
// deploying a new contract and pointing migration at it on a CORE vote.
// Holders then spend their own units into the migration held address, where
// Quintessence retires them. An address that never spends keeps its units on
// this contract and reaches nothing the new one governs.
// =============================================================================
pragma solidity 0.8.36;

interface IQuintessenceBalances {
    function balance(address wallet) external view returns (uint256);

    function spentInto(address wallet, address heldAddress) external view returns (uint256);

    function REGISTRY() external view returns (address);
}

interface IGovernedRegistry {
    function setPriceFeed(string calldata symbol, address feed) external;

    function priceFeeds(string calldata symbol) external view returns (address);
}

interface IGovernedTrophy {
    function setTierSvg(string calldata tier, string calldata svgBase64) external;
}

/// The one question a halted contract asks Governance before it moves anything.
interface IHaltSource {
    function isHalted(address mechanism) external view returns (bool);
}

contract Governance is IHaltSource {

    // ── Levels ────────────────────────────────────────────────────────────────

    uint8 public constant LEVEL_INFORMATIONAL = 1;
    uint8 public constant LEVEL_PATCH = 2;
    uint8 public constant LEVEL_INTERFACE = 3;
    uint8 public constant LEVEL_CORE = 4;

    uint256 public constant HOLDING_INFORMATIONAL = 1 * 10**18;
    uint256 public constant HOLDING_PATCH = 25 * 10**18;
    uint256 public constant HOLDING_INTERFACE = 75 * 10**18;
    uint256 public constant HOLDING_CORE = 150 * 10**18;

    uint256 public constant QUORUM_BPS_INFORMATIONAL = 1_000;
    uint256 public constant QUORUM_BPS_PATCH = 2_000;
    uint256 public constant QUORUM_BPS_INTERFACE = 3_000;
    uint256 public constant QUORUM_BPS_CORE = 4_000;

    uint256 public constant APPROVAL_BPS_SIMPLE = 5_000;
    uint256 public constant APPROVAL_BPS_INTERFACE = 6_000;
    uint256 public constant APPROVAL_BPS_CORE = 6_700;

    uint256 public constant DELAY_INFORMATIONAL = 0;
    uint256 public constant DELAY_PATCH = 2 days;
    uint256 public constant DELAY_INTERFACE = 7 days;
    uint256 public constant DELAY_CORE = 30 days;

    uint256 public constant BPS_DENOMINATOR = 10_000;

    // ── Dormancy ──────────────────────────────────────────────────────────────

    /// An address's franchise ceiling stands for this long after its last
    /// event-anchored action, then resynchronization begins.
    uint256 public constant HOLD_SECONDS = 90 days;

    /// Dormancy that closes the whole gap between ceiling and balance, so the
    /// rate is one ninetieth of the gap a day.
    uint256 public constant RESYNC_SECONDS = 90 days;

    // ── Halt council ──────────────────────────────────────────────────────────

    uint256 public constant COUNCIL_SIZE = 5;
    uint256 public constant HALT_SIGNALS_REQUIRED = 3;
    uint256 public constant HALT_SECONDS = 7 days;

    // ── Immutable wiring ──────────────────────────────────────────────────────

    IQuintessenceBalances public immutable QUINT;
    IGovernedRegistry public immutable REGISTRY;
    IGovernedTrophy public immutable TROPHY;
    address public immutable TOKEN;

    /// The Quintessence registry, and the only recordEventAction caller.
    address public immutable EVENT_RECORDER;

    // ── Franchise state ───────────────────────────────────────────────────────

    struct Franchise {
        /// The remembered maximum, in base units. Never below the address's balance.
        uint256 ceiling;
        /// When resynchronization started for the current ceiling, zero when none runs.
        uint256 resyncStartedAt;
        uint256 lastEventActionAt;
        /// The level this address counted toward at its last sync, zero for none.
        uint8 syncedLevel;
    }

    mapping(address => Franchise) public franchise;

    /// How many roster addresses counted toward each level at their last sync.
    mapping(uint8 => uint256) public levelMemberCount;

    address[] public roster;
    mapping(address => bool) public onRoster;

    // ── Proposal state ────────────────────────────────────────────────────────

    enum Action { SetPriceFeed, SetTierSvg, ElectHaltCouncil, SetMigration }

    struct Proposal {
        address proposer;
        Action action;
        uint8 level;
        bool executed;
        uint256 openedAt;
        uint256 eligibleAtOpen;
        uint256 forVotes;
        uint256 againstVotes;
        bytes payload;
    }

    Proposal[] private _proposals;

    mapping(uint256 => mapping(address => bool)) public hasVoted;

    // ── Halt state ────────────────────────────────────────────────────────────

    address[COUNCIL_SIZE] public haltCouncil;
    mapping(address => bool) public onHaltCouncil;

    /// Raised by each election, so a new council signals from a clean slate.
    uint256 public councilEpoch;

    mapping(address => uint256) public haltExpiresAt;
    mapping(address => uint256) public haltRaisedInEpoch;
    mapping(address => mapping(uint256 => mapping(address => bool))) public haltSignalled;
    mapping(address => mapping(uint256 => uint256)) public haltSignalCount;

    // ── Migration state ───────────────────────────────────────────────────────

    address public migrationTarget;
    address public migrationHeldAddress;

    // ── Events ────────────────────────────────────────────────────────────────

    event FranchiseSynced(address indexed holder, uint256 ceiling, uint256 balanceNow);

    event EventActionRecorded(address indexed holder, uint256 actedAt, uint256 ceiling);

    event ProposalOpened(uint256 indexed id, Action action, uint8 level, uint256 eligibleAtOpen);

    event VoteCast(uint256 indexed id, address indexed voter, bool support, uint256 weight);

    event ProposalExecuted(uint256 indexed id, Action action, uint8 level);

    event HaltCouncilElected(uint256 indexed epoch, address[] council);

    event HaltSignalled(address indexed mechanism, address indexed member, uint256 signals);

    event HaltRaised(address indexed mechanism, uint256 expiresAt, uint256 epoch);

    event MigrationSet(address indexed target, address indexed heldAddress);

    // ── Constructor ───────────────────────────────────────────────────────────

    /**
     * @notice Name the Quintessence contract and the three contracts a vote
     *         reaches, permanently.
     * @param quintessence The Quintessence contract read for every balance.
     * @param registry The CompetitionRegistry whose price feeds a vote sets.
     * @param trophy The AcervatorTrophy whose tier art a vote sets.
     * @param token The ACRV token, haltable but holding no governed setter.
     */
    constructor(address quintessence, address registry, address trophy, address token) {
        require(quintessence.code.length > 0, "Gov: quint no code");
        require(registry.code.length > 0, "Gov: registry no code");
        require(trophy.code.length > 0, "Gov: trophy no code");
        require(token.code.length > 0, "Gov: token no code");

        QUINT = IQuintessenceBalances(quintessence);
        REGISTRY = IGovernedRegistry(registry);
        TROPHY = IGovernedTrophy(trophy);
        TOKEN = token;

        address recorder = IQuintessenceBalances(quintessence).REGISTRY();
        require(recorder != address(0), "Gov: quint names no registry");
        EVENT_RECORDER = recorder;
    }

    // ── The four levels, read one figure at a time ────────────────────────────

    /// @notice Return the Quintessence a voter must hold to reach this level.
    function holdingFor(uint8 level) public pure returns (uint256) {
        if (level == LEVEL_INFORMATIONAL) return HOLDING_INFORMATIONAL;
        if (level == LEVEL_PATCH) return HOLDING_PATCH;
        if (level == LEVEL_INTERFACE) return HOLDING_INTERFACE;
        if (level == LEVEL_CORE) return HOLDING_CORE;
        revert("Gov: level out of range");
    }

    /// @notice Return the fraction of eligible voters a vote at this level needs.
    function quorumBpsFor(uint8 level) public pure returns (uint256) {
        if (level == LEVEL_INFORMATIONAL) return QUORUM_BPS_INFORMATIONAL;
        if (level == LEVEL_PATCH) return QUORUM_BPS_PATCH;
        if (level == LEVEL_INTERFACE) return QUORUM_BPS_INTERFACE;
        if (level == LEVEL_CORE) return QUORUM_BPS_CORE;
        revert("Gov: level out of range");
    }

    /// @notice Return the fraction of votes cast that must be in favour.
    function approvalBpsFor(uint8 level) public pure returns (uint256) {
        if (level == LEVEL_INFORMATIONAL) return APPROVAL_BPS_SIMPLE;
        if (level == LEVEL_PATCH) return APPROVAL_BPS_SIMPLE;
        if (level == LEVEL_INTERFACE) return APPROVAL_BPS_INTERFACE;
        if (level == LEVEL_CORE) return APPROVAL_BPS_CORE;
        revert("Gov: level out of range");
    }

    /// @notice Return how long a proposal at this level stays open before execution.
    function delaySecondsFor(uint8 level) public pure returns (uint256) {
        if (level == LEVEL_INFORMATIONAL) return DELAY_INFORMATIONAL;
        if (level == LEVEL_PATCH) return DELAY_PATCH;
        if (level == LEVEL_INTERFACE) return DELAY_INTERFACE;
        if (level == LEVEL_CORE) return DELAY_CORE;
        revert("Gov: level out of range");
    }

    // ── The franchise ─────────────────────────────────────────────────────────

    /**
     * @notice Return the address's franchise at this block, in base units.
     * @dev The return is at or above QUINT.balance(holder) on every input,
     *      because the ceiling branch floors at the balance and the two other
     *      branches return the balance itself.
     * @param holder The address read.
     * @return The franchise, which moves no Quintessence.
     */
    function franchiseOf(address holder) public view returns (uint256) {
        Franchise storage held = franchise[holder];
        uint256 balanceNow = QUINT.balance(holder);
        uint256 ceiling = held.ceiling;
        if (ceiling <= balanceNow) {
            return balanceNow;
        }

        uint256 startedAt = held.resyncStartedAt;
        if (startedAt == 0) {
            if (held.lastEventActionAt == 0) {
                return ceiling;
            }
            startedAt = held.lastEventActionAt + HOLD_SECONDS;
        }
        if (block.timestamp <= startedAt) {
            return ceiling;
        }

        uint256 dormantFor = block.timestamp - startedAt;
        if (dormantFor >= RESYNC_SECONDS) {
            return balanceNow;
        }
        return ceiling - ((ceiling - balanceNow) * dormantFor) / RESYNC_SECONDS;
    }

    /// @notice Return whether this address has ever acted inside a PoA event.
    /// @dev A zero lastEventActionAt is the never-acted sentinel, so the read
    ///      compares rather than equates.
    function isVoteLive(address holder) public view returns (bool) {
        return franchise[holder].lastEventActionAt > 0;
    }

    /**
     * @notice Return the highest issue level this address may vote on, or zero.
     * @param holder The address read.
     * @return Four, three, two, one, or zero for no level.
     */
    function issueLevelOf(address holder) public view returns (uint8) {
        if (!isVoteLive(holder)) {
            return 0;
        }
        uint256 settled = franchiseOf(holder);
        if (settled >= HOLDING_CORE) return LEVEL_CORE;
        if (settled >= HOLDING_INTERFACE) return LEVEL_INTERFACE;
        if (settled >= HOLDING_PATCH) return LEVEL_PATCH;
        if (settled >= HOLDING_INFORMATIONAL) return LEVEL_INFORMATIONAL;
        return 0;
    }

    /**
     * @notice Write the address's franchise and level counters from its balance
     *         and its dormancy, moving no Quintessence.
     * @param holder The address synced. Any caller may sync any address.
     */
    function syncFranchise(address holder) public {
        require(holder != address(0), "Gov: holder is zero");
        Franchise storage held = franchise[holder];
        uint256 settled = franchiseOf(holder);
        uint256 balanceNow = QUINT.balance(holder);

        if (settled <= balanceNow) {
            held.ceiling = balanceNow;
            held.resyncStartedAt = 0;
        } else if (held.resyncStartedAt == 0 && held.lastEventActionAt != 0) {
            uint256 dormantFrom = held.lastEventActionAt + HOLD_SECONDS;
            if (block.timestamp > dormantFrom) {
                held.resyncStartedAt = dormantFrom;
            }
        }

        _joinRoster(holder);
        _recountLevel(holder);

        emit FranchiseSynced(holder, held.ceiling, balanceNow);
    }

    /**
     * @notice Refresh the address's activity clock after one action inside a
     *         PoA event, banking whatever the resynchronization already closed.
     * @param holder The address that acted.
     */
    function recordEventAction(address holder) external {
        require(msg.sender == EVENT_RECORDER, "Gov: caller not event recorder");
        require(holder != address(0), "Gov: holder is zero");

        Franchise storage held = franchise[holder];
        uint256 settled = franchiseOf(holder);
        if (settled < held.ceiling) {
            held.ceiling = settled;
        }
        held.resyncStartedAt = 0;
        held.lastEventActionAt = block.timestamp;

        _joinRoster(holder);
        _recountLevel(holder);

        emit EventActionRecorded(holder, block.timestamp, held.ceiling);
    }

    /// @notice Return how many roster addresses last synced at or above this level.
    function eligibleVoterCount(uint8 level) public view returns (uint256 total) {
        for (uint8 candidate = level; candidate <= LEVEL_CORE; ++candidate) {
            total += levelMemberCount[candidate];
        }
    }

    function rosterCount() external view returns (uint256) {
        return roster.length;
    }

    // ── Proposals ─────────────────────────────────────────────────────────────

    /**
     * @notice Return the level a vote on this action and payload must run at.
     * @dev A price feed for a symbol that holds none is an addition and runs at
     *      INTERFACE. Repointing a symbol that already holds one changes what
     *      every award is measured against and runs at CORE.
     * @param action The action proposed.
     * @param payload Its encoded arguments.
     * @return The required level.
     */
    function requiredLevel(Action action, bytes memory payload) public view returns (uint8) {
        if (action == Action.SetPriceFeed) {
            (string memory symbol,) = abi.decode(payload, (string, address));
            return REGISTRY.priceFeeds(symbol) == address(0) ? LEVEL_INTERFACE : LEVEL_CORE;
        }
        if (action == Action.SetTierSvg) {
            return LEVEL_INTERFACE;
        }
        if (action == Action.ElectHaltCouncil) {
            return LEVEL_PATCH;
        }
        return LEVEL_CORE;
    }

    /**
     * @notice Open a proposal at the level its own action and payload require.
     * @param action The action a passed vote executes.
     * @param payload Its encoded arguments.
     * @return id The proposal identifier.
     */
    function propose(Action action, bytes calldata payload) external returns (uint256 id) {
        uint8 level = requiredLevel(action, payload);
        require(issueLevelOf(msg.sender) >= level, "Gov: proposer below level");
        _checkPayload(action, payload);

        uint256 eligible = eligibleVoterCount(level);
        require(eligible > 0, "Gov: no eligible voters");

        id = _proposals.length;
        _proposals.push(
            Proposal({
                action: action,
                level: level,
                proposer: msg.sender,
                openedAt: block.timestamp,
                eligibleAtOpen: eligible,
                forVotes: 0,
                againstVotes: 0,
                executed: false,
                payload: payload
            })
        );

        emit ProposalOpened(id, action, level, eligible);
    }

    /**
     * @notice Cast this address's one vote on a proposal.
     * @dev The vote adds one. No balance, franchise or holding reaches the
     *      tally, so a large holder and a small holder move it identically.
     * @param id The proposal voted on.
     * @param support True to count toward forVotes.
     */
    function castVote(uint256 id, bool support) external {
        Proposal storage proposal = _proposal(id);
        require(!proposal.executed, "Gov: proposal executed");
        require(!hasVoted[id][msg.sender], "Gov: already voted");
        require(issueLevelOf(msg.sender) >= proposal.level, "Gov: voter below level");

        hasVoted[id][msg.sender] = true;
        if (support) {
            ++proposal.forVotes;
        } else {
            ++proposal.againstVotes;
        }

        emit VoteCast(id, msg.sender, support, 1);
    }

    /// @notice Return whether the proposal has met its quorum of eligible voters.
    function quorumReached(uint256 id) public view returns (bool) {
        Proposal storage proposal = _proposal(id);
        uint256 cast = proposal.forVotes + proposal.againstVotes;
        return cast * BPS_DENOMINATOR >= proposal.eligibleAtOpen * quorumBpsFor(proposal.level);
    }

    /// @notice Return whether the proposal has met its approval fraction.
    function approvalReached(uint256 id) public view returns (bool) {
        Proposal storage proposal = _proposal(id);
        uint256 cast = proposal.forVotes + proposal.againstVotes;
        if (cast == 0) {
            return false;
        }
        return proposal.forVotes > proposal.againstVotes
            && proposal.forVotes * BPS_DENOMINATOR >= cast * approvalBpsFor(proposal.level);
    }

    /// @notice Return whether the proposal's delay has elapsed since it opened.
    function delayElapsed(uint256 id) public view returns (bool) {
        Proposal storage proposal = _proposal(id);
        return block.timestamp >= proposal.openedAt + delaySecondsFor(proposal.level);
    }

    /**
     * @notice Execute a proposal that has met its quorum, its approval and its delay.
     * @param id The proposal executed.
     */
    function execute(uint256 id) external {
        Proposal storage proposal = _proposal(id);
        require(!proposal.executed, "Gov: proposal executed");
        require(delayElapsed(id), "Gov: delay not elapsed");
        require(quorumReached(id), "Gov: quorum not reached");
        require(approvalReached(id), "Gov: approval not reached");

        proposal.executed = true;
        Action action = proposal.action;
        bytes memory payload = proposal.payload;
        emit ProposalExecuted(id, action, proposal.level);

        if (action == Action.SetPriceFeed) {
            (string memory symbol, address feed) = abi.decode(payload, (string, address));
            REGISTRY.setPriceFeed(symbol, feed);
        } else if (action == Action.SetTierSvg) {
            (string memory tier, string memory svgBase64) = abi.decode(payload, (string, string));
            TROPHY.setTierSvg(tier, svgBase64);
        } else if (action == Action.ElectHaltCouncil) {
            _seatCouncil(abi.decode(payload, (address[])));
        } else {
            (address target, address heldAddress) = abi.decode(payload, (address, address));
            migrationTarget = target;
            migrationHeldAddress = heldAddress;
            emit MigrationSet(target, heldAddress);
        }
    }

    function proposalCount() external view returns (uint256) {
        return _proposals.length;
    }

    /**
     * @notice Return a proposal's action, level, tally and eligible snapshot.
     * @param id The proposal read.
     * @return action The action a passed vote executes.
     * @return level The issue level it runs at.
     * @return forVotes Votes in favour, one per voter.
     * @return againstVotes Votes against, one per voter.
     * @return eligibleAtOpen Eligible voters counted when it opened.
     * @return executed Whether it has executed.
     */
    function proposalAt(uint256 id)
        external
        view
        returns (
            Action action,
            uint8 level,
            uint256 forVotes,
            uint256 againstVotes,
            uint256 eligibleAtOpen,
            bool executed
        )
    {
        Proposal storage proposal = _proposal(id);
        action = proposal.action;
        level = proposal.level;
        forVotes = proposal.forVotes;
        againstVotes = proposal.againstVotes;
        eligibleAtOpen = proposal.eligibleAtOpen;
        executed = proposal.executed;
    }

    // ── The halt council ──────────────────────────────────────────────────────

    /**
     * @notice Signal a halt on one named mechanism as a sitting council member.
     * @dev The third distinct signal of the sitting council starts the halt. A
     *      council that has already halted this mechanism cannot halt it again,
     *      so a renewal needs a PATCH vote seating a different council.
     * @param mechanism The token, the registry or the trophy.
     */
    function signalHalt(address mechanism) external {
        require(onHaltCouncil[msg.sender], "Gov: caller not on council");
        require(_isHaltableMechanism(mechanism), "Gov: mechanism not haltable");
        require(block.timestamp >= haltExpiresAt[mechanism], "Gov: mechanism already halted");
        require(haltRaisedInEpoch[mechanism] != councilEpoch, "Gov: council already halted it");
        require(!haltSignalled[mechanism][councilEpoch][msg.sender], "Gov: already signalled");

        haltSignalled[mechanism][councilEpoch][msg.sender] = true;
        uint256 signals = haltSignalCount[mechanism][councilEpoch] + 1;
        haltSignalCount[mechanism][councilEpoch] = signals;

        emit HaltSignalled(mechanism, msg.sender, signals);

        if (signals >= HALT_SIGNALS_REQUIRED) {
            haltExpiresAt[mechanism] = block.timestamp + HALT_SECONDS;
            haltRaisedInEpoch[mechanism] = councilEpoch;
            emit HaltRaised(mechanism, haltExpiresAt[mechanism], councilEpoch);
        }
    }

    /**
     * @notice Return whether this mechanism is halted at this block.
     * @dev No call lifts a halt. The window closes when the timestamp passes.
     * @param mechanism The contract asking.
     */
    function isHalted(address mechanism) external view override returns (bool) {
        return block.timestamp < haltExpiresAt[mechanism];
    }

    function haltCouncilMembers() external view returns (address[COUNCIL_SIZE] memory) {
        return haltCouncil;
    }

    // ── Migration ─────────────────────────────────────────────────────────────

    /**
     * @notice Return the units this address has spent into the migration address.
     * @dev Zero means the address is still wholly on this contract.
     * @param holder The address read.
     */
    function migratedUnits(address holder) external view returns (uint256) {
        if (migrationHeldAddress == address(0)) {
            return 0;
        }
        return QUINT.spentInto(holder, migrationHeldAddress);
    }

    // ── Internals ─────────────────────────────────────────────────────────────

    function _proposal(uint256 id) private view returns (Proposal storage) {
        require(id < _proposals.length, "Gov: no such proposal");
        return _proposals[id];
    }

    function _isHaltableMechanism(address mechanism) private view returns (bool) {
        return mechanism == TOKEN || mechanism == address(REGISTRY) || mechanism == address(TROPHY);
    }

    function _joinRoster(address holder) private {
        if (onRoster[holder]) {
            return;
        }
        if (franchise[holder].ceiling > 0 || isVoteLive(holder)) {
            onRoster[holder] = true;
            roster.push(holder);
        }
    }

    /// @dev The decrement and the increment cancel when the level has not moved,
    ///      so no comparison of the two levels is needed.
    function _recountLevel(address holder) private {
        uint8 previous = franchise[holder].syncedLevel;
        uint8 current = issueLevelOf(holder);
        if (previous > 0) {
            --levelMemberCount[previous];
        }
        if (current > 0) {
            ++levelMemberCount[current];
        }
        franchise[holder].syncedLevel = current;
    }

    function _seatCouncil(address[] memory council) private {
        require(council.length == COUNCIL_SIZE, "Gov: council not five");
        for (uint256 i = 0; i < COUNCIL_SIZE; ++i) {
            require(council[i] != address(0), "Gov: council member is zero");
            onHaltCouncil[haltCouncil[i]] = false;
        }
        for (uint256 i = 0; i < COUNCIL_SIZE; ++i) {
            for (uint256 j = i + 1; j < COUNCIL_SIZE; ++j) {
                require(council[i] != council[j], "Gov: council member repeated");
            }
            haltCouncil[i] = council[i];
            onHaltCouncil[council[i]] = true;
        }
        ++councilEpoch;
        emit HaltCouncilElected(councilEpoch, council);
    }

    function _checkPayload(Action action, bytes calldata payload) private pure {
        if (action == Action.SetPriceFeed) {
            (string memory symbol, address feed) = abi.decode(payload, (string, address));
            require(bytes(symbol).length > 0, "Gov: symbol is empty");
            require(feed != address(0), "Gov: feed is zero");
        } else if (action == Action.SetTierSvg) {
            (string memory tier, string memory svgBase64) = abi.decode(payload, (string, string));
            require(bytes(tier).length > 0, "Gov: tier is empty");
            require(bytes(svgBase64).length > 0, "Gov: svg is empty");
        } else if (action == Action.ElectHaltCouncil) {
            require(abi.decode(payload, (address[])).length == COUNCIL_SIZE, "Gov: council not five");
        } else {
            (address target, address heldAddress) = abi.decode(payload, (address, address));
            require(target != address(0), "Gov: migration target is zero");
            require(heldAddress != address(0), "Gov: migration held is zero");
        }
    }
}
