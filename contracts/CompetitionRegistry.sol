// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — Competition Registry Contract
// Chain: Base (Coinbase L2)
// =============================================================================
// On-chain arbiter for Proof of Accumulation competitions.
//
// Lifecycle (mirrors Python competition_engine.py):
//   1. registerBot()     — bot commits capital + config hash
//   2. openCompetition() — operations locks registration, starts trading window
//   3. submitResult()    — bot posts Merkle root + performance claim
//   4. adjudicate()      — operations ranks submissions, mints ACRV to winners
//
// Two privileged callers, and they are different kinds of thing.
//
//   OPERATIONS   an immutable address written at construction. It runs the
//                season: openCompetition, activateCompetition,
//                closeForSubmission, adjudicate, advanceSeason and
//                cancelCompetition. Each of those runs every competition, so
//                none can sit behind a vote carrying a delay in days. The
//                address cannot move: there is no ownership handover and no
//                renounce. A lost key is repaired the way every other
//                unchangeable thing here is, by an L4 migration vote.
//   governance   the Governance contract. setPriceFeed is the one rule-bearing
//                function on this contract, because a feed decides what every
//                award is measured against, and it answers to a vote alone.
//
// The halt council halts the six operations functions for seven days. isHalted
// reads a timestamp in Governance and no call lifts a halt.
//
// Price verification:
//   Chainlink Data Feeds on Base verify that submitted trade prices are
//   plausible given the on-chain price at the claimed timestamp.
//   Full ZK circuit verification is a planned upgrade (see TODO below).
//
// Immutable guarantees:
//   • Ekthelius tier: at most 21 ACRV awards ever carry that tier name
//   • Grand Accumulator: at most 1,000 ACRV awards ever carry that tier name
//   • All competition results are permanently on-chain (append-only)
//
// Neither cap reaches AcervatorTrophy. This contract holds no reference to the
// NFT contract and mints no NFT. AcervatorTrophy declares its own four tier
// constants and enforces them in its own mint.
// =============================================================================
pragma solidity 0.8.36;

import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SafeCast} from "@openzeppelin/contracts/utils/math/SafeCast.sol";
import {AggregatorV3Interface} from
    "@chainlink/contracts/src/v0.8/shared/interfaces/AggregatorV3Interface.sol";
import {IHaltSource} from "./Governance.sol";

interface IACRV {
    function mint(address recipient, uint256 amount,
                  string calldata competitionId,
                  string calldata tierName) external;
    function remainingSupply() external view returns (uint256);
}

