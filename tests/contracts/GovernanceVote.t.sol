// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — the four issue levels, the halt council, and migration
// =============================================================================
// The test contract is the Quintessence registry, so it distils the holdings and
// records the event actions that make a vote live. It is also DEPLOYER and
// OPERATIONS on the three governed contracts, which is what lets a refusal test
// drive the most privileged caller left and watch it refused.
//
// Four holdings are distilled, and the disparity is the point: bigHolder holds
// 10,000 Quintessence and smallHolder holds 150, the CORE threshold. Each moves
// a tally by one. Two small holders outvote one large one.
//
//   bigHolder        10,000 Q   CORE
//   smallHolder         150 Q   CORE
//   thirdVoter          150 Q   CORE
//   interfaceHolder      75 Q   INTERFACE
//
// So eligibleVoterCount(CORE) is 3 and eligibleVoterCount(INTERFACE) is 4, while
// the supply behind them is 10,475 Quintessence. The two numbers are unrelated
// and only the voter count reaches a quorum.
// =============================================================================
pragma solidity 0.8.36;

import {ACRV} from "../../contracts/ACRV.sol";
import {AcervatorTrophy} from "../../contracts/AcervatorTrophy.sol";
import {CompetitionRegistry} from "../../contracts/CompetitionRegistry.sol";
import {Governance} from "../../contracts/Governance.sol";
import {Quintessence} from "../../contracts/Quintessence.sol";

interface Vm {
    function warp(uint256 newTimestamp) external;

    function prank(address sender) external;
}

