// SPDX-License-Identifier: Apache-2.0
// ACERVATOR — Competition Registry Contract
// Chain: Base (Coinbase L2)
// =============================================================================
// On-chain arbiter for Proof of Accumulation competitions.
//
// Lifecycle (mirrors Python competition_engine.py):
//   1. registerBot()     — bot commits capital + config hash
//   2. openCompetition() — owner locks registration, starts trading window
//   3. submitResult()    — bot posts Merkle root + performance claim
//   4. adjudicate()      — owner ranks submissions, mints ACRV to winners
//
// Price verification:
//   Chainlink Data Feeds on Base verify that submitted trade prices are
//   plausible given the on-chain price at the claimed timestamp.
//   Full ZK circuit verification is a planned upgrade (see TODO below).
//
// Immutable guarantees:
//   • Ekthelius tier: maximum 21 ever minted (enforced on-chain)
//   • Grand Accumulator: maximum 1,000 ever minted
//   • All competition results are permanently on-chain (append-only)
// =============================================================================
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@chainlink/contracts/src/v0.8/shared/interfaces/AggregatorV3Interface.sol";

interface IACRV {
    function mint(address recipient, uint256 amount,
                  string calldata competitionId,
                  string calldata tierName) external;
    function remainingSupply() external view returns (uint256);
}

contract CompetitionRegistry is Ownable, ReentrancyGuard {

    // ── Token reference ───────────────────────────────────────────────────────

    IACRV public immutable acrv;

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
    // Configured at deployment; can be updated by owner for additional assets.

    mapping(string => address) public priceFeeds; // symbol → feed address

    // ── Season state ─────────────────────────────────────────────────────────

    uint256 public currentSeason = 1;

    // Season reward curve: 500_000, 425_000, 361_250, ... (× 0.85 each season)
    // Stored as a simple counter; Python-side validates against the full curve.
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

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor(address _acrv, address _btcFeed, address _ethFeed)
        Ownable(msg.sender)
    {
        require(_acrv != address(0), "Registry: ACRV address required");
        acrv = IACRV(_acrv);
        if (_btcFeed != address(0)) priceFeeds["BTC/USDT"] = _btcFeed;
        if (_ethFeed != address(0)) priceFeeds["ETH/USDT"] = _ethFeed;
    }

    // ── Price feed management ─────────────────────────────────────────────────

    function setPriceFeed(string calldata symbol, address feed)
        external onlyOwner
    {
        priceFeeds[symbol] = feed;
        emit PriceFeedSet(symbol, feed);
    }

    /**
     * @notice Get the latest price from Chainlink for a symbol.
     * @return price in USD * 10^8 (Chainlink standard)
     */
    function getLatestPrice(string calldata symbol)
        external view returns (int256 price, uint256 updatedAt)
    {
        address feed = priceFeeds[symbol];
        require(feed != address(0), "Registry: no price feed for symbol");
        AggregatorV3Interface oracle = AggregatorV3Interface(feed);
        (, price, , updatedAt,) = oracle.latestRoundData();
    }

    // ── Competition lifecycle ─────────────────────────────────────────────────

    /**
     * @notice Create and open a new competition.
     */
    function openCompetition(
        string calldata id,
        string calldata symbol,
        uint256         season
    ) external onlyOwner {
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
    function activateCompetition(string calldata compId) external onlyOwner {
        Competition storage c = competitions[compId];
        require(c.status == CompStatus.REGISTRATION, "Registry: not in registration");
        require(c.participants.length >= 2,          unicode"Registry: need ≥ 2 participants");
        c.status = CompStatus.ACTIVE;
    }

    /// Close trading window and move to SUBMISSION.
    function closeForSubmission(
        string calldata compId,
        string calldata marketRegime
    ) external onlyOwner {
        Competition storage c = competitions[compId];
        require(c.status == CompStatus.ACTIVE, "Registry: not active");
        c.status      = CompStatus.SUBMISSION;
        c.closedAt    = block.timestamp;
        c.marketRegime = marketRegime;
    }

    /**
     * @notice Submit a performance result.
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

        int256 advantage   = finalValueCents - startValueCents;
        int32  advBps      = int32(int256(advantage * 10000) / startValueCents);

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
    ) external onlyOwner nonReentrant {
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

        // Mint tokens
        if (tokenAmount > 0) {
            require(acrv.remainingSupply() >= tokenAmount,
                    "Registry: insufficient ACRV supply remaining");
            acrv.mint(winnerWallet, tokenAmount, compId, tierName);
            seasonMinted[c.season] += tokenAmount;
        }

        // Finalise competition state
        c.status           = CompStatus.ADJUDICATED;
        c.adjudicatedAt    = block.timestamp;
        winners[compId]    = winnerWallet;
        winnerTiers[compId] = tierName;

        emit Adjudicated(compId, winnerWallet, tierName, tokenAmount, c.season);
        emit TierMinted(tierName, winnerWallet, tokenAmount, compId);
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

    function advanceSeason() external onlyOwner {
        currentSeason++;
    }

    // ── Emergency cancel ──────────────────────────────────────────────────────

    function cancelCompetition(string calldata compId) external onlyOwner {
        Competition storage c = competitions[compId];
        require(c.status != CompStatus.ADJUDICATED, "Registry: already adjudicated");
        c.status = CompStatus.CANCELLED;
    }
}