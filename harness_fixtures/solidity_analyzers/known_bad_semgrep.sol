// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.36;

// Calibration body for semgrep. transferOwnership has no caller check, which
// semgrep reports as solidity.security.unrestricted-transferownership.
contract KnownBadSemgrep {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function transferOwnership(address next) external {
        owner = next;
    }
}
