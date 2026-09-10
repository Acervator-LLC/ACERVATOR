// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — the franchise, dormancy, and the activity clock
// =============================================================================
// GovernanceFranchiseHandler is the Quintessence registry, so it is the only
// caller that reaches distil and respawn, and Governance reads the same address
// as its event recorder. forge drives the handler with random call sequences and
// checks every invariant_ function after them.
//
// The franchise invariant this file holds is the one the contract promises:
//
//   franchiseOf(a) >= Quintessence.balance(a), for every roster address, always
//
// Unit 6's conservation invariants live in QuintessenceConservation.t.sol and are
// not repeated here. What is new is the narrower law: a governance call moves no
// Quintessence, so the bucket sum is identical on both sides of every
// syncFranchise and every recordEventAction.
//
// A counting invariant asserts its attempt counter is above zero before it reads
// its violation counter, so a path no sequence reached fails instead of passing
// on an absence.
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

contract GovernanceFranchiseHandler {
    uint256 private constant HOLDER_COUNT = 4;

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    Quintessence public quint;
    Governance public gov;

    address[HOLDER_COUNT] public holders;

    uint256 public syncCalls;
    uint256 public eventActionCalls;
    uint256 public ceilingBelowBalanceAfterSync;
    uint256 public bucketSumMovedByAGovernanceCall;
    uint256 public distilCalls;
    uint256 public spendCalls;
    uint256 public respawnCalls;
    uint256 public warpCalls;

    constructor() {
        for (uint256 i = 0; i < HOLDER_COUNT; ++i) {
            holders[i] = address(uint160(uint256(keccak256(abi.encode("poa holder", i))) | 1));
        }
    }

    function bind(Quintessence quintessence, Governance governance) external {
        require(address(quint) == address(0), "Handler: already bound");
        quint = quintessence;
        gov = governance;
    }

    function distil(uint256 holderSeed, uint256 amount) external {
        uint256 room = quint.remainingEverMintable();
        if (room == 0) {
            return;
        }
        quint.distil(_holder(holderSeed), (amount % room) + 1);
        distilCalls += 1;
    }

    function spend(uint256 holderSeed, uint256 heldSeed, uint256 amount) external {
        address holder = _holder(holderSeed);
        uint256 holds = quint.balance(holder);
        if (holds == 0) {
            return;
        }
        address heldAddress = address(uint160(uint256(keccak256(abi.encode(heldSeed))) | 1));
        VM.prank(holder);
        quint.spend(heldAddress, (amount % holds) + 1);
        spendCalls += 1;
    }

    function respawn(uint256 holderSeed, uint256 amount) external {
        uint256 pleroma = quint.pleromaTotal();
        if (pleroma == 0) {
            return;
        }
        quint.respawn(_holder(holderSeed), (amount % pleroma) + 1);
        respawnCalls += 1;
    }

    function syncFranchise(uint256 holderSeed) external {
        address holder = _holder(holderSeed);
        uint256 bucketsBefore = _bucketSum();
        gov.syncFranchise(holder);
        syncCalls += 1;
        if (_bucketSum() != bucketsBefore) {
            bucketSumMovedByAGovernanceCall += 1;
        }
        if (_ceilingOf(holder) < quint.balance(holder)) {
            ceilingBelowBalanceAfterSync += 1;
        }
    }

    function recordEventAction(uint256 holderSeed) external {
        address holder = _holder(holderSeed);
        uint256 bucketsBefore = _bucketSum();
        gov.recordEventAction(holder);
        eventActionCalls += 1;
        if (_bucketSum() != bucketsBefore) {
            bucketSumMovedByAGovernanceCall += 1;
        }
    }

    function warpForward(uint256 secondsAhead) external {
        VM.warp(block.timestamp + (secondsAhead % (400 days)) + 1);
        warpCalls += 1;
    }

    function governanceCalls() external view returns (uint256) {
        return syncCalls + eventActionCalls;
    }

    function holderCount() external pure returns (uint256) {
        return HOLDER_COUNT;
    }

    function _holder(uint256 seed) private view returns (address) {
        return holders[seed % HOLDER_COUNT];
    }

    function _ceilingOf(address holder) private view returns (uint256 ceiling) {
        (ceiling,,,) = gov.franchise(holder);
    }

    function _bucketSum() private view returns (uint256) {
        return quint.walletsTotal() + quint.heldTotal() + quint.pleromaTotal()
            + quint.embeddedTotal();
    }
}

