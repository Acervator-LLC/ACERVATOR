// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.36;

// Calibration body for the forge invariant runner. spend credits heldTotal and
// leaves walletsTotal standing, so the bucket sum passes totalEverMinted.

contract KnownBadForgeBuckets {
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
        require(msg.sender == REGISTRY, "bad: caller not registry");
        require(amount > 0, "bad: amount is zero");
        totalEverMinted += amount;
        balance[wallet] += amount;
        walletsTotal += amount;
    }

    function spend(address heldAddress, uint256 amount) external {
        require(amount > 0, "bad: amount is zero");
        require(balance[msg.sender] >= amount, "bad: balance below amount");
        balance[msg.sender] -= amount;
        heldBalance[heldAddress] += amount;
        heldTotal += amount;
    }
}

contract KnownBadForgeHandler {
    address public constant HELD = address(0xBEEF);

    KnownBadForgeBuckets public subject;

    function bind(KnownBadForgeBuckets buckets) external {
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

contract KnownBadForgeTest {
    KnownBadForgeBuckets public subject;
    KnownBadForgeHandler public handler;

    function setUp() public {
        handler = new KnownBadForgeHandler();
        subject = new KnownBadForgeBuckets(address(handler));
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
