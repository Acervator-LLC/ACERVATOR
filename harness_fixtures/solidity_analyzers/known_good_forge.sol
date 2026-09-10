// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.36;

// Calibration body for the forge invariant runner. spend debits walletsTotal by
// the same amount it credits heldTotal, so the bucket sum equals totalEverMinted.

contract KnownGoodForgeBuckets {
    address public immutable REGISTRY;

    mapping(address => uint256) public balance;
    mapping(address => uint256) public heldBalance;

    uint256 public walletsTotal;
    uint256 public heldTotal;
    uint256 public totalEverMinted;

    constructor(address registryAddress) {
        REGISTRY = registryAddress;
    }

    function distil(address wallet, uint256 amount) external {
        require(msg.sender == REGISTRY, "good: caller not registry");
        require(amount > 0, "good: amount is zero");
        totalEverMinted += amount;
        balance[wallet] += amount;
        walletsTotal += amount;
    }

    function spend(address heldAddress, uint256 amount) external {
        require(amount > 0, "good: amount is zero");
        require(balance[msg.sender] >= amount, "good: balance below amount");
        balance[msg.sender] -= amount;
        walletsTotal -= amount;
        heldBalance[heldAddress] += amount;
        heldTotal += amount;
    }
}

contract KnownGoodForgeHandler {
    address public constant HELD = address(0xBEEF);

    KnownGoodForgeBuckets public subject;

    function bind(KnownGoodForgeBuckets buckets) external {
        subject = buckets;
    }

    function distil(uint256 amount) external {
        subject.distil(address(this), (amount % (1_000 * 10**18)) + 1);
    }

    function spend(uint256 amount) external {
        uint256 available = subject.balance(address(this));
        if (available == 0) {
            return;
        }
        subject.spend(HELD, (amount % available) + 1);
    }
}

contract KnownGoodForgeTest {
    KnownGoodForgeBuckets public subject;
    KnownGoodForgeHandler public handler;

    function setUp() public {
        handler = new KnownGoodForgeHandler();
        subject = new KnownGoodForgeBuckets(address(handler));
        handler.bind(subject);
        handler.distil(1_000 * 10**18);
    }

    /// @notice A failure means the buckets no longer hold every unit minted.
    function invariant_bucketsEqualTotalEverMinted() public view {
        require(
            subject.walletsTotal() + subject.heldTotal() == subject.totalEverMinted(),
            "buckets do not equal totalEverMinted"
        );
    }
}