contract GovernanceFranchiseTest {
    uint256 private constant ONE_WHOLE = 10**18;

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    ACRV public acrv;
    CompetitionRegistry public registry;
    AcervatorTrophy public trophy;
    Quintessence public quint;
    Governance public gov;
    GovernanceFranchiseHandler public handler;

    address private _holder;

    function setUp() public {
        VM.warp(1_800_000_000);

        acrv = new ACRV();
        registry = new CompetitionRegistry(address(acrv), address(0xB7C), address(0xE7C));
        acrv.setRegistry(address(registry));
        trophy = new AcervatorTrophy(address(registry));

        handler = new GovernanceFranchiseHandler();
        quint = new Quintessence(address(handler));
        gov = new Governance(address(quint), address(registry), address(trophy), address(acrv));

        acrv.setGovernance(address(gov));
        registry.setGovernance(address(gov));
        trophy.setGovernance(address(gov));

        handler.bind(quint, gov);

        handler.distil(0, 100 * ONE_WHOLE);
        handler.recordEventAction(0);
        handler.syncFranchise(0);
        handler.spend(0, 1, 10 * ONE_WHOLE);
        handler.warpForward(1 days);
        handler.syncFranchise(0);

        _holder = handler.holders(1);
    }

    /// @notice forge drives only the handler, which is the registry and the recorder.
    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    // ── Invariants ────────────────────────────────────────────────────────────

    /// @notice A failure means an address's franchise fell below its balance.
    function invariant_franchiseIsNeverBelowTheBalance() public view {
        uint256 recorded = gov.rosterCount();
        require(recorded > 0, "no address reached the roster");
        for (uint256 i = 0; i < recorded; ++i) {
            address holder = gov.roster(i);
            require(
                gov.franchiseOf(holder) >= quint.balance(holder),
                "franchiseOf is below the address's balance"
            );
        }
    }

    /// @notice A failure means a sync left the stored ceiling under the balance.
    function invariant_aSyncLeavesTheCeilingAtOrAboveTheBalance() public view {
        require(handler.syncCalls() > 0, "no syncFranchise was called");
        require(
            handler.ceilingBelowBalanceAfterSync() == 0,
            "a sync left franchiseCeiling below the balance"
        );
    }

    /// @notice A failure means a governance call moved Quintessence.
    function invariant_noGovernanceCallMovesQuintessence() public view {
        require(handler.governanceCalls() > 0, "no governance call was made");
        require(
            handler.bucketSumMovedByAGovernanceCall() == 0,
            "a governance call changed the bucket sum"
        );
    }

    // ── The franchise rises with the balance, in the same block ───────────────

    /// @notice A failure means a distil did not carry the franchise up with it.
    function test_a_balance_that_rises_carries_the_franchise_up_at_once() public {
        _distilTo(_holder, 50 * ONE_WHOLE);
        require(gov.franchiseOf(_holder) == 50 * ONE_WHOLE, "franchise did not follow the first distil");

        _distilTo(_holder, 100 * ONE_WHOLE);
        require(
            quint.balance(_holder) == 150 * ONE_WHOLE,
            "the balance is not 150 after both distils"
        );
        require(
            gov.franchiseOf(_holder) == 150 * ONE_WHOLE,
            "franchise did not follow the second distil in the same block"
        );
    }

    /// @notice A failure means a spend pulled the franchise down with the balance.
    function test_a_balance_that_falls_leaves_the_franchise_where_it_was() public {
        _distilTo(_holder, 150 * ONE_WHOLE);
        gov.syncFranchise(_holder);

        VM.prank(_holder);
        quint.spend(address(0x4E1D), 100 * ONE_WHOLE);

        require(quint.balance(_holder) == 50 * ONE_WHOLE, "the spend did not leave 50");
        require(
            gov.franchiseOf(_holder) == 150 * ONE_WHOLE,
            "the franchise fell with the balance"
        );
    }

    // ── Dormancy ──────────────────────────────────────────────────────────────

    /// @notice A failure means the ceiling did not stand for the whole hold period.
    function test_the_ceiling_stands_for_the_ninety_day_hold_period() public {
        _openAGapOfOneHundred();

        VM.warp(block.timestamp + gov.HOLD_SECONDS());
        require(
            gov.franchiseOf(_holder) == 150 * ONE_WHOLE,
            "the franchise resynchronized inside the hold period"
        );
    }

    /// @notice A failure means the resynchronization rate is not a ninetieth a day.
    function test_forty_five_dormant_days_close_half_the_gap() public {
        _openAGapOfOneHundred();

        VM.warp(block.timestamp + gov.HOLD_SECONDS() + 45 days);
        require(
            gov.franchiseOf(_holder) == 100 * ONE_WHOLE,
            "forty-five dormant days did not close half the gap"
        );
    }

    /// @notice A failure means a full resynchronization does not reach the balance.
    function test_ninety_dormant_days_close_the_whole_gap() public {
        _openAGapOfOneHundred();

        VM.warp(block.timestamp + gov.HOLD_SECONDS() + 90 days);
        require(
            gov.franchiseOf(_holder) == 50 * ONE_WHOLE,
            "ninety dormant days did not close the whole gap"
        );
        require(
            gov.franchiseOf(_holder) == quint.balance(_holder),
            "the resynchronization floor is not the address's balance"
        );
    }

    /// @notice A failure means a full resynchronization moved Quintessence.
    function test_a_full_resynchronization_moves_no_quintessence() public {
        _openAGapOfOneHundred();

        (
            uint256 walletsBefore,
            uint256 heldBefore,
            uint256 pleromaBefore,
            uint256 embeddedBefore,
            uint256 mintedBefore,
            ,
            bool balancedBefore,
        ) = quint.conservation();

        VM.warp(block.timestamp + gov.HOLD_SECONDS() + 90 days);
        gov.syncFranchise(_holder);

        (
            uint256 walletsAfter,
            uint256 heldAfter,
            uint256 pleromaAfter,
            uint256 embeddedAfter,
            uint256 mintedAfter,
            ,
            bool balancedAfter,
        ) = quint.conservation();

        require(walletsAfter == walletsBefore, "walletsTotal moved during a resynchronization");
        require(heldAfter == heldBefore, "heldTotal moved during a resynchronization");
        require(pleromaAfter == pleromaBefore, "pleromaTotal moved during a resynchronization");
        require(embeddedAfter == embeddedBefore, "embeddedTotal moved during a resynchronization");
        require(mintedAfter == mintedBefore, "totalEverMinted moved during a resynchronization");
        require(balancedBefore && balancedAfter, "the conservation law did not hold on both sides");
        require(
            gov.franchiseOf(_holder) == quint.balance(_holder),
            "the franchise did not settle on the balance"
        );
    }

    // ── What counts as activity ───────────────────────────────────────────────

    /// @notice A failure means a certified trade refreshed the activity clock.
    function test_a_distil_does_not_reset_the_activity_clock() public {
        _openAGapOfOneHundred();
        uint256 clockBefore = _clockOf(_holder);

        _distilTo(_holder, 1);

        require(
            _clockOf(_holder) == clockBefore,
            "a distil moved lastEventActionAt"
        );

        VM.warp(block.timestamp + gov.HOLD_SECONDS() + 45 days);
        require(
            gov.franchiseOf(_holder) < 150 * ONE_WHOLE,
            "the franchise did not resynchronize after a distil, so the trade reset the clock"
        );
    }

    /// @notice A failure means an event-anchored action did not refresh the clock.
    function test_an_event_action_resets_the_activity_clock() public {
        _openAGapOfOneHundred();
        uint256 clockBefore = _clockOf(_holder);

        VM.warp(block.timestamp + 10 days);
        VM.prank(address(handler));
        gov.recordEventAction(_holder);

        require(
            _clockOf(_holder) > clockBefore,
            "an event action did not move lastEventActionAt"
        );

        VM.warp(block.timestamp + gov.HOLD_SECONDS());
        require(
            gov.franchiseOf(_holder) == 150 * ONE_WHOLE,
            "the franchise resynchronized inside the hold period the event action bought"
        );
    }

    /// @notice A failure means an event action restored franchise already given up.
    function test_an_event_action_banks_the_resynchronization_already_made() public {
        _openAGapOfOneHundred();

        VM.warp(block.timestamp + gov.HOLD_SECONDS() + 45 days);
        require(gov.franchiseOf(_holder) == 100 * ONE_WHOLE, "half the gap did not close");

        VM.prank(address(handler));
        gov.recordEventAction(_holder);

        require(
            gov.franchiseOf(_holder) == 100 * ONE_WHOLE,
            "an event action restored franchise the resynchronization had closed"
        );
    }

    /// @notice A failure means an address other than the registry refreshed a clock.
    function test_only_the_quintessence_registry_records_an_event_action() public {
        try gov.recordEventAction(_holder) {
            revert("a non-registry caller recorded an event action");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Gov: caller not event recorder"),
                "the refusal came from somewhere else"
            );
        }

        VM.prank(address(handler));
        gov.recordEventAction(_holder);
        require(_clockOf(_holder) != 0, "the registry's own call was refused");
    }

    /// @notice A failure means a holding alone made a vote live.
    function test_a_holding_with_no_event_action_reaches_no_level() public {
        _distilTo(_holder, 150 * ONE_WHOLE);
        gov.syncFranchise(_holder);

        require(gov.franchiseOf(_holder) == 150 * ONE_WHOLE, "the franchise is not 150");
        require(!gov.isVoteLive(_holder), "a vote went live with no event action");
        require(gov.issueLevelOf(_holder) == 0, "a holding with no event action reached a level");

        VM.prank(address(handler));
        gov.recordEventAction(_holder);
        require(gov.issueLevelOf(_holder) == gov.LEVEL_CORE(), "the event action did not open CORE");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _ceilingOf(address holder) private view returns (uint256 ceiling) {
        (ceiling,,,) = gov.franchise(holder);
    }

    function _clockOf(address holder) private view returns (uint256 clock) {
        (,, clock,) = gov.franchise(holder);
    }

    function _distilTo(address holder, uint256 amount) private {
        VM.prank(address(handler));
        quint.distil(holder, amount);
    }

    /// Leaves the address on a 150 ceiling, a 50 balance and a live activity clock.
    function _openAGapOfOneHundred() private {
        _distilTo(_holder, 150 * ONE_WHOLE);
        VM.prank(address(handler));
        gov.recordEventAction(_holder);
        gov.syncFranchise(_holder);

        VM.prank(_holder);
        quint.spend(address(0x4E1D), 100 * ONE_WHOLE);

        require(quint.balance(_holder) == 50 * ONE_WHOLE, "the gap setup did not leave 50");
        require(_ceilingOf(_holder) == 150 * ONE_WHOLE, "the ceiling is not 150");
    }
}
