// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.36;

// Calibration body for solhint. setOwner authorises on tx.origin, which solhint
// reports as avoid-tx-origin.
contract KnownBadSolhint {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function setOwner(address next) external {
        require(tx.origin == owner, "KnownBadSolhint: not owner");
        owner = next;
    }
}
