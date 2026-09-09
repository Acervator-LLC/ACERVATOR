// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.36;

// Calibration body for solhint. setOwner authorises on msg.sender, so solhint
// reports no avoid-tx-origin.
contract KnownGoodSolhint {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function setOwner(address next) external {
        require(msg.sender == owner, "KnownGoodSolhint: not owner");
        owner = next;
    }
}
