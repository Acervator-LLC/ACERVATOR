// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.36;

// Calibration body for semgrep. transferOwnership checks msg.sender, so semgrep
// reports no unrestricted-transferownership.
contract KnownGoodSemgrep {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function transferOwnership(address next) external {
        require(msg.sender == owner, "KnownGoodSemgrep: not owner");
        owner = next;
    }
}
