// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — the registry mints the trophy
// =============================================================================
// forge drives RegistryAwardHandler with random call sequences and checks every
// invariant_ function after them. targetContracts names that handler alone, so
// no call is spent driving the registry or the trophy from an address neither
// admits.
//
// RegistryAwardHandler deploys ACRV and CompetitionRegistry, so it is the
// registry's OPERATIONS and DEPLOYER and the token's deployer. The test contract
// deploys AcervatorTrophy, so it is the trophy's DEPLOYER and fills every tier
// SVG, including one under a tier name outside the five so an unknown-tier
// refusal can only come from the tier check.
//
// Each bot is a contract holding onERC721Received, because _safeMint refuses a
// contract recipient that does not answer it.
//
// Gold Fold, Bear Slayer and Grand Accumulator cannot be awarded to their
// ceilings in a test, so the handler parks a counter at one below its ceiling
// with vm.store. Ekthelius is driven to 21 awards with no parking at all.
// setUp proves the parked slot is the storage the tierMinted getter reads.
//
// A counting invariant asserts its attempt counter is above zero before it reads
// its refusal counter, so a path no sequence reached fails instead of passing on
// an absence.
// =============================================================================
pragma solidity 0.8.36;

import {ACRV} from "../../contracts/ACRV.sol";
import {AcervatorTrophy} from "../../contracts/AcervatorTrophy.sol";
import {CompetitionRegistry} from "../../contracts/CompetitionRegistry.sol";
import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";

interface Vm {
    function load(address target, bytes32 slot) external view returns (bytes32);
    function store(address target, bytes32 slot, bytes32 value) external;
}

contract BotStub {
    function register(CompetitionRegistry registry, string calldata compId) external {
        registry.registerBot(compId, keccak256(abi.encodePacked(compId)), 40_000);
    }

    function submit(
        CompetitionRegistry registry,
        string calldata compId,
        bytes32 merkleRoot,
        int256 finalValueCents
    ) external {
        registry.submitResult(compId, merkleRoot, 40_000, finalValueCents, 12);
    }

    function onERC721Received(address, address, uint256, bytes calldata)
        external pure returns (bytes4)
    {
        return this.onERC721Received.selector;
    }
}

