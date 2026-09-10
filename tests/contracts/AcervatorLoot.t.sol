// SPDX-License-Identifier: Apache-2.0
// ACERVATOR LOOT — the weight total, the draw span, and the on-chain metadata
// =============================================================================
// forge drives LootDropHandler with random call sequences and checks every
// invariant_ function after them.
//
// LootDropHandler is DROPPER, so its mint calls pass onlyDropper. The test
// contract deploys the loot, so it is DEPLOYER and fills all five tier SVGs,
// which leaves the tier check as the only reason an unknown id is refused.
//
// targetContracts names LootDropHandler alone. Without it forge also drives
// AcervatorLoot directly from the handler's address, so a direct mint raises
// totalMinted that no handler counter recorded.
//
// A counting invariant asserts its attempt counter is above zero before it reads
// its refusal counter, so a path no sequence reached fails instead of passing on
// an absence.
//
// The constructor require on the weight total takes no input: _setTier is
// private, it runs from the constructor on literals, and dropper is the only
// constructor argument. The suite drives the side that is reachable — the five
// weights read back out of tiers, and mint's roll check against the same
// WEIGHT_TOTAL_PER_MILLE those weights add up to.
// =============================================================================
pragma solidity 0.8.36;

import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";
import {AcervatorLoot} from "../../contracts/AcervatorLoot.sol";

interface Vm {
    function load(address target, bytes32 slot) external view returns (bytes32);

    function store(address target, bytes32 slot, bytes32 value) external;
}

contract LootDropHandler {
    AcervatorLoot public loot;

    uint256 public minted;

    uint256 public insideSpanAttempts;
    uint256 public insideSpanRefusals;

    uint256 public spanAttempts;
    uint256 public spanSuccesses;

    uint256 public unknownTierAttempts;
    uint256 public unknownTierSuccesses;

    uint256 public zeroRecipientAttempts;
    uint256 public zeroRecipientSuccesses;

    function bind(AcervatorLoot acervatorLoot) external {
        require(address(loot) == address(0), "Handler: already bound");
        loot = acervatorLoot;
    }

    function dropTier(uint256 tierSeed, uint256 rollSeed, uint256 recipientSeed) external {
        insideSpanAttempts += 1;
        try loot.mint(
            _recipient(recipientSeed),
            _knownTier(tierSeed),
            "kraken",
            "BTC/USD",
            1,
            rollSeed % loot.WEIGHT_TOTAL_PER_MILLE(),
            bytes32(0)
        ) {
            minted += 1;
        } catch {
            insideSpanRefusals += 1;
        }
    }

    function tryDropAtOrAboveTheSpan(uint256 tierSeed, uint256 rollSeed, uint256 recipientSeed)
        external
    {
        spanAttempts += 1;
        try loot.mint(
            _recipient(recipientSeed),
            _knownTier(tierSeed),
            "kraken",
            "BTC/USD",
            1,
            loot.WEIGHT_TOTAL_PER_MILLE() + (rollSeed % loot.WEIGHT_TOTAL_PER_MILLE()),
            bytes32(0)
        ) {
            minted += 1;
            spanSuccesses += 1;
        } catch {
            return;
        }
    }

    function tryDropUnknownTierId(uint256 tierSeed, uint256 recipientSeed) external {
        unknownTierAttempts += 1;
        try loot.mint(
            _recipient(recipientSeed),
            _unknownTier(tierSeed),
            "kraken",
            "BTC/USD",
            1,
            0,
            bytes32(0)
        ) {
            minted += 1;
            unknownTierSuccesses += 1;
        } catch {
            return;
        }
    }

    function tryDropToZeroAddress(uint256 tierSeed, uint256 rollSeed) external {
        zeroRecipientAttempts += 1;
        try loot.mint(
            address(0),
            _knownTier(tierSeed),
            "kraken",
            "BTC/USD",
            1,
            rollSeed % loot.WEIGHT_TOTAL_PER_MILLE(),
            bytes32(0)
        ) {
            minted += 1;
            zeroRecipientSuccesses += 1;
        } catch {
            return;
        }
    }

    /// Forwards as the dropper and lets the revert through, so a caller reads the
    /// loot contract's own refusal reason rather than the onlyDropper one.
    function mintAs(address recipient, uint256 tierId, uint256 roll)
        external
        returns (uint256 amount)
    {
        amount = loot.mint(recipient, tierId, "kraken", "BTC/USD", 1, roll, bytes32(0));
        minted += 1;
    }

    function weightTotal() external view returns (uint256 total) {
        for (uint256 id = loot.CALX(); id <= loot.TIER_COUNT(); ++id) {
            total += loot.tierWeight(id);
        }
    }

    function _knownTier(uint256 seed) private view returns (uint256) {
        return loot.CALX() + (seed % loot.TIER_COUNT());
    }

    function _unknownTier(uint256 seed) private view returns (uint256) {
        if (seed % 2 == 0) {
            return 0;
        }
        return loot.TIER_COUNT() + 1 + (seed % 4);
    }

    function _recipient(uint256 seed) private pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encode(seed)))) | 1);
    }
}

