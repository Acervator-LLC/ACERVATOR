// SPDX-License-Identifier: Apache-2.0
// ACERVATOR TROPHY — tier supply cap invariants
// =============================================================================
// forge drives TrophyCapHandler with random call sequences and checks every
// invariant_ function after them.
//
// TrophyCapHandler is the registry, so its mint calls pass onlyRegistry. The
// test contract deploys the trophy, so it is the owner and uploads every tier
// SVG, including one under an unknown tier name so an unknown-tier refusal can
// only come from the tier check and never from the missing-SVG check.
//
// Gold Fold, Bear Slayer and Grand Accumulator cannot be minted to their caps in
// a test, so the handler parks a counter at one below its cap with vm.store and
// records how much it injected. setUp proves the parked slot is the same storage
// the tierMinted getter reads.
//
// A counting invariant asserts its attempt counter is above zero before it reads
// its refusal counter, so a path no sequence reached fails instead of passing on
// an absence.
// =============================================================================
pragma solidity 0.8.36;

import {AcervatorTrophy} from "../../contracts/AcervatorTrophy.sol";

interface Vm {
    function load(address target, bytes32 slot) external view returns (bytes32);
    function store(address target, bytes32 slot, bytes32 value) external;
}

contract TrophyCapHandler {
    uint256 private constant CAPPED_TIER_COUNT = 4;

    /// tierMinted occupies slot 9 of AcervatorTrophy, per forge inspect storage.
    uint256 private constant TIER_MINTED_SLOT = 9;

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    string private constant UNKNOWN_TIER = "Ekthelius ";

    AcervatorTrophy public trophy;

    uint256 public injected;

    uint256[CAPPED_TIER_COUNT] public capAttempts;
    uint256[CAPPED_TIER_COUNT] public capSuccesses;

    uint256 public harvestAttempts;
    uint256 public harvestRefusals;

    uint256 public unknownTierAttempts;
    uint256 public unknownTierSuccesses;

    function bind(AcervatorTrophy acervatorTrophy) external {
        require(address(trophy) == address(0), "Handler: already bound");
        trophy = acervatorTrophy;
    }

    function cappedTierName(uint256 index) public pure returns (string memory) {
        if (index == 0) return "Ekthelius";
        if (index == 1) return "Grand Accumulator";
        if (index == 2) return "Bear Slayer";
        return "Gold Fold";
    }

    function cappedTierMax(uint256 index) public view returns (uint256) {
        if (index == 0) return trophy.MAX_EKTHELIUS();
        if (index == 1) return trophy.MAX_GRAND_ACCUMULATOR();
        if (index == 2) return trophy.MAX_BEAR_SLAYER();
        return trophy.MAX_GOLD_FOLD();
    }

    function tierMintedSlot(string memory tier) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(bytes(tier), TIER_MINTED_SLOT));
    }

    function mintTier(uint256 tierSeed, uint256 recipientSeed) external {
        uint256 index = tierSeed % CAPPED_TIER_COUNT;
        string memory tier = cappedTierName(index);
        if (trophy.tierMinted(tier) >= cappedTierMax(index)) {
            return;
        }
        trophy.mint(
            _recipient(recipientSeed), tier, "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        );
    }

    function mintHarvest(uint256 recipientSeed) external {
        harvestAttempts += 1;
        try trophy.mint(
            _recipient(recipientSeed), "Harvest", "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        ) {
            return;
        } catch {
            harvestRefusals += 1;
        }
    }

    function mintUnknownTier(uint256 recipientSeed) external {
        unknownTierAttempts += 1;
        try trophy.mint(
            _recipient(recipientSeed), UNKNOWN_TIER, "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        ) {
            unknownTierSuccesses += 1;
        } catch {
            return;
        }
    }

    /// Raises a capped tier's counter to one below its cap and records the jump,
    /// because no test can reach a 100,000 ceiling by minting.
    function parkTierAtOneBelowCap(uint256 tierSeed) public {
        uint256 index = tierSeed % CAPPED_TIER_COUNT;
        string memory tier = cappedTierName(index);
        uint256 target = cappedTierMax(index) - 1;
        uint256 held = trophy.tierMinted(tier);
        if (held >= target) {
            return;
        }
        VM.store(address(trophy), tierMintedSlot(tier), bytes32(target));
        injected += target - held;
    }

    function mintToTheCap(uint256 tierSeed, uint256 recipientSeed) public {
        uint256 index = tierSeed % CAPPED_TIER_COUNT;
        string memory tier = cappedTierName(index);
        if (trophy.tierMinted(tier) != cappedTierMax(index) - 1) {
            return;
        }
        trophy.mint(
            _recipient(recipientSeed), tier, "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        );
    }

    function mintPastTheCap(uint256 tierSeed, uint256 recipientSeed) public {
        uint256 index = tierSeed % CAPPED_TIER_COUNT;
        string memory tier = cappedTierName(index);
        if (trophy.tierMinted(tier) != cappedTierMax(index)) {
            return;
        }
        capAttempts[index] += 1;
        try trophy.mint(
            _recipient(recipientSeed), tier, "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        ) {
            capSuccesses[index] += 1;
        } catch {
            return;
        }
    }

    function mintedAcrossEveryTier() external view returns (uint256 total) {
        for (uint256 i = 0; i < CAPPED_TIER_COUNT; ++i) {
            total += trophy.tierMinted(cappedTierName(i));
        }
        total += trophy.tierMinted("Harvest");
        total += trophy.tierMinted(UNKNOWN_TIER);
    }

    function _recipient(uint256 seed) private pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encode(seed)))) | 1);
    }
}