contract RegistryAwardHandler {
    using Strings for uint256;

    uint256 private constant CAPPED_TIER_COUNT = 4;
    uint256 private constant TIER_MINTED_SLOT = 8;

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    string public constant UNKNOWN_TIER = "Ekthelius ";
    string public constant SYMBOL = "BTC/USDT";
    string public constant REGIME = "BULL";
    bytes32 public constant MERKLE_ROOT = keccak256("winning trade log");
    int256 public constant FINAL_VALUE_CENTS = 52_000;

    ACRV public immutable acrv;
    CompetitionRegistry public immutable registry;
    BotStub public immutable winnerBot;
    BotStub public immutable runnerUpBot;

    AcervatorTrophy public trophy;

    uint256 public openedCount;
    uint256 public injected;

    uint256 public awardSuccesses;

    uint256[CAPPED_TIER_COUNT] public capAttempts;
    uint256[CAPPED_TIER_COUNT] public capSuccesses;

    uint256 public harvestAttempts;
    uint256 public harvestRefusals;

    uint256 public unknownTierAttempts;
    uint256 public unknownTierSuccesses;

    string public lastAwardedCompId;
    uint256 public lastAwardedTrophyId;

    constructor() {
        acrv = new ACRV();
        registry = new CompetitionRegistry(address(acrv), address(0xB7C), address(0xE7C));
        acrv.setRegistry(address(registry));
        winnerBot = new BotStub();
        runnerUpBot = new BotStub();
    }

    function wireTrophy(AcervatorTrophy acervatorTrophy) external {
        require(address(trophy) == address(0), "Handler: already wired");
        trophy = acervatorTrophy;
        registry.setTrophy(address(acervatorTrophy));
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

    /// Opens a competition, seats two bots, takes the winner's submission and
    /// leaves the competition in SUBMISSION, ready for adjudicate.
    function stageCompetition() public returns (string memory compId) {
        openedCount += 1;
        compId = string.concat("COMP-", openedCount.toString());
        registry.openCompetition(compId, SYMBOL, registry.currentSeason());
        winnerBot.register(registry, compId);
        runnerUpBot.register(registry, compId);
        registry.activateCompetition(compId);
        registry.closeForSubmission(compId, REGIME);
        winnerBot.submit(registry, compId, MERKLE_ROOT, FINAL_VALUE_CENTS);
    }

    /// Adjudicates a staged competition and lets the revert through, so a caller
    /// reads the refusal reason the registry or the trophy gave. Every award the
    /// suite makes passes through here, so awardSuccesses counts all of them.
    function awardAs(string memory tier, uint256 tokenAmount)
        public returns (string memory compId)
    {
        compId = stageCompetition();
        registry.adjudicate(compId, address(winnerBot), tier, tokenAmount);
        awardSuccesses += 1;
        lastAwardedCompId = compId;
        lastAwardedTrophyId = trophy.totalMinted();
    }

    function advanceSeason() external {
        registry.advanceSeason();
    }

    function awardCappedTier(uint256 tierSeed) external {
        uint256 index = tierSeed % CAPPED_TIER_COUNT;
        string memory tier = cappedTierName(index);
        if (trophy.tierMinted(tier) >= cappedTierMax(index)) {
            return;
        }
        awardAs(tier, 0);
    }

    function awardHarvest() external {
        harvestAttempts += 1;
        try this.awardAs("Harvest", 0) {
            return;
        } catch {
            harvestRefusals += 1;
        }
    }

    function awardUnknownTier() external {
        unknownTierAttempts += 1;
        try this.awardAs(UNKNOWN_TIER, 0) {
            unknownTierSuccesses += 1;
        } catch {
            return;
        }
    }

    function awardWithTokens(uint256 amountSeed) external {
        uint256 amount = ((amountSeed % 1_000) + 1) * 10**18;
        try this.awardAs("Harvest", amount) {
            return;
        } catch {
            return;
        }
    }

    /// Raises a capped tier's counter to one below its ceiling and records the
    /// jump, because no test can reach a 100,000 ceiling by awarding.
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

    function parkTierAt(string memory tier, uint256 value) external {
        VM.store(address(trophy), tierMintedSlot(tier), bytes32(value));
    }

    function awardToTheCap(uint256 tierSeed) public {
        uint256 index = tierSeed % CAPPED_TIER_COUNT;
        string memory tier = cappedTierName(index);
        if (trophy.tierMinted(tier) != cappedTierMax(index) - 1) {
            return;
        }
        awardAs(tier, 0);
    }

    function awardPastTheCap(uint256 tierSeed) public {
        uint256 index = tierSeed % CAPPED_TIER_COUNT;
        string memory tier = cappedTierName(index);
        if (trophy.tierMinted(tier) != cappedTierMax(index)) {
            return;
        }
        capAttempts[index] += 1;
        try this.awardAs(tier, 0) {
            capSuccesses[index] += 1;
        } catch {
            return;
        }
    }
}

contract RegistryMintsTrophyTest {
    uint256 private constant CAPPED_TIER_COUNT = 4;

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    AcervatorTrophy public trophy;
    RegistryAwardHandler public handler;

    function setUp() public {
        (trophy, handler) = _freshSet();

        handler.awardHarvest();
        _proveParkedSlotIsTheGetterSlot();
        handler.awardUnknownTier();

        for (uint256 i = 0; i < CAPPED_TIER_COUNT; ++i) {
            handler.parkTierAtOneBelowCap(i);
            handler.awardToTheCap(i);
            handler.awardPastTheCap(i);
        }
    }

    /// @notice forge drives only the handler, which is operations and the recorder.
    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    /// Each test gets its own set, because setUp drives every tier to its ceiling
    /// and a test that needs a tier below its ceiling would read a filled counter.
    function _freshSet() private returns (AcervatorTrophy, RegistryAwardHandler) {
        RegistryAwardHandler freshHandler = new RegistryAwardHandler();
        AcervatorTrophy freshTrophy = new AcervatorTrophy(address(freshHandler.registry()));

        freshTrophy.setTierSvg("Harvest", "c3Zn");
        freshTrophy.setTierSvg("Gold Fold", "c3Zn");
        freshTrophy.setTierSvg("Bear Slayer", "c3Zn");
        freshTrophy.setTierSvg("Grand Accumulator", "c3Zn");
        freshTrophy.setTierSvg("Ekthelius", "c3Zn");
        freshTrophy.setTierSvg(freshHandler.UNKNOWN_TIER(), "c3Zn");

        freshHandler.wireTrophy(freshTrophy);
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

    // ── Invariants ────────────────────────────────────────────────────────────

    /// @notice A failure means an adjudicated award minted no trophy, or minted two.
    function invariant_everyAwardMintsExactlyOneTrophy() public view {
        require(handler.awardSuccesses() > 0, "no award was adjudicated");
        require(
            trophy.totalMinted() == handler.awardSuccesses(),
            "the trophies minted do not match the awards adjudicated"
        );
    }

    /// @notice A failure means the winner does not hold the trophy its award minted.
    function invariant_theWinnerHoldsTheTrophyItsAwardMinted() public view {
        require(handler.awardSuccesses() > 0, "no award was adjudicated");
        string memory compId = handler.lastAwardedCompId();
        uint256 tokenId = handler.lastAwardedTrophyId();
        require(tokenId != 0, "the award minted no trophy");
        require(
            trophy.ownerOf(tokenId) == handler.registry().winners(compId),
            "the trophy is not held by the competition's winner"
        );
    }

    /// @notice A failure means an award at a tier's ceiling succeeded, or none was tried.
    function invariant_everyCeilingRefusedAnAwardAtIt() public view {
        for (uint256 i = 0; i < CAPPED_TIER_COUNT; ++i) {
            require(handler.capAttempts(i) > 0, "no award at a ceiling was attempted");
            require(handler.capSuccesses(i) == 0, "an award at a ceiling succeeded");
        }
    }

    /// @notice A failure means a tier name outside the five won an award, or none was tried.
    function invariant_aTierNameOutsideTheFiveWinsNoAward() public view {
        require(handler.unknownTierAttempts() > 0, "no unknown tier name was attempted");
        require(
            handler.unknownTierSuccesses() == 0,
            "a tier name outside the five won an award"
        );
    }

    /// @notice A failure means Harvest was refused, so the lowest tier gained a ceiling.
    function invariant_harvestIsNeverRefused() public view {
        require(handler.harvestAttempts() > 0, "no Harvest award was attempted");
        require(handler.harvestRefusals() == 0, "a Harvest award was refused");
    }

    /// @notice A failure means a season awarded more ACRV than its budget allows.
    function invariant_noSeasonAwardsPastItsBudget() public view {
        CompetitionRegistry registry = handler.registry();
        uint256 season = registry.currentSeason();
        require(
            registry.seasonMinted(season) <= registry.seasonBudgetWei(season),
            "a season awarded past its on-chain budget"
        );
    }

    // ── The trophy reference ──────────────────────────────────────────────────

    /// @notice A failure means an adjudicated award reaches no NFT.
    function test_an_adjudicated_award_mints_the_trophy_to_the_winner() public {
        (AcervatorTrophy fresh, RegistryAwardHandler freshHandler) = _freshSet();
        CompetitionRegistry registry = freshHandler.registry();

        string memory compId = freshHandler.awardAs("Grand Accumulator", 500 * 10**18);

        uint256 tokenId = fresh.totalMinted();
        require(tokenId == 1, "the award minted no trophy");
        require(
            keccak256(bytes(registry.winnerTiers(compId))) == keccak256("Grand Accumulator"),
            "the registry recorded no winning tier for the award"
        );
        require(
            fresh.ownerOf(tokenId) == address(freshHandler.winnerBot()),
            "the trophy was not minted to the winning bot"
        );
        require(
            keccak256(bytes(fresh.getTrophyTier(tokenId)))
                == keccak256("Grand Accumulator"),
            "the trophy does not carry the awarded tier"
        );
        require(bytes(fresh.tokenURI(tokenId)).length > 0, "the trophy has no metadata");
    }

    /// @notice A failure means the trophy metadata lost a value the competition held.
    function test_the_trophy_carries_the_competition_its_award_came_from() public {
        (AcervatorTrophy fresh, RegistryAwardHandler freshHandler) = _freshSet();
        CompetitionRegistry registry = freshHandler.registry();

        string memory compId = freshHandler.awardAs("Ekthelius", 0);

        (
            ,
            string memory tierEmoji,
            uint256 season,
            string memory mintedCompId,
            uint256 rank,
            uint256 fieldSize,
            int256 advantageBps,
            string memory marketRegime,
            bytes32 merkleRoot,
            address botWallet,
        ) = fresh.trophyData(1);

        require(keccak256(bytes(tierEmoji)) == keccak256(unicode"∞"), "wrong tier emoji");
        require(season == registry.currentSeason(), "wrong season");
        require(keccak256(bytes(mintedCompId)) == keccak256(bytes(compId)), "wrong competition");
        require(rank == 1, "the winner is not ranked first");
        require(fieldSize == registry.getParticipantCount(compId), "wrong field size");
        require(
            advantageBps == registry.getSubmission(compId, botWallet).advantageBps,
            "the trophy advantage does not match the submission"
        );
        require(
            keccak256(bytes(marketRegime)) == keccak256(bytes(freshHandler.REGIME())),
            "wrong market regime"
        );
        require(merkleRoot == freshHandler.MERKLE_ROOT(), "wrong merkle root");
        require(botWallet == address(freshHandler.winnerBot()), "wrong bot wallet");
    }

    /// @notice A failure means an award can be adjudicated with no NFT behind it.
    function test_adjudicate_is_refused_until_the_trophy_reference_lands() public {
        RegistryAwardHandler bareHandler = new RegistryAwardHandler();
        CompetitionRegistry registry = bareHandler.registry();

        _assertAwardRefused(bareHandler, "Harvest", "Registry: trophy not set");
        require(bareHandler.awardSuccesses() == 0, "an award landed with no trophy set");

        AcervatorTrophy late = new AcervatorTrophy(address(registry));
        late.setTierSvg("Harvest", "c3Zn");
        bareHandler.wireTrophy(late);

        string memory compId = bareHandler.awardAs("Harvest", 0);
        require(late.totalMinted() == 1, "the wired award minted no trophy");
        require(
            late.ownerOf(1) == registry.winners(compId),
            "the wired award's trophy is not held by the winner"
        );
    }

    /// @notice A failure means the trophy a deployment mints through can be redirected.
    function test_the_trophy_reference_is_written_once_by_the_deployer() public {
        (AcervatorTrophy fresh, RegistryAwardHandler freshHandler) = _freshSet();
        CompetitionRegistry registry = freshHandler.registry();

        AcervatorTrophy rival = new AcervatorTrophy(address(registry));
        try freshHandler.wireTrophy(rival) {
            revert("the trophy reference was written twice");
        } catch {
            require(
                address(registry.trophy()) == address(fresh),
                "the second write moved the trophy reference"
            );
        }
    }

    /// @notice A failure means an address other than the deployer can name the trophy.
    function test_a_caller_other_than_the_deployer_cannot_name_the_trophy() public {
        RegistryAwardHandler bareHandler = new RegistryAwardHandler();
        CompetitionRegistry registry = bareHandler.registry();
        AcervatorTrophy outside = new AcervatorTrophy(address(registry));

        try registry.setTrophy(address(outside)) {
            revert("a caller other than the deployer named the trophy");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Registry: caller is not the deployer"),
                "the outside caller was refused for some other reason"
            );
        }
        require(address(registry.trophy()) == address(0), "the refused call wrote the reference");

        bareHandler.wireTrophy(outside);
        require(address(registry.trophy()) == address(outside), "the deployer was refused");
    }

    /// @notice A failure means a wallet holding no code can be named as the trophy.
    function test_an_address_holding_no_code_cannot_be_named_as_the_trophy() public {
        RegistryAwardHandler bareHandler = new RegistryAwardHandler();
        CompetitionRegistry registry = bareHandler.registry();

        try bareHandler.registry().setTrophy(address(0xBEEF)) {
            revert("an address holding no code was named as the trophy");
        } catch {
            require(address(registry.trophy()) == address(0), "the refused call wrote the reference");
        }
    }

    // ── One ceiling, and it is the trophy's ───────────────────────────────────

    /// @notice A failure means the Ekthelius ceiling admitted a 22nd award.
    function test_ekthelius_awards_twenty_one_times_and_the_twenty_second_is_refused() public {
        (AcervatorTrophy fresh, RegistryAwardHandler freshHandler) = _freshSet();
        uint256 ceiling = fresh.MAX_EKTHELIUS();

        for (uint256 i = 0; i < ceiling; ++i) {
            freshHandler.awardAs("Ekthelius", 0);
        }
        require(fresh.tierMinted("Ekthelius") == ceiling, "an award below the ceiling was refused");
        require(fresh.totalMinted() == ceiling, "an award below the ceiling minted no trophy");

        _assertAwardRefused(
            freshHandler, "Ekthelius", "Trophy: Ekthelius supply of 21 exhausted"
        );
        require(fresh.tierMinted("Ekthelius") == ceiling, "a refused award raised the counter");
        require(fresh.totalMinted() == ceiling, "a refused award minted a trophy");
    }

    /// @notice A failure means the Grand Accumulator ceiling admitted a 1,001st award.
    function test_grand_accumulator_awards_at_999_and_is_refused_at_1000() public {
        _assertCeilingRefusesAtItsLimit(1, "Trophy: Grand Accumulator supply of 1,000 exhausted");
    }

    /// @notice A failure means the Bear Slayer ceiling admitted a 10,001st award.
    function test_bear_slayer_awards_at_9999_and_is_refused_at_10000() public {
        _assertCeilingRefusesAtItsLimit(2, "Trophy: Bear Slayer supply of 10,000 exhausted");
    }

    /// @notice A failure means the Gold Fold ceiling admitted a 100,001st award.
    function test_gold_fold_awards_at_99999_and_is_refused_at_100000() public {
        _assertCeilingRefusesAtItsLimit(3, "Trophy: Gold Fold supply of 100,000 exhausted");
    }

    /// @notice A failure means the registry keeps a tier counter of its own, because
    ///         clearing the trophy's counter would not admit the same award.
    function test_the_only_counter_refusing_an_award_is_the_trophy_s() public {
        (AcervatorTrophy fresh, RegistryAwardHandler freshHandler) = _freshSet();
        uint256 ceiling = fresh.MAX_EKTHELIUS();

        freshHandler.parkTierAt("Ekthelius", ceiling);
        _assertAwardRefused(
            freshHandler, "Ekthelius", "Trophy: Ekthelius supply of 21 exhausted"
        );

        freshHandler.parkTierAt("Ekthelius", 0);
        freshHandler.awardAs("Ekthelius", 0);
        require(
            fresh.tierMinted("Ekthelius") == 1,
            "clearing the trophy's counter did not admit the award"
        );
    }

    /// @notice A failure means a tier name outside the five won an award.
    function test_a_tier_name_outside_the_five_is_refused_at_adjudication() public {
        (AcervatorTrophy fresh, RegistryAwardHandler freshHandler) = _freshSet();
        string memory unknown = freshHandler.UNKNOWN_TIER();
        require(
            bytes(fresh.getTierSvg(unknown)).length > 0,
            "the unknown tier has no SVG, so the refusal would prove the SVG check"
        );

        _assertAwardRefused(freshHandler, unknown, "Trophy: unknown tier");
        require(fresh.totalMinted() == 0, "the unknown tier minted a trophy");

        freshHandler.awardAs("Harvest", 0);
        require(fresh.totalMinted() == 1, "a known tier was refused");
    }

    /// @notice A failure means Harvest refuses an award, so it is no longer uncapped.
    function test_harvest_awards_past_every_other_tier_ceiling() public {
        (AcervatorTrophy fresh, RegistryAwardHandler freshHandler) = _freshSet();
        uint256 beyond = fresh.MAX_EKTHELIUS() + fresh.MAX_GRAND_ACCUMULATOR();
        freshHandler.parkTierAt("Harvest", beyond);

        freshHandler.awardAs("Harvest", 0);
        require(
            fresh.tierMinted("Harvest") == beyond + 1,
            "a Harvest award was refused above the other tiers' ceilings"
        );
    }

    // ── The season budget ─────────────────────────────────────────────────────

    /// @notice A failure means the on-chain budget left the published decay curve.
    function test_the_season_budget_is_the_decay_curve() public view {
        CompetitionRegistry registry = handler.registry();
        require(registry.seasonBudgetWei(1) == 500_000 * 10**18, "season 1 is not 500,000");
        require(registry.seasonBudgetWei(2) == 425_000 * 10**18, "season 2 is not 425,000");
        require(registry.seasonBudgetWei(3) == 361_250 * 10**18, "season 3 is not 361,250");
        require(registry.seasonBudgetWei(4) == 307_062 * 10**18, "season 4 is not 307,062");
        require(registry.seasonBudgetWei(5) == 261_003 * 10**18, "season 5 is not 261,003");
        require(registry.seasonBudgetWei(6) == 221_852 * 10**18, "season 6 is not 221,852");
        require(registry.seasonBudgetWei(53) == 106 * 10**18, "season 53 is not 106");
        require(registry.seasonBudgetWei(54) == 100 * 10**18, "season 54 is not the floor");
        require(registry.seasonBudgetWei(5_000) == 100 * 10**18, "a far season is not the floor");
    }

    /// @notice A failure means the whole-ACRV ceiling left what season_reward returns.
    function test_the_whole_token_budget_matches_the_python_schedule() public view {
        CompetitionRegistry registry = handler.registry();
        require(registry.seasonBudgetTokens(1) == 500_000, "season 1 is not 500,000");
        require(registry.seasonBudgetTokens(2) == 425_000, "season 2 is not 425,000");
        require(registry.seasonBudgetTokens(3) == 361_250, "season 3 is not 361,250");
        require(registry.seasonBudgetTokens(4) == 307_062, "season 4 is not 307,062");
        require(registry.seasonBudgetTokens(5) == 261_003, "season 5 is not 261,003");
        require(registry.seasonBudgetTokens(6) == 221_852, "season 6 is not 221,852");
        require(registry.seasonBudgetTokens(52) == 125, "season 52 is not 125");
        require(registry.seasonBudgetTokens(53) == 106, "season 53 is not 106");
        require(registry.seasonBudgetTokens(54) == 100, "season 54 is not the floor");
    }

    /// @notice A failure means season zero answers a budget it has no curve for.
    function test_season_zero_has_no_budget() public {
        CompetitionRegistry registry = handler.registry();
        try registry.seasonBudgetWei(0) {
            revert("season zero answered a budget");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Registry: season starts at 1"),
                "season zero was refused for some other reason"
            );
        }
    }

    /// @notice A failure means a season can award more ACRV than its budget.
    function test_an_award_filling_the_season_budget_lands_and_one_wei_past_it_is_refused()
        public
    {
        (, RegistryAwardHandler freshHandler) = _freshSet();
        CompetitionRegistry registry = freshHandler.registry();
        uint256 season = registry.currentSeason();
        uint256 budget = registry.seasonBudgetWei(season);

        freshHandler.awardAs("Harvest", budget);
        require(registry.seasonMinted(season) == budget, "the award did not fill the budget");
        require(registry.remainingSeasonBudgetWei(season) == 0, "the budget reads as unspent");

        _assertAwardRefusedWithAmount(
            freshHandler, "Harvest", 1, "Registry: season budget exhausted"
        );
        require(
            registry.seasonMinted(season) == budget,
            "a refused award raised the season total"
        );
    }

    /// @notice A failure means a later season inherits the season before it.
    function test_each_season_carries_its_own_budget() public {
        (, RegistryAwardHandler freshHandler) = _freshSet();
        CompetitionRegistry registry = freshHandler.registry();

        uint256 firstBudget = registry.seasonBudgetWei(1);
        freshHandler.awardAs("Harvest", firstBudget);
        require(registry.remainingSeasonBudgetWei(1) == 0, "season 1 reads as unspent");

        freshHandler.advanceSeason();
        require(registry.currentSeason() == 2, "advanceSeason did not move the season");
        require(
            registry.remainingSeasonBudgetWei(2) == registry.seasonBudgetWei(2),
            "season 2 opened with season 1's spend against it"
        );

        freshHandler.awardAs("Harvest", registry.seasonBudgetWei(2));
        require(registry.seasonMinted(2) == registry.seasonBudgetWei(2), "season 2 award refused");
        require(registry.seasonMinted(1) == firstBudget, "season 2's award moved season 1");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _assertCeilingRefusesAtItsLimit(uint256 index, string memory refusal) private {
        (AcervatorTrophy fresh, RegistryAwardHandler freshHandler) = _freshSet();
        string memory tier = freshHandler.cappedTierName(index);
        uint256 ceiling = freshHandler.cappedTierMax(index);

        freshHandler.parkTierAtOneBelowCap(index);
        require(
            fresh.tierMinted(tier) == ceiling - 1,
            "the counter was not parked one below the ceiling"
        );

        freshHandler.awardToTheCap(index);
        require(fresh.tierMinted(tier) == ceiling, "the award one below the ceiling was refused");

        _assertAwardRefused(freshHandler, tier, refusal);
        require(fresh.tierMinted(tier) == ceiling, "a refused award raised the counter");
    }

    function _assertAwardRefused(
        RegistryAwardHandler subject,
        string memory tier,
        string memory refusal
    ) private {
        _assertAwardRefusedWithAmount(subject, tier, 0, refusal);
    }

    function _assertAwardRefusedWithAmount(
        RegistryAwardHandler subject,
        string memory tier,
        uint256 tokenAmount,
        string memory refusal
    ) private {
        try subject.awardAs(tier, tokenAmount) {
            revert("an award that should have been refused succeeded");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256(bytes(refusal)),
                "the award was refused for some other reason"
            );
        }
    }
}
