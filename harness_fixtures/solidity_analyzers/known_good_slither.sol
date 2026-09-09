// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.36;

// Calibration body for slither. withdraw clears balances before sending ether,
// so slither reports no reentrancy.
contract KnownGoodSlither {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "KnownGoodSlither: nothing to withdraw");
        balances[msg.sender] = 0;
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "KnownGoodSlither: transfer failed");
    }
}