contract AcervatorLootTest {
    /// tiers occupies slot 4 of AcervatorLoot and weightPerMille is its third field.
    uint256 private constant TIERS_SLOT = 4;
    uint256 private constant WEIGHT_FIELD_OFFSET = 2;

    string private constant ART = "c3Zn";
    string private constant OTHER_ART = "c3ZnMg==";

    string private constant URI_PREFIX = "data:application/json;base64,";

    /// The metadata AcervatorLoot must serve for Calx with ART uploaded and none minted.
    string private constant CALX_JSON =
        unicode"{\"name\":\"Acervator Loot — Calx\",\"description\":\""
        unicode"A Proof-of-Accumulation loot item dropped by a qualifying market. "
        unicode"Tier 1 of 5, weight 600 of 1000. "
        unicode"It augments a tournament action and no trading figure: "
        unicode"0 Impetus off one action's cost and "
        unicode"20 of 1000 added to that action's effect."
        unicode"\",\"image\":\"data:image/svg+xml;base64,c3Zn\",\"attributes\":"
        unicode"[{\"trait_type\":\"Tier\",\"value\":\"Calx\"},"
        unicode"{\"trait_type\":\"Short Form\",\"value\":\"Calx\"},"
        unicode"{\"trait_type\":\"Weight (per mille)\",\"value\":600},"
        unicode"{\"trait_type\":\"Impetus Relief\",\"value\":0},"
        unicode"{\"trait_type\":\"Effect Bonus (per mille)\",\"value\":20},"
        unicode"{\"trait_type\":\"Minted\",\"value\":0},"
        unicode"{\"trait_type\":\"Tier Color\",\"value\":\"#C8C0B4\"}]}";

    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    AcervatorLoot public loot;
    LootDropHandler public handler;

    function setUp() public {
        (loot, handler) = _freshPair();

        handler.dropTier(0, 0, 1);
        handler.tryDropAtOrAboveTheSpan(1, 0, 2);
        handler.tryDropUnknownTierId(0, 3);
        handler.tryDropUnknownTierId(1, 4);
        handler.tryDropToZeroAddress(2, 5);
    }

    /// @notice forge drives only the handler, which is the dropper and counts every mint.
    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    // ── Invariants ────────────────────────────────────────────────────────────

    /// @notice A failure means the five tier weights no longer add up to the draw span.
    function invariant_theFiveWeightsTotalTheDrawSpan() public view {
        require(
            handler.weightTotal() == loot.WEIGHT_TOTAL_PER_MILLE(),
            "the five tier weights do not total WEIGHT_TOTAL_PER_MILLE"
        );
    }

    /// @notice A failure means a tier weight moved off the number the scale declares.
    function invariant_everyTierKeepsItsDeclaredWeight() public view {
        require(loot.tierWeight(loot.CALX()) == 600, "Calx is not weight 600");
        require(loot.tierWeight(loot.CAUDA_PAVONIS()) == 250, "Cauda Pavonis is not weight 250");
        require(loot.tierWeight(loot.FLORES()) == 110, "Flores is not weight 110");
        require(loot.tierWeight(loot.ELIXIR()) == 35, "Elixir is not weight 35");
        require(loot.tierWeight(loot.MAGISTERIUM()) == 5, "Magisterium is not weight 5");
    }

    /// @notice A failure means a mint raised no tier counter, or raised two.
    function invariant_everyMintRaisesTheMintedTotalByOne() public view {
        require(
            loot.totalMinted() == handler.minted(),
            "totalMinted does not account for every minted item"
        );
    }

    /// @notice A failure means a roll at or above the draw span minted, or none was tried.
    function invariant_noRollAtOrAboveTheDrawSpanMints() public view {
        require(handler.spanAttempts() > 0, "no roll at or above the draw span was attempted");
        require(handler.spanSuccesses() == 0, "a roll at or above the draw span minted");
    }

    /// @notice A failure means a roll inside the draw span was refused, or none was tried.
    function invariant_everyRollInsideTheDrawSpanMints() public view {
        require(handler.insideSpanAttempts() > 0, "no roll inside the draw span was attempted");
        require(handler.insideSpanRefusals() == 0, "a roll inside the draw span was refused");
    }

    /// @notice A failure means a tier id outside the five minted, or none was tried.
    function invariant_noTierIdOutsideTheFiveMints() public view {
        require(handler.unknownTierAttempts() > 0, "no tier id outside the five was attempted");
        require(handler.unknownTierSuccesses() == 0, "a tier id outside the five minted an item");
    }

    /// @notice A failure means a drop to the zero address minted, or none was tried.
    function invariant_noDropToTheZeroAddressMints() public view {
        require(handler.zeroRecipientAttempts() > 0, "no drop to the zero address was attempted");
        require(handler.zeroRecipientSuccesses() == 0, "a drop to the zero address minted an item");
    }

    // ── The weight total ──────────────────────────────────────────────────────

    /// @notice A failure means the deployed scale carries weights the tier list does not declare.
    function test_the_five_weights_are_the_numbers_the_rarity_scale_declares() public view {
        require(loot.tierWeight(loot.CALX()) == 600, "Calx is not weight 600");
        require(loot.tierWeight(loot.CAUDA_PAVONIS()) == 250, "Cauda Pavonis is not weight 250");
        require(loot.tierWeight(loot.FLORES()) == 110, "Flores is not weight 110");
        require(loot.tierWeight(loot.ELIXIR()) == 35, "Elixir is not weight 35");
        require(loot.tierWeight(loot.MAGISTERIUM()) == 5, "Magisterium is not weight 5");
        require(
            handler.weightTotal() == 1000, "the five weights do not total 1000"
        );
        require(
            loot.WEIGHT_TOTAL_PER_MILLE() == 1000, "WEIGHT_TOTAL_PER_MILLE is not 1000"
        );
    }

    /// @notice A failure means the constructor refused the weight set it is deployed with.
    function test_the_constructor_admits_the_declared_weight_set() public {
        LootDropHandler freshHandler = new LootDropHandler();
        AcervatorLoot fresh = new AcervatorLoot(address(freshHandler));
        freshHandler.bind(fresh);

        require(
            freshHandler.weightTotal() == fresh.WEIGHT_TOTAL_PER_MILLE(),
            "a deployed loot contract carries a weight total other than the draw span"
        );
        require(
            keccak256(bytes(fresh.tierName(fresh.MAGISTERIUM()))) == keccak256("Magisterium"),
            "the rarest tier id does not carry the name Magisterium"
        );
    }

    /// @notice A failure means the weight total is not read from tiers, so the total proves nothing.
    function test_the_weight_total_follows_the_weight_held_in_tier_storage() public {
        (AcervatorLoot fresh, LootDropHandler freshHandler) = _freshPair();
        bytes32 slot = _weightSlot(fresh.CALX());

        require(
            uint256(VM.load(address(fresh), slot)) == 600,
            "the weight slot does not hold the weight the getter reads"
        );
        require(
            freshHandler.weightTotal() == fresh.WEIGHT_TOTAL_PER_MILLE(),
            "the weight total misses the draw span before any weight moves"
        );

        VM.store(address(fresh), slot, bytes32(uint256(599)));
        require(fresh.tierWeight(fresh.CALX()) == 599, "tierWeight does not read the weight slot");
        require(
            freshHandler.weightTotal() == 999,
            "a weight one below its declared number left the total on the draw span"
        );

        VM.store(address(fresh), slot, bytes32(uint256(600)));
        require(
            freshHandler.weightTotal() == fresh.WEIGHT_TOTAL_PER_MILLE(),
            "the restored weight did not return the total to the draw span"
        );
    }

    // ── The draw span the weight total defines ────────────────────────────────

    /// @notice A failure means mint admitted a roll the draw span does not contain.
    function test_a_roll_at_the_draw_span_is_refused_and_one_below_it_is_admitted() public {
        (AcervatorLoot fresh, LootDropHandler freshHandler) = _freshPair();
        uint256 span = fresh.WEIGHT_TOTAL_PER_MILLE();

        require(
            freshHandler.mintAs(address(0xCAFE), fresh.CALX(), span - 1) == 1,
            "a roll one below the draw span was refused"
        );

        _expectMintRefusal(
            freshHandler, address(0xCAFE), fresh.CALX(), span, "Loot: roll outside the draw span"
        );
        _expectMintRefusal(
            freshHandler,
            address(0xCAFE),
            fresh.CALX(),
            type(uint256).max,
            "Loot: roll outside the draw span"
        );

        require(fresh.totalMinted() == 1, "a refused roll raised the minted total");
    }

    /// @notice A failure means a tier id outside the five minted an item.
    function test_a_tier_id_outside_the_five_is_refused() public {
        (AcervatorLoot fresh, LootDropHandler freshHandler) = _freshPair();

        require(
            freshHandler.mintAs(address(0xCAFE), fresh.MAGISTERIUM(), 0) == 1,
            "the highest tier id was refused"
        );

        _expectMintRefusal(freshHandler, address(0xCAFE), 0, 0, "Loot: unknown tier");
        _expectMintRefusal(
            freshHandler, address(0xCAFE), fresh.TIER_COUNT() + 1, 0, "Loot: unknown tier"
        );
    }

    /// @notice A failure means a tier with no art minted, so the roll refusal could be the art one.
    function test_a_tier_holding_no_art_cannot_drop() public {
        (AcervatorLoot fresh, LootDropHandler freshHandler) = _freshBarePair();
        fresh.setTierSvg("Calx", ART);

        require(
            freshHandler.mintAs(address(0xCAFE), fresh.CALX(), 0) == 1,
            "the tier holding art was refused"
        );
        _expectMintRefusal(
            freshHandler,
            address(0xCAFE),
            fresh.CAUDA_PAVONIS(),
            0,
            "Loot: SVG not uploaded for this tier"
        );
    }

    /// @notice A failure means an address other than the dropper minted an item.
    function test_only_the_dropper_mints() public {
        (AcervatorLoot fresh, LootDropHandler freshHandler) = _freshPair();

        try fresh.mint(address(0xCAFE), fresh.CALX(), "kraken", "BTC/USD", 1, 0, bytes32(0)) {
            revert("the deployer minted an item");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Loot: caller is not the dropper"),
                "the deployer was refused for some other reason"
            );
        }
        require(fresh.totalMinted() == 0, "the refused mint raised the minted total");

        require(
            freshHandler.mintAs(address(0xCAFE), fresh.CALX(), 0) == 1,
            "the dropper's mint was refused"
        );
        require(fresh.totalMinted() == 1, "the dropper's mint raised no counter");
    }

    /// @notice A failure means a drop to the zero address minted an item.
    function test_a_drop_to_the_zero_address_is_refused() public {
        (AcervatorLoot fresh, LootDropHandler freshHandler) = _freshPair();
        _expectMintRefusal(freshHandler, address(0), fresh.CALX(), 0, "Loot: mint to zero address");
        require(fresh.totalMinted() == 0, "the refused mint raised the minted total");
    }

    // ── The metadata ──────────────────────────────────────────────────────────

    /// @notice A failure means uri no longer serves the JSON the metadata library builds.
    function test_the_lowest_tier_serves_the_json_the_metadata_library_builds() public {
        (AcervatorLoot fresh,) = _freshPair();
        require(
            keccak256(bytes(fresh.uri(fresh.CALX())))
                == keccak256(bytes(string.concat(URI_PREFIX, Base64.encode(bytes(CALX_JSON))))),
            "uri does not serve the declared Calx metadata as a base64 JSON data URI"
        );
    }

    /// @notice A failure means a token id outside the five served metadata instead of refusing.
    function test_a_token_id_that_does_not_exist_has_no_uri() public {
        (AcervatorLoot fresh,) = _freshPair();

        require(bytes(fresh.uri(fresh.CALX())).length > 0, "a tier that exists served no uri");

        _expectUriRefusal(fresh, 0);
        _expectUriRefusal(fresh, fresh.TIER_COUNT() + 1);
        _expectUriRefusal(fresh, type(uint256).max);
    }

    /// @notice A failure means two tiers share one uri, so the metadata is not per tier.
    function test_each_of_the_five_tiers_serves_its_own_uri() public {
        (AcervatorLoot fresh,) = _freshPair();
        uint256 span = fresh.TIER_COUNT();
        bytes32[] memory served = new bytes32[](span);

        for (uint256 i = 0; i < span; ++i) {
            served[i] = keccak256(bytes(fresh.uri(fresh.CALX() + i)));
        }
        require(
            served[0] == keccak256(bytes(fresh.uri(fresh.CALX()))),
            "one tier served two different uris on two reads"
        );
        for (uint256 i = 0; i < span; ++i) {
            for (uint256 j = i + 1; j < span; ++j) {
                require(served[i] != served[j], "two tiers served the same uri");
            }
        }
    }

    /// @notice A failure means the uri does not carry the tier's minted count.
    function test_the_uri_follows_the_minted_count() public {
        (AcervatorLoot fresh, LootDropHandler freshHandler) = _freshPair();
        bytes32 before = keccak256(bytes(fresh.uri(fresh.CALX())));

        require(
            freshHandler.mintAs(address(0xCAFE), fresh.CALX(), 0) == 1,
            "the mint that should move the uri was refused"
        );
        require(
            keccak256(bytes(fresh.uri(fresh.CALX()))) != before,
            "the uri did not move when the tier's minted count rose"
        );
        require(
            keccak256(bytes(fresh.uri(fresh.CAUDA_PAVONIS())))
                == keccak256(bytes(fresh.uri(fresh.CAUDA_PAVONIS()))),
            "a tier nothing minted served two different uris"
        );
    }

    /// @notice A failure means the uri does not carry the tier's own art.
    function test_the_uri_carries_the_art_uploaded_for_the_tier() public {
        (AcervatorLoot fresh,) = _freshBarePair();
        bytes32 bare = keccak256(bytes(fresh.uri(fresh.CALX())));

        fresh.setTierSvg("Calx", ART);
        bytes32 filled = keccak256(bytes(fresh.uri(fresh.CALX())));
        require(bare != filled, "the uri did not move when the tier's art was uploaded");

        require(
            keccak256(bytes(fresh.getTierSvg(fresh.CALX()))) == keccak256(bytes(ART)),
            "the tier does not hold the art that was uploaded"
        );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _freshPair() private returns (AcervatorLoot, LootDropHandler) {
        (AcervatorLoot fresh, LootDropHandler freshHandler) = _freshBarePair();
        fresh.setTierSvg("Calx", ART);
        fresh.setTierSvg("Cauda Pavonis", OTHER_ART);
        fresh.setTierSvg("Flores", ART);
        fresh.setTierSvg("Elixir", ART);
        fresh.setTierSvg("Magisterium", ART);
        return (fresh, freshHandler);
    }

    function _freshBarePair() private returns (AcervatorLoot, LootDropHandler) {
        LootDropHandler freshHandler = new LootDropHandler();
        AcervatorLoot fresh = new AcervatorLoot(address(freshHandler));
        freshHandler.bind(fresh);
        return (fresh, freshHandler);
    }

    function _weightSlot(uint256 tierId) private pure returns (bytes32) {
        return bytes32(
            uint256(keccak256(abi.encode(tierId, TIERS_SLOT))) + WEIGHT_FIELD_OFFSET
        );
    }

    function _expectMintRefusal(
        LootDropHandler target,
        address recipient,
        uint256 tierId,
        uint256 roll,
        string memory refusal
    ) private {
        try target.mintAs(recipient, tierId, roll) {
            revert("a mint the contract must refuse succeeded");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256(bytes(refusal)),
                "the refusal names some other reason"
            );
        }
    }

    function _expectUriRefusal(AcervatorLoot target, uint256 tierId) private view {
        try target.uri(tierId) {
            revert("a token id outside the five served metadata");
        } catch Error(string memory reason) {
            require(
                keccak256(bytes(reason)) == keccak256("Loot: unknown tier"),
                "the unknown token id was refused for some other reason"
            );
        }
    }
}
