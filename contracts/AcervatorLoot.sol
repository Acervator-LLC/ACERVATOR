// SPDX-License-Identifier: Apache-2.0
// ACERVATOR LOOT — ERC-1155 NFT
// Chain: Base (Coinbase L2)
// =============================================================================
// Loot dropped by a qualifying market, in five rarity tiers. One token id per
// tier, so every item of a tier shares one image and one attribute set, and the
// drop that produced it rides in the LootDropped event instead of in per-token
// storage.
//
// Metadata and artwork are fully on-chain. The JSON helpers come from
// MetadataLib, shared with AcervatorTrophy.
//
// The five tiers and their weights, in tenths of a per cent of the draw span:
//   Calx 600, Cauda Pavonis 250, Flores 110, Elixir 35, Magisterium 5.
// The constructor refuses a set that does not sum to WEIGHT_TOTAL_PER_MILLE,
// so the rarity scale cannot be deployed half-declared. No tier carries a
// lifetime ceiling: the weight is what makes a tier rare.
//
// Each tier carries two bonuses that augment a tournament action and no trading
// figure: impetusRelief takes Impetus off one action's cost, and
// effectBonusPerMille raises that action's effect.
//
// This contract holds no owner. mint admits dropper alone. setTierSvg writes a
// tier's art, and the write splits in two: the deployer may fill a tier that
// holds none, which is what makes a deployment mintable, and every later write
// to a tier that already holds art admits governance alone. setGovernance is
// the one other wiring call, admitted once from the deployer.
// =============================================================================
pragma solidity 0.8.36;

import {ERC1155} from "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";
import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";
import {IGovernedTrophy} from "./Governance.sol";
import {MetadataLib} from "./MetadataLib.sol";

