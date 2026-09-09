// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.36;

// Calibration body for slither. withdraw sends ether before clearing balances,
// which slither reports as reentrancy-eth at High severity.
contract KnownBadSlither {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "KnownBadSlither: nothing to withdraw");
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "KnownBadSlither: transfer failed");
        balances[msg.sender] = 0;
    }
}