contract GovernanceVoteTest {
    uint256 private constant ONE_WHOLE = 10**18;

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant BTC_FEED = address(0xB7C);
    address private constant ETH_FEED = address(0xE7C);
    address private constant NEW_FEED = address(0xFEED);
    address private constant MIGRATION_TARGET = address(0x4E1D);
    address private constant MIGRATION_HELD = address(0x9914);

    ACRV public acrv;
    CompetitionRegistry public registry;
    AcervatorTrophy public trophy;
    Quintessence public quint;
    Governance public gov;

    address public bigHolder = address(0xB16);
    address public smallHolder = address(0x5A11);
    address public thirdVoter = address(0x3D);
    address public interfaceHolder = address(0x1F3);

    address[] private _council;

    function setUp() public {
        VM.warp(1_800_000_000);

        acrv = new ACRV();
        registry = new CompetitionRegistry(address(acrv), BTC_FEED, ETH_FEED);
        acrv.setRegistry(address(registry));
        trophy = new AcervatorTrophy(address(registry));

        quint = new Quintessence(address(this));
        gov = new Governance(address(quint), address(registry), address(trophy), address(acrv));

        acrv.setGovernance(address(gov));
        registry.setGovernance(address(gov));
        trophy.setGovernance(address(gov));

        trophy.setTierSvg("Ekthelius", "c3Zn");

        _enrol(bigHolder, 10_000 * ONE_WHOLE);
        _enrol(smallHolder, 150 * ONE_WHOLE);
        _enrol(thirdVoter, 150 * ONE_WHOLE);
        _enrol(interfaceHolder, 75 * ONE_WHOLE);

        _council = new address[](5);
        _council[0] = address(0xC1);
        _council[1] = address(0xC2);
        _council[2] = address(0xC3);
        _council[3] = address(0xC4);
        _council[4] = address(0xC5);
    }

    // ── The four levels ───────────────────────────────────────────────────────

    /// @notice A failure means a level's holding threshold is not the figure decided.
    function test_the_four_levels_carry_the_holdings_decided() public view {
        require(gov.holdingFor(1) == 1 * ONE_WHOLE, "INFORMATIONAL is not 1 Q");
        require(gov.holdingFor(2) == 25 * ONE_WHOLE, "PATCH is not 25 Q");
        require(gov.holdingFor(3) == 75 * ONE_WHOLE, "INTERFACE is not 75 Q");
        require(gov.holdingFor(4) == 150 * ONE_WHOLE, "CORE is not 150 Q");
    }

    /// @notice A failure means a level's quorum fraction is not the figure decided.
    function test_the_four_levels_carry_the_quorums_decided() public view {
        require(gov.quorumBpsFor(1) == 1_000, "INFORMATIONAL quorum is not 10%");
        require(gov.quorumBpsFor(2) == 2_000, "PATCH quorum is not 20%");
        require(gov.quorumBpsFor(3) == 3_000, "INTERFACE quorum is not 30%");
        require(gov.quorumBpsFor(4) == 4_000, "CORE quorum is not 40%");
    }

    /// @notice A failure means a level's approval fraction is not the figure decided.
    function test_the_four_levels_carry_the_approvals_decided() public view {
        require(gov.approvalBpsFor(1) == 5_000, "INFORMATIONAL approval is not simple");
        require(gov.approvalBpsFor(2) == 5_000, "PATCH approval is not simple");
        require(gov.approvalBpsFor(3) == 6_000, "INTERFACE approval is not 60%");
        require(gov.approvalBpsFor(4) == 6_700, "CORE approval is not 67%");
    }

    /// @notice A failure means a level's delay is not the figure decided.
    function test_the_four_levels_carry_the_delays_decided() public view {
        require(gov.delaySecondsFor(1) == 0, "INFORMATIONAL delay is not none");
        require(gov.delaySecondsFor(2) == 2 days, "PATCH delay is not 2 days");
        require(gov.delaySecondsFor(3) == 7 days, "INTERFACE delay is not 7 days");
        require(gov.delaySecondsFor(4) == 30 days, "CORE delay is not 30 days");
    }

    // ── A vote is never weighted by the holding ───────────────────────────────

    /// @notice A failure means a holding reached the tally, so votes carry weight.
    function test_a_large_holder_and_a_small_holder_each_move_the_tally_by_one() public {
        require(
            quint.balance(bigHolder) / quint.balance(smallHolder) >= 66,
            "the two holdings are not far enough apart to see weighting"
        );

        uint256 id = _proposeMigration(bigHolder);

        VM.prank(bigHolder);
        gov.castVote(id, true);
        (,, uint256 forAfterBig, uint256 againstAfterBig,,) = gov.proposalAt(id);
        require(forAfterBig == 1, "the large holder did not add exactly one");
        require(againstAfterBig == 0, "the large holder added an against vote");

        VM.prank(smallHolder);
        gov.castVote(id, true);
        (,, uint256 forAfterSmall,,,) = gov.proposalAt(id);
        require(forAfterSmall == 2, "the small holder did not add exactly one");
    }

    /// @notice A failure means a large holder outvoted two small ones.
    function test_two_small_holders_outvote_one_large_holder() public {
        uint256 id = _proposeCouncil(bigHolder);

        VM.prank(bigHolder);
        gov.castVote(id, false);
        VM.prank(smallHolder);
        gov.castVote(id, true);

        (,, uint256 forVotes, uint256 againstVotes,,) = gov.proposalAt(id);
        require(forVotes == 1 && againstVotes == 1, "the tally is not one against one");
        require(
            !gov.approvalReached(id),
            "a tied tally passed, so one side carried more than one vote"
        );

        VM.prank(thirdVoter);
        gov.castVote(id, true);
        (,, uint256 forFinal, uint256 againstFinal,,) = gov.proposalAt(id);
        require(forFinal == 2 && againstFinal == 1, "the third vote did not land");
        require(
            gov.approvalReached(id),
            "two small holders did not outvote the large holder"
        );
    }

    /// @notice A failure means one address voted twice on one proposal.
    function test_an_address_votes_once_on_a_proposal() public {
        uint256 id = _proposeMigration(bigHolder);

        VM.prank(bigHolder);
        gov.castVote(id, true);

        VM.prank(bigHolder);
        try gov.castVote(id, true) {
            revert("the same address voted twice");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: already voted"),
                "the second vote was refused for some other reason"
            );
        }

        (,, uint256 forVotes,,,) = gov.proposalAt(id);
        require(forVotes == 1, "the refused second vote still raised the tally");
    }

    // ── Quorum counts voters, never supply ────────────────────────────────────

    /// @notice A failure means a quorum denominator moved with the supply.
    function test_quorum_counts_eligible_voters_and_not_supply() public {
        require(gov.eligibleVoterCount(4) == 3, "CORE does not count three voters");
        require(gov.eligibleVoterCount(3) == 4, "INTERFACE does not count four voters");
        uint256 mintedBefore = quint.totalEverMinted();
        require(mintedBefore == 10_375 * ONE_WHOLE, "the distilled supply is not 10,375 Q");

        quint.distil(bigHolder, 1_000_000 * ONE_WHOLE);
        gov.syncFranchise(bigHolder);

        require(
            quint.totalEverMinted() > mintedBefore * 96,
            "the control did not raise the supply far enough to see a supply quorum"
        );
        require(
            gov.eligibleVoterCount(4) == 3,
            "a quorum denominator moved when the supply moved"
        );
    }

    /// @notice A failure means a CORE proposal's eligible snapshot is not the voters.
    function test_a_core_proposal_snapshots_three_eligible_voters() public {
        uint256 id = _proposeMigration(bigHolder);
        (,,,, uint256 eligibleAtOpen,) = gov.proposalAt(id);
        require(eligibleAtOpen == 3, "the eligible snapshot is not the three CORE voters");
    }

    // ── The level a change runs at follows the change ─────────────────────────

    /// @notice A failure means an addition and a repoint run at the same level.
    function test_a_new_symbol_runs_at_interface_and_a_repoint_runs_at_core() public view {
        require(
            gov.requiredLevel(Governance.Action.SetPriceFeed, abi.encode("SOL/USDT", NEW_FEED)) == 3,
            "a symbol with no feed does not run at INTERFACE"
        );
        require(
            gov.requiredLevel(Governance.Action.SetPriceFeed, abi.encode("BTC/USDT", NEW_FEED)) == 4,
            "repointing a seeded symbol does not run at CORE"
        );
    }

    /// @notice A failure means an INTERFACE holder reached a CORE change.
    function test_an_interface_holder_cannot_propose_a_repointed_price_feed() public {
        VM.prank(interfaceHolder);
        try gov.propose(Governance.Action.SetPriceFeed, abi.encode("BTC/USDT", NEW_FEED)) {
            revert("an INTERFACE holder proposed a CORE change");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: proposer below level"),
                "the refusal came from somewhere else"
            );
        }

        VM.prank(interfaceHolder);
        uint256 id = gov.propose(Governance.Action.SetPriceFeed, abi.encode("SOL/USDT", NEW_FEED));
        (, uint8 level,,,,) = gov.proposalAt(id);
        require(level == 3, "the INTERFACE addition did not open at INTERFACE");
    }

    /// @notice A failure means an address other than governance set a price feed.
    function test_a_price_feed_moves_on_a_passed_core_vote_and_no_other_way() public {
        try registry.setPriceFeed("BTC/USDT", NEW_FEED) {
            revert("operations set a price feed");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Registry: caller is not governance"),
                "the refusal came from somewhere else"
            );
        }
        require(registry.priceFeeds("BTC/USDT") == BTC_FEED, "the feed moved anyway");

        VM.prank(bigHolder);
        uint256 id = gov.propose(Governance.Action.SetPriceFeed, abi.encode("BTC/USDT", NEW_FEED));
        _carryAtCore(id);

        require(registry.priceFeeds("BTC/USDT") == NEW_FEED, "the passed vote did not set the feed");
    }

    /// @notice A failure means a CORE proposal executed before its thirty days.
    function test_a_core_proposal_is_refused_before_its_thirty_day_delay() public {
        VM.prank(bigHolder);
        uint256 id = gov.propose(Governance.Action.SetPriceFeed, abi.encode("BTC/USDT", NEW_FEED));
        _voteAll(id, true);

        VM.warp(block.timestamp + 30 days - 1);
        require(!gov.delayElapsed(id), "the delay read as elapsed one second early");
        try gov.execute(id) {
            revert("a CORE proposal executed inside its delay");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: delay not elapsed"),
                "the refusal came from somewhere else"
            );
        }

        VM.warp(block.timestamp + 1);
        gov.execute(id);
        require(registry.priceFeeds("BTC/USDT") == NEW_FEED, "the vote did not execute on time");
    }

    /// @notice A failure means a filled tier's art moved without a passed vote.
    function test_a_filled_tier_is_rewritten_only_by_a_passed_interface_vote() public {
        try trophy.setTierSvg("Ekthelius", "bmV3") {
            revert("the deployer rewrote a filled tier");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Trophy: filled tier is governance's"),
                "the refusal came from somewhere else"
            );
        }

        VM.prank(bigHolder);
        uint256 id = gov.propose(Governance.Action.SetTierSvg, abi.encode("Ekthelius", "bmV3"));
        VM.prank(bigHolder);
        gov.castVote(id, true);
        VM.prank(smallHolder);
        gov.castVote(id, true);
        VM.warp(block.timestamp + 7 days);
        gov.execute(id);

        require(
            keccak256(bytes(trophy.getTierSvg("Ekthelius"))) == keccak256("bmV3"),
            "the passed vote did not write the tier art"
        );
    }

    // ── The halt council ──────────────────────────────────────────────────────

    /// @notice A failure means fewer or more than three signals raised a halt.
    function test_three_of_five_council_signals_halt_the_token() public {
        _seatTheCouncil();

        VM.prank(_council[0]);
        gov.signalHalt(address(acrv));
        require(!acrv.isHalted(), "one signal halted the token");

        VM.prank(_council[1]);
        gov.signalHalt(address(acrv));
        require(!acrv.isHalted(), "two signals halted the token");

        VM.prank(_council[2]);
        gov.signalHalt(address(acrv));
        require(acrv.isHalted(), "three signals did not halt the token");

        try acrv.transfer(smallHolder, 0) {
            revert("a transfer ran while the token was halted");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("ACRV: halted by the halt council"),
                "the refusal came from somewhere else"
            );
        }
    }

    /// @notice A failure means an address off the council raised a halt.
    function test_only_a_sitting_council_member_signals_a_halt() public {
        _seatTheCouncil();

        VM.prank(bigHolder);
        try gov.signalHalt(address(acrv)) {
            revert("an address off the council signalled a halt");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: caller not on council"),
                "the refusal came from somewhere else"
            );
        }
    }

    /// @notice A failure means a halt outlived seven days or needed a release call.
    function test_a_halt_expires_after_seven_days_with_no_release_call() public {
        _seatTheCouncil();
        _raiseTheHalt(address(acrv));

        VM.warp(block.timestamp + 7 days - 1);
        require(acrv.isHalted(), "the halt lapsed one second early");

        VM.warp(block.timestamp + 1);
        require(!acrv.isHalted(), "the halt outlived its seven days");
        acrv.transfer(smallHolder, 0);
    }

    /// @notice A failure means the council could lift its own halt early.
    function test_the_council_cannot_lift_its_own_halt() public {
        _seatTheCouncil();
        _raiseTheHalt(address(acrv));

        VM.prank(_council[3]);
        try gov.signalHalt(address(acrv)) {
            revert("a council member reached a halted mechanism again");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: mechanism already halted"),
                "the refusal came from somewhere else"
            );
        }
        require(acrv.isHalted(), "the refused call lifted the halt");
    }

    /// @notice A failure means the same council renewed its own halt.
    function test_the_same_council_cannot_halt_one_mechanism_twice() public {
        _seatTheCouncil();
        _raiseTheHalt(address(acrv));
        VM.warp(block.timestamp + 7 days);
        require(!acrv.isHalted(), "the halt did not expire");

        VM.prank(_council[0]);
        try gov.signalHalt(address(acrv)) {
            revert("the same council halted the token twice");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: council already halted it"),
                "the refusal came from somewhere else"
            );
        }

        VM.prank(_council[0]);
        gov.signalHalt(address(trophy));
        require(
            gov.haltSignalCount(address(trophy), gov.councilEpoch()) == 1,
            "the same council could not halt a mechanism it had not halted"
        );
    }

    /// @notice A failure means the council reached something other than a halt.
    function test_the_halt_council_reaches_nothing_but_a_halt() public {
        _seatTheCouncil();
        address member = _council[0];

        VM.prank(member);
        try gov.propose(Governance.Action.SetPriceFeed, abi.encode("SOL/USDT", NEW_FEED)) {
            revert("a council member opened a proposal");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: proposer below level"),
                "the proposal refusal came from somewhere else"
            );
        }

        VM.prank(member);
        try registry.setPriceFeed("SOL/USDT", NEW_FEED) {
            revert("a council member set a price feed");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Registry: caller is not governance"),
                "the price feed refusal came from somewhere else"
            );
        }

        VM.prank(member);
        try trophy.setTierSvg("Ekthelius", "bmV3") {
            revert("a council member rewrote a tier's art");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Trophy: filled tier is governance's"),
                "the tier art refusal came from somewhere else"
            );
        }

        VM.prank(member);
        try gov.signalHalt(address(quint)) {
            revert("a council member halted the Quintessence contract");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: mechanism not haltable"),
                "the Quintessence refusal came from somewhere else"
            );
        }

        VM.prank(member);
        gov.signalHalt(address(acrv));
        require(
            gov.haltSignalCount(address(acrv), gov.councilEpoch()) == 1,
            "the one call a council member may make was refused"
        );
    }

    // ── Migration ─────────────────────────────────────────────────────────────

    /// @notice A failure means a holder who ignores a migration loses or keeps the wrong thing.
    function test_a_holder_who_ignores_a_migration_keeps_units_on_the_old_contract() public {
        uint256 id = _proposeMigration(bigHolder);
        _carryAtCore(id);

        address held = gov.migrationHeldAddress();
        require(gov.migrationTarget() == MIGRATION_TARGET, "the migration target did not land");
        require(held == MIGRATION_HELD, "the migration held address did not land");

        uint256 bigBefore = quint.balance(bigHolder);

        VM.prank(smallHolder);
        quint.spend(held, 150 * ONE_WHOLE);

        require(gov.migratedUnits(smallHolder) == 150 * ONE_WHOLE, "the mover did not migrate");
        require(quint.balance(smallHolder) == 0, "the mover kept units on the old contract");
        require(gov.migratedUnits(bigHolder) == 0, "the idle holder migrated without acting");
        require(
            quint.balance(bigHolder) == bigBefore,
            "the idle holder's units moved without it acting"
        );
        require(quint.heldBalance(held) == 150 * ONE_WHOLE, "the migrated units did not retire");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _enrol(address holder, uint256 amount) private {
        quint.distil(holder, amount);
        gov.recordEventAction(holder);
        gov.syncFranchise(holder);
    }

    function _proposeMigration(address proposer) private returns (uint256 id) {
        VM.prank(proposer);
        id = gov.propose(
            Governance.Action.SetMigration,
            abi.encode(MIGRATION_TARGET, MIGRATION_HELD)
        );
    }

    function _proposeCouncil(address proposer) private returns (uint256 id) {
        VM.prank(proposer);
        id = gov.propose(Governance.Action.ElectHaltCouncil, abi.encode(_council));
    }

    function _voteAll(uint256 id, bool support) private {
        VM.prank(bigHolder);
        gov.castVote(id, support);
        VM.prank(smallHolder);
        gov.castVote(id, support);
        VM.prank(thirdVoter);
        gov.castVote(id, support);
    }

    function _carryAtCore(uint256 id) private {
        _voteAll(id, true);
        VM.warp(block.timestamp + 30 days);
        gov.execute(id);
    }

    function _seatTheCouncil() private {
        uint256 id = _proposeCouncil(bigHolder);
        VM.prank(bigHolder);
        gov.castVote(id, true);
        VM.warp(block.timestamp + 2 days);
        gov.execute(id);
        require(gov.councilEpoch() == 1, "the council was not seated");
    }

    function _raiseTheHalt(address mechanism) private {
        VM.prank(_council[0]);
        gov.signalHalt(mechanism);
        VM.prank(_council[1]);
        gov.signalHalt(mechanism);
        VM.prank(_council[2]);
        gov.signalHalt(mechanism);
    }
}