contract TrophyTierCapsTest {
    uint256 private constant CAPPED_TIER_COUNT = 4;

    AcervatorTrophy public trophy;
    TrophyCapHandler public handler;

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function setUp() public {
        (trophy, handler) = _freshPair();

        handler.mintHarvest(1);
        _proveParkedSlotIsTheGetterSlot();
        handler.mintUnknownTier(2);

        for (uint256 i = 0; i < CAPPED_TIER_COUNT; ++i) {
            handler.parkTierAtOneBelowCap(i);
            handler.mintToTheCap(i, i + 10);
            handler.mintPastTheCap(i, i + 20);
        }
    }

    /// Each test gets its own pair, because setUp drives every tier to its cap and
    /// a test that observed the mint one below the cap would read a filled counter.
    function _freshPair() private returns (AcervatorTrophy, TrophyCapHandler) {
        TrophyCapHandler freshHandler = new TrophyCapHandler();
        AcervatorTrophy freshTrophy = new AcervatorTrophy(address(freshHandler));
        freshHandler.bind(freshTrophy);

        freshTrophy.setTierSvg("Harvest", "c3Zn");
        freshTrophy.setTierSvg("Gold Fold", "c3Zn");
        freshTrophy.setTierSvg("Bear Slayer", "c3Zn");
        freshTrophy.setTierSvg("Grand Accumulator", "c3Zn");
        freshTrophy.setTierSvg("Ekthelius", "c3Zn");
        freshTrophy.setTierSvg("Ekthelius ", "c3Zn");

        return (freshTrophy, freshHandler);
    }

    /// @notice A failure means vm.store writes a slot the tierMinted getter does not read.
    function _proveParkedSlotIsTheGetterSlot() private {
        handler.parkTierAtOneBelowCap(3);
        uint256 parked = trophy.MAX_GOLD_FOLD() - 1;
        require(
            uint256(VM.load(address(trophy), handler.tierMintedSlot("Gold Fold"))) == parked,
            "the parked slot does not hold the parked value"
        );
        require(
            trophy.tierMinted("Gold Fold") == parked,
            "tierMinted does not read the parked slot"
        );
    }

    /// @notice A failure means a capped tier minted past its declared maximum.
    function invariant_noCappedTierExceedsItsMaximum() public view {
        for (uint256 i = 0; i < CAPPED_TIER_COUNT; ++i) {
            require(
                trophy.tierMinted(handler.cappedTierName(i)) <= handler.cappedTierMax(i),
                "a tier holds more trophies than its declared maximum"
            );
        }
    }

    /// @notice A failure means a mint at a cap succeeded, or no cap was reached.
    function invariant_everyCapRefusedAMintAtIt() public view {
        for (uint256 i = 0; i < CAPPED_TIER_COUNT; ++i) {
            require(handler.capAttempts(i) > 0, "no mint at a cap was attempted");
            require(handler.capSuccesses(i) == 0, "a mint at a cap succeeded");
        }
    }

    /// @notice A failure means a tier name outside the five minted, or none was tried.
    function invariant_unknownTierNameIsRefused() public view {
        require(handler.unknownTierAttempts() > 0, "no unknown tier name was attempted");
        require(
            handler.unknownTierSuccesses() == 0,
            "a tier name outside the five minted a trophy"
        );
    }

    /// @notice A failure means Harvest was refused, so the lowest tier gained a ceiling.
    function invariant_harvestIsNeverRefused() public view {
        require(handler.harvestAttempts() > 0, "no Harvest mint was attempted");
        require(handler.harvestRefusals() == 0, "a Harvest mint was refused");
    }

    /// @notice A failure means a mint raised no tier counter.
    function invariant_everyMintIsCounted() public view {
        require(
            handler.mintedAcrossEveryTier() == trophy.totalMinted() + handler.injected(),
            "the tier counters do not account for every minted trophy"
        );
    }

    /// @notice A failure means a ceiling moved off the max_ever value RARITY_TIERS holds.
    function test_the_four_ceilings_hold_the_numbers_the_tier_list_declares() public view {
        require(trophy.MAX_GOLD_FOLD() == 100_000, "MAX_GOLD_FOLD is not 100,000");
        require(trophy.MAX_BEAR_SLAYER() == 10_000, "MAX_BEAR_SLAYER is not 10,000");
        require(
            trophy.MAX_GRAND_ACCUMULATOR() == 1_000, "MAX_GRAND_ACCUMULATOR is not 1,000"
        );
        require(trophy.MAX_EKTHELIUS() == 21, "MAX_EKTHELIUS is not 21");
    }

    /// @notice A failure means the Ekthelius cap admitted a 22nd trophy.
    function test_ekthelius_mints_at_twenty_and_is_refused_at_twenty_one() public {
        _assertCapRefusesAtItsLimit(0, "Trophy: Ekthelius supply of 21 exhausted");
    }

    /// @notice A failure means the Grand Accumulator cap admitted a 1,001st trophy.
    function test_grand_accumulator_mints_at_999_and_is_refused_at_1000() public {
        _assertCapRefusesAtItsLimit(1, "Trophy: Grand Accumulator supply of 1,000 exhausted");
    }

    /// @notice A failure means the Bear Slayer cap admitted a 10,001st trophy.
    function test_bear_slayer_mints_at_9999_and_is_refused_at_10000() public {
        _assertCapRefusesAtItsLimit(2, "Trophy: Bear Slayer supply of 10,000 exhausted");
    }

    /// @notice A failure means the Gold Fold cap admitted a 100,001st trophy.
    function test_gold_fold_mints_at_99999_and_is_refused_at_100000() public {
        _assertCapRefusesAtItsLimit(3, "Trophy: Gold Fold supply of 100,000 exhausted");
    }

    /// @notice A failure means the owner minted past a cap the registry is held to.
    function test_the_owner_mints_at_twenty_and_is_refused_at_twenty_one() public {
        (AcervatorTrophy fresh, TrophyCapHandler freshHandler) = _freshPair();
        uint256 cap = fresh.MAX_EKTHELIUS();
        VM.store(
            address(fresh), freshHandler.tierMintedSlot("Ekthelius"), bytes32(cap - 1)
        );

        fresh.mint(address(0xBEEF), "Ekthelius", "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0));
        require(fresh.tierMinted("Ekthelius") == cap, "the owner's mint at 20 was refused");

        try fresh.mint(
            address(0xBEEF), "Ekthelius", "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        ) {
            revert("the owner minted past the Ekthelius cap");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Trophy: Ekthelius supply of 21 exhausted"),
                "the owner was refused for some other reason"
            );
        }
    }

    /// @notice A failure means a tier name outside the five minted a trophy.
    function test_a_tier_name_outside_the_five_is_refused() public {
        (AcervatorTrophy fresh, TrophyCapHandler freshHandler) = _freshPair();
        require(
            bytes(fresh.getTierSvg("Ekthelius ")).length > 0,
            "the unknown tier has no SVG, so the refusal would prove the SVG check"
        );

        freshHandler.mintHarvest(7);
        require(fresh.tierMinted("Harvest") == 1, "a known tier was refused");

        try fresh.mint(
            address(0xCAFE), "Ekthelius ", "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        ) {
            revert("a tier name outside the five minted a trophy");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Trophy: unknown tier"),
                "the unknown tier was refused for some other reason"
            );
        }
    }

    /// @notice A failure means Harvest refuses a mint, so it is no longer uncapped.
    function test_harvest_mints_past_every_other_tier_ceiling() public {
        (AcervatorTrophy fresh, TrophyCapHandler freshHandler) = _freshPair();
        uint256 beyond = fresh.MAX_EKTHELIUS() + fresh.MAX_GRAND_ACCUMULATOR();
        VM.store(address(fresh), freshHandler.tierMintedSlot("Harvest"), bytes32(beyond));
        freshHandler.mintHarvest(99);
        require(
            fresh.tierMinted("Harvest") == beyond + 1,
            "a Harvest mint was refused above the other tiers' ceilings"
        );
    }

    function _assertCapRefusesAtItsLimit(uint256 index, string memory refusal) private {
        (AcervatorTrophy fresh, TrophyCapHandler freshHandler) = _freshPair();
        string memory tier = freshHandler.cappedTierName(index);
        uint256 cap = freshHandler.cappedTierMax(index);

        freshHandler.parkTierAtOneBelowCap(index);
        require(
            fresh.tierMinted(tier) == cap - 1,
            "the counter was not parked one below the cap"
        );

        freshHandler.mintToTheCap(index, index + 100);
        require(fresh.tierMinted(tier) == cap, "the mint one below the cap was refused");

        try fresh.mint(
            address(0xCAFE), tier, "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        ) {
            revert("a mint at the cap succeeded");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256(bytes(refusal)),
                "the refusal at the cap names some other reason"
            );
        }
        require(fresh.tierMinted(tier) == cap, "a refused mint raised the counter");
    }
}