contract CompetitionRegistry is ReentrancyGuard {

    // ── Token reference ───────────────────────────────────────────────────────

    IACRV public immutable acrv;

    // ── Privileged callers ────────────────────────────────────────────────────

    /// Runs the season. Written at construction and unchangeable afterwards.
    address public immutable OPERATIONS;

    /// The deployer, and the only caller of setGovernance.
    address public immutable DEPLOYER;

    /// The Governance contract. Zero until setGovernance writes it, once.
    address public governance;

    // ── Tier supply caps (enforced on-chain, immutable) ───────────────────────

    uint256 public constant MAX_EKTHELIUS         = 21;
    uint256 public constant MAX_GRAND_ACCUMULATOR = 1_000;

    uint256 public mintedEkthelius        = 0;
    uint256 public mintedGrandAccumulator = 0;

    // ── Chainlink price feeds on Base ────────────────────────────────────────
    // Base mainnet:
    //   BTC/USD: 0x64c911996D3c6aC71f9b455B1E8E7266BcbD848F  // sweep-ignore: contract address, not a secret key
    //   ETH/USD: 0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70  // sweep-ignore: contract address, not a secret key
    // Base Sepolia:
    //   ETH/USD: 0x4aDC67696bA383F43DD60A9e78F2C97Fbbfc7cb1  // sweep-ignore: contract address, not a secret key
    // Seeded at construction. setPriceFeed is the only later writer and it
    // admits governance alone, so every change to this mapping is a passed vote.

    mapping(string => address) public priceFeeds; // symbol → feed address

    // ── Season state ─────────────────────────────────────────────────────────

    uint256 public currentSeason = 1;

    // Season reward curve: 500_000, 425_000, 361_250, ... (× 0.85 each season)
    // Records season issuance only. No on-chain check reads seasonMinted, so
    // the season budget is enforced off-chain by the Python engine.
    mapping(uint256 => uint256) public seasonMinted;

    // ── Competition storage ───────────────────────────────────────────────────

    enum CompStatus { REGISTRATION, ACTIVE, SUBMISSION, ADJUDICATED, CANCELLED }

    struct BotEntry {
        address wallet;     // Base wallet address to receive tokens
        bytes32 configHash; // SHA-256 of strategy config (proves consistency)
        uint256 capital;    // USD * 100 (cents, avoid float)
        bool    registered;
    }

    struct Submission {
        bytes32 merkleRoot;
        int256  startingValueCents;
        int256  finalValueCents;
        int256  advantageCents;     // final - starting
        int32   advantageBps;       // advantage / starting * 10000
        uint32  tradeCount;
        uint256 submittedAt;
        bool    submitted;
    }

    struct Competition {
        string     id;
        string     symbol;
        CompStatus status;
        uint256    season;
        uint256    openedAt;
        uint256    closedAt;
        uint256    adjudicatedAt;
        address[]  participants;
        string     marketRegime;   // "BULL" | "BEAR" | "SIDEWAYS" | "ANY"
        bool       exists;
    }

    mapping(string => Competition)                      public competitions;
    mapping(string => mapping(address => BotEntry))     public botEntries;
    mapping(string => mapping(address => Submission))   public submissions;
    mapping(string => address)                          public winners;
    mapping(string => string)                           public winnerTiers;

    string[] public competitionIds;  // all-time list

    // ── Award events (immutable on-chain record) ──────────────────────────────

    event CompetitionOpened(string indexed id, string symbol, uint256 season);
    event BotRegistered(string indexed compId, address indexed wallet, bytes32 configHash);
    event ResultSubmitted(string indexed compId, address indexed wallet,
                          bytes32 merkleRoot, int32 advantageBps);
    event Adjudicated(string indexed compId, address indexed winner,
                      string tier, uint256 tokensAwarded, uint256 season);
    event TierMinted(string tier, address recipient, uint256 amount,
                     string competitionId);
    event PriceFeedSet(string symbol, address feedAddress);

    event GovernanceSet(address indexed governance);

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor(address _acrv, address _btcFeed, address _ethFeed) {
        require(_acrv != address(0), "Registry: ACRV address required");
        require(_acrv.code.length > 0, "Registry: ACRV not a contract");
        acrv = IACRV(_acrv);
        OPERATIONS = msg.sender;
        DEPLOYER = msg.sender;
        if (_btcFeed != address(0)) priceFeeds["BTC/USDT"] = _btcFeed;
        if (_ethFeed != address(0)) priceFeeds["ETH/USDT"] = _ethFeed;
    }

    // ── Modifiers ─────────────────────────────────────────────────────────────

    modifier onlyOperations() {
        require(msg.sender == OPERATIONS, "Registry: caller is not operations");
        require(!isHalted(), "Registry: halted by the halt council");
        _;
    }

    modifier onlyGovernance() {
        require(governance != address(0), "Registry: governance not set");
        require(msg.sender == governance, "Registry: caller is not governance");
        _;
    }

    // ── Halt wiring, once ─────────────────────────────────────────────────────

    /**
     * @notice Name the Governance contract, permanently.
     * @dev    Callable once, by the deployer, on an address that already holds
     *         code. Until it lands setPriceFeed has no caller at all, so a feed
     *         set at construction is the only feed that exists.
     * @param governanceAddress The deployed Governance address
     */
    function setGovernance(address governanceAddress) external {
        require(msg.sender == DEPLOYER, "Registry: caller is not the deployer");
        require(governance == address(0), "Registry: governance already set");
        require(governanceAddress.code.length > 0, "Registry: governance not a contract");
        governance = governanceAddress;
        emit GovernanceSet(governanceAddress);
    }

    /// @notice Return whether the halt council has this registry halted right now.
    function isHalted() public view returns (bool) {
        address source = governance;
        if (source == address(0)) {
            return false;
        }
        return IHaltSource(source).isHalted(address(this));
    }

    // ── Price feed management, on a vote ─────────────────────────────────────

    /**
     * @notice Point a symbol at a Chainlink feed, on a passed vote.
     * @dev    Governance runs a new symbol at INTERFACE and a repointed symbol
     *         at CORE, because repointing changes what every award already
     *         measured against that symbol is compared to.
     * @param symbol The market symbol, such as BTC/USDT
     * @param feed   The Chainlink aggregator address
     */
    function setPriceFeed(string calldata symbol, address feed)
        external onlyGovernance
    {
        priceFeeds[symbol] = feed;
        emit PriceFeedSet(symbol, feed);
    }

    /**
     * @notice Get the latest price from Chainlink for a symbol.
     * @dev    All five values latestRoundData returns are checked. Chainlink
     *         marks answeredInRound deprecated and its own feeds set it equal
     *         to roundId, but setPriceFeed accepts any address, so the
     *         comparison still screens a feed that is not a Chainlink one.
     *
     *         A caller that needs a freshness ceiling compares updatedAt
     *         against that feed's heartbeat. No ceiling is set here, because
     *         the heartbeat differs per feed.
     * @return price in USD * 10^8 (Chainlink standard)
     * @return updatedAt timestamp the feed last wrote this answer
     */
    function getLatestPrice(string calldata symbol)
        external view returns (int256 price, uint256 updatedAt)
    {
        address feed = priceFeeds[symbol];
        require(feed != address(0), "Registry: no price feed for symbol");
        AggregatorV3Interface oracle = AggregatorV3Interface(feed);
        (
            uint80  roundId,
            int256  answer,
            uint256 startedAt,
            uint256 answeredAt,
            uint80  answeredInRound
        ) = oracle.latestRoundData();
        require(roundId != 0,               "Registry: oracle has no round");
        require(answeredInRound >= roundId, "Registry: oracle answer is stale");
        require(startedAt  != 0, "Registry: oracle round unstarted");
        require(answeredAt != 0, "Registry: round incomplete");
        require(answer      > 0, "Registry: price not positive");
        price     = answer;
        updatedAt = answeredAt;
    }

    // ── Competition lifecycle ─────────────────────────────────────────────────

    /**
     * @notice Create and open a new competition.
     */
    function openCompetition(
        string calldata id,
        string calldata symbol,
        uint256         season
    ) external onlyOperations {
        require(!competitions[id].exists, "Registry: competition ID already exists");
        Competition storage c = competitions[id];
        c.id       = id;
        c.symbol   = symbol;
        c.status   = CompStatus.REGISTRATION;
        c.season   = season;
        c.openedAt = block.timestamp;
        c.exists   = true;
        competitionIds.push(id);
        emit CompetitionOpened(id, symbol, season);
    }

    /**
     * @notice Register a bot for a competition.
     * @param compId     Competition identifier
     * @param configHash SHA-256(strategy_config) — proves config consistency
     * @param capitalUSD Starting capital in USD cents (e.g. 40000 = $400.00)
     */
    function registerBot(
        string  calldata compId,
        bytes32          configHash,
        uint256          capitalUSD
    ) external {
        Competition storage c = competitions[compId];
        require(c.exists,                             "Registry: competition not found");
        require(c.status == CompStatus.REGISTRATION,  "Registry: not in registration");
        require(!botEntries[compId][msg.sender].registered, "Registry: already registered");

        botEntries[compId][msg.sender] = BotEntry({
            wallet:     msg.sender,
            configHash: configHash,
            capital:    capitalUSD,
            registered: true
        });
        c.participants.push(msg.sender);
        emit BotRegistered(compId, msg.sender, configHash);
    }

    /// Close registration and move competition to ACTIVE.
    function activateCompetition(string calldata compId) external onlyOperations {
        Competition storage c = competitions[compId];
        require(c.status == CompStatus.REGISTRATION, "Registry: not in registration");
        require(c.participants.length >= 2,          unicode"Registry: need ≥ 2 participants");
        c.status = CompStatus.ACTIVE;
    }

    /// Close trading window and move to SUBMISSION.
    function closeForSubmission(
        string calldata compId,
        string calldata marketRegime
    ) external onlyOperations {
        Competition storage c = competitions[compId];
        require(c.status == CompStatus.ACTIVE, "Registry: not active");
        c.status      = CompStatus.SUBMISSION;
        c.closedAt    = block.timestamp;
        c.marketRegime = marketRegime;
    }

    /**
     * @notice Submit a performance result.
     * @dev    startValueCents must be positive. At zero the advantage
     *         division panics; below zero it inverts the sign of every
     *         ranking built on advantageBps.
     * @param compId          Competition ID
     * @param merkleRoot      Merkle root of all signed trades
     * @param startValueCents Starting portfolio value (USD cents)
     * @param finalValueCents Final portfolio value (USD cents)
     * @param tradeCount      Number of trades in the Merkle log
     */
    function submitResult(
        string  calldata compId,
        bytes32          merkleRoot,
        int256           startValueCents,
        int256           finalValueCents,
        uint32           tradeCount
    ) external nonReentrant {
        Competition storage c = competitions[compId];
        require(c.status == CompStatus.SUBMISSION,             "Registry: not in submission");
        require(botEntries[compId][msg.sender].registered,     "Registry: bot not registered");
        require(!submissions[compId][msg.sender].submitted,    "Registry: already submitted");
        require(tradeCount > 0,                                "Registry: no trades recorded");
        require(merkleRoot != bytes32(0),                      "Registry: null Merkle root");
        require(startValueCents > 0,                           "Registry: start value <= 0");

        int256 advantage   = finalValueCents - startValueCents;
        int32  advBps      = SafeCast.toInt32((advantage * 10000) / startValueCents);

        submissions[compId][msg.sender] = Submission({
            merkleRoot:          merkleRoot,
            startingValueCents:  startValueCents,
            finalValueCents:     finalValueCents,
            advantageCents:      advantage,
            advantageBps:        advBps,
            tradeCount:          tradeCount,
            submittedAt:         block.timestamp,
            submitted:           true
        });

        emit ResultSubmitted(compId, msg.sender, merkleRoot, advBps);
    }

    /**
     * @notice Adjudicate a competition and award tokens.
     * @dev    Owner calls this after verifying all submissions off-chain.
     *         Winner address and tier are determined off-chain; this function
     *         enforces supply caps and executes the mint.
     *         TODO: Replace owner call with on-chain ZK proof verification.
     *
     *         acrv.mint is the last statement. Every state write and both
     *         events land before it, so a re-entering token contract finds
     *         this competition already ADJUDICATED.
     *
     * @param compId       Competition ID
     * @param winnerWallet Wallet address of the winning bot
     * @param tierName     Rarity tier name ("Harvest", "Gold Fold", etc.)
     * @param tokenAmount  ACRV tokens to award (in wei, 18 decimals)
     */
    function adjudicate(
        string  calldata compId,
        address          winnerWallet,
        string  calldata tierName,
        uint256          tokenAmount
    ) external nonReentrant onlyOperations {
        Competition storage c = competitions[compId];
        require(c.status == CompStatus.SUBMISSION, "Registry: not in submission");
        require(submissions[compId][winnerWallet].submitted,
                "Registry: winner has no submission");

        // Tier supply cap enforcement (on-chain, immutable)
        bytes32 tierHash = keccak256(bytes(tierName));
        if (tierHash == keccak256("Ekthelius")) {
            require(mintedEkthelius < MAX_EKTHELIUS,
                    "Registry: Ekthelius supply of 21 exhausted");
            mintedEkthelius++;
        } else if (tierHash == keccak256("Grand Accumulator")) {
            require(mintedGrandAccumulator < MAX_GRAND_ACCUMULATOR,
                    "Registry: Grand Accumulator supply of 1,000 exhausted");
            mintedGrandAccumulator++;
        }

        // Finalise competition state
        c.status            = CompStatus.ADJUDICATED;
        c.adjudicatedAt     = block.timestamp;
        winners[compId]     = winnerWallet;
        winnerTiers[compId] = tierName;
        if (tokenAmount > 0) {
            seasonMinted[c.season] += tokenAmount;
        }

        emit Adjudicated(compId, winnerWallet, tierName, tokenAmount, c.season);
        emit TierMinted(tierName, winnerWallet, tokenAmount, compId);

        // Interaction, last
        if (tokenAmount > 0) {
            require(acrv.remainingSupply() >= tokenAmount,
                    "Registry: insufficient ACRV supply remaining");
            acrv.mint(winnerWallet, tokenAmount, compId, tierName);
        }
    }

    // ── Views ─────────────────────────────────────────────────────────────────

    function getParticipantCount(string calldata compId)
        external view returns (uint256)
    {
        return competitions[compId].participants.length;
    }

    function getParticipants(string calldata compId)
        external view returns (address[] memory)
    {
        return competitions[compId].participants;
    }

    function getSubmission(string calldata compId, address wallet)
        external view returns (Submission memory)
    {
        return submissions[compId][wallet];
    }

    function totalCompetitions() external view returns (uint256) {
        return competitionIds.length;
    }

    function remainingEkthelius() external view returns (uint256) {
        return MAX_EKTHELIUS - mintedEkthelius;
    }

    function remainingGrandAccumulator() external view returns (uint256) {
        return MAX_GRAND_ACCUMULATOR - mintedGrandAccumulator;
    }

    // ── Season management ─────────────────────────────────────────────────────

    function advanceSeason() external onlyOperations {
        currentSeason++;
    }

    // ── Emergency cancel ──────────────────────────────────────────────────────

    function cancelCompetition(string calldata compId) external onlyOperations {
        Competition storage c = competitions[compId];
        require(c.status != CompStatus.ADJUDICATED, "Registry: already adjudicated");
        c.status = CompStatus.CANCELLED;
    }
}