/// @title  Acervator Loot
/// @author Anthony L. Brown
/// @notice Loot dropped by a qualifying market, in five rarity tiers, one token id each.
contract AcervatorLoot is ERC1155, IGovernedTrophy {
    using Strings for uint256;

    // ── State ─────────────────────────────────────────────────────────────────

    /// The address that deployed this contract. It fills an empty tier once.
    address public immutable DEPLOYER;

    /// The Governance contract. Zero until setGovernance writes it, once.
    address public governance;

    /// The only address that may mint a drop.
    address public immutable DROPPER;

    // ── The rarity scale ──────────────────────────────────────────────────────

    /// @notice Token ids, lowest tier first. Id 0 is never minted.
    uint256 public constant CALX          = 1;
    uint256 public constant CAUDA_PAVONIS = 2;
    uint256 public constant FLORES        = 3;
    uint256 public constant ELIXIR        = 4;
    uint256 public constant MAGISTERIUM   = 5;

    /// @notice The highest token id, and the number of tiers.
    uint256 public constant TIER_COUNT = 5;

    /// @notice Every tier weight adds up to this. 1000 tenths of a per cent.
    uint256 public constant WEIGHT_TOTAL_PER_MILLE = 1000;

    struct LootTier {
        string  name;
        string  shortForm;
        uint256 weightPerMille;
        uint256 impetusRelief;
        uint256 effectBonusPerMille;
        string  color;
    }

    mapping(uint256 => LootTier) public tiers;

    mapping(uint256 => uint256) public tierMinted;

    mapping(uint256 => string) private _tierSvgB64;

    mapping(string => uint256) private _tierIdByName;

    // ── Events ────────────────────────────────────────────────────────────────

    event LootDropped(
        address indexed recipient,
        uint256 indexed tierId,
        string  exchange,
        string  marketSymbol,
        uint256 season,
        uint256 roll,
        bytes32 rotationRoot
    );

    event SvgUpdated(string tier);

    event GovernanceSet(address indexed governance);

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor(address dropper) ERC1155("") {
        require(dropper != address(0), "Loot: dropper cannot be zero");
        require(dropper.code.length > 0, "Loot: dropper not a contract");
        DROPPER  = dropper;
        DEPLOYER = msg.sender;

        _setTier(CALX,          "Calx",          "Calx",        600, 0,  20, "#C8C0B4");
        _setTier(CAUDA_PAVONIS, "Cauda Pavonis", "Pavonis",     250, 0,  50, "#2E8BC0");
        _setTier(FLORES,        "Flores",        "Flores",      110, 1, 100, "#E8B84B");
        _setTier(ELIXIR,        "Elixir",        "Elixir",       35, 1, 200, "#B03060");
        _setTier(MAGISTERIUM,   "Magisterium",   "Magisterium",   5, 2, 500, "#F5F0E1");

        uint256 total = 0;
        for (uint256 id = CALX; id <= TIER_COUNT; ++id) {
            total += tiers[id].weightPerMille;
        }
        require(total == WEIGHT_TOTAL_PER_MILLE, "Loot: weights do not total 1000");
    }

    // ── Modifiers ─────────────────────────────────────────────────────────────

    modifier onlyDropper() {
        require(msg.sender == DROPPER, "Loot: caller is not the dropper");
        _;
    }

    // ── Governance wiring, once ───────────────────────────────────────────────

    /**
     * @notice Name the Governance contract that rewrites a filled tier, permanently.
     * @dev    Callable once, by the deployer, on an address that already holds code.
     * @param governanceAddress The deployed Governance address
     */
    function setGovernance(address governanceAddress) external {
        require(msg.sender == DEPLOYER, "Loot: caller is not the deployer");
        require(governance == address(0), "Loot: governance already set");
        require(governanceAddress.code.length > 0, "Loot: governance not a contract");
        governance = governanceAddress;
        emit GovernanceSet(governanceAddress);
    }

    // ── SVG management ────────────────────────────────────────────────────────

    /**
     * @notice Upload the base64-encoded SVG for a tier, named as the drop names it.
     * @dev    The deployer fills a tier that holds no art, which is what makes a
     *         deployment mintable. Rewriting a tier that already holds art is a
     *         change to what every holder of that tier sees, so it admits
     *         governance alone.
     * @param tier      The tier name, one of the five
     * @param svgBase64 The base64-encoded SVG
     */
    function setTierSvg(string calldata tier, string calldata svgBase64) external override {
        uint256 id = _tierIdByName[tier];
        require(id != 0, "Loot: unknown tier");
        if (bytes(_tierSvgB64[id]).length == 0) {
            require(msg.sender == DEPLOYER, "Loot: empty tier is the deployer's");
        } else {
            require(governance != address(0), "Loot: governance not set");
            require(msg.sender == governance, "Loot: filled tier is governance's");
        }
        _tierSvgB64[id] = svgBase64;
        emit SvgUpdated(tier);
    }

    function getTierSvg(uint256 tierId) external view returns (string memory) {
        return _tierSvgB64[tierId];
    }

    function tierIdOf(string calldata tier) external view returns (uint256) {
        return _tierIdByName[tier];
    }

    // ── Minting ───────────────────────────────────────────────────────────────

    /**
     * @notice Mint one item of a tier to a participant, recording the drop that made it.
     * @dev    The counter, the event and the art check all land before the
     *         transfer, so a recipient re-entering through onERC1155Received
     *         reads a finished balance.
     * @param recipient    The participant's wallet
     * @param tierId       One of the five tier ids
     * @param exchange     The exchange the market sits on
     * @param marketSymbol The qualifying market that dropped it
     * @param season       The season the drop happened in
     * @param roll         The draw that landed on this tier
     * @param rotationRoot The rotation commitment the market was drawn under
     * @return amount The holder's balance of tierId after the mint
     */
    function mint(
        address         recipient,
        uint256         tierId,
        string calldata exchange,
        string calldata marketSymbol,
        uint256         season,
        uint256         roll,
        bytes32         rotationRoot
    ) external onlyDropper returns (uint256 amount) {
        require(recipient != address(0), "Loot: mint to zero address");
        require(tierId >= CALX && tierId <= TIER_COUNT, "Loot: unknown tier");
        require(bytes(_tierSvgB64[tierId]).length > 0,
                "Loot: SVG not uploaded for this tier");
        require(roll < WEIGHT_TOTAL_PER_MILLE, "Loot: roll outside the draw span");

        ++tierMinted[tierId];

        emit LootDropped(recipient, tierId, exchange, marketSymbol,
                         season, roll, rotationRoot);

        _mint(recipient, tierId, 1, "");
        return balanceOf(recipient, tierId);
    }

    // ── uri — fully on-chain ──────────────────────────────────────────────────

    /**
     * @notice The ERC-1155 metadata for one tier, as a base64-encoded data URI.
     *         No external URLs. Art and metadata fully on-chain.
     * @param id The tier id
     * @return The data URI
     */
    function uri(uint256 id) public view override returns (string memory) {
        LootTier memory t = tiers[id];
        require(bytes(t.name).length > 0, "Loot: unknown tier");

        string memory attrs = string.concat(
            "[",
            MetadataLib.attr("Tier",        t.name),            ",",
            MetadataLib.attr("Short Form",  t.shortForm),       ",",
            MetadataLib.attrNum("Weight (per mille)", t.weightPerMille), ",",
            MetadataLib.attrNum("Impetus Relief",     t.impetusRelief),  ",",
            MetadataLib.attrNum("Effect Bonus (per mille)",
                                t.effectBonusPerMille),         ",",
            MetadataLib.attrNum("Minted",   tierMinted[id]),    ",",
            MetadataLib.attr("Tier Color",  t.color),
            "]"
        );

        string memory json = string.concat(
            "{\"name\":\"Acervator Loot ",
            unicode"— ", t.name,
            "\",\"description\":\"",
            "A Proof-of-Accumulation loot item dropped by a qualifying market. ",
            "Tier ", id.toString(), " of ", TIER_COUNT.toString(), ", weight ",
            t.weightPerMille.toString(), " of ",
            WEIGHT_TOTAL_PER_MILLE.toString(), ". ",
            "It augments a tournament action and no trading figure: ",
            t.impetusRelief.toString(), " Impetus off one action's cost and ",
            t.effectBonusPerMille.toString(),
            " of 1000 added to that action's effect.",
            "\",\"image\":\"data:image/svg+xml;base64,", _tierSvgB64[id],
            "\",\"attributes\":", attrs,
            "}"
        );

        return string.concat(
            "data:application/json;base64,",
            Base64.encode(bytes(json))
        );
    }

    // ── Views ─────────────────────────────────────────────────────────────────

    function totalMinted() external view returns (uint256 total) {
        for (uint256 id = CALX; id <= TIER_COUNT; ++id) {
            total += tierMinted[id];
        }
    }

    function tierWeight(uint256 id) external view returns (uint256) {
        return tiers[id].weightPerMille;
    }

    function tierName(uint256 id) external view returns (string memory) {
        return tiers[id].name;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /// @dev Writes one tier and its reverse name lookup. Constructor only.
    function _setTier(
        uint256 id,
        string memory name,
        string memory shortForm,
        uint256 weightPerMille,
        uint256 impetusRelief,
        uint256 effectBonusPerMille,
        string memory color
    ) private {
        tiers[id] = LootTier({
            name: name,
            shortForm: shortForm,
            weightPerMille: weightPerMille,
            impetusRelief: impetusRelief,
            effectBonusPerMille: effectBonusPerMille,
            color: color
        });
        _tierIdByName[name] = id;
    }
}
