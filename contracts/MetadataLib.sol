// SPDX-License-Identifier: Apache-2.0
// ACERVATOR METADATA — the JSON helpers AcervatorTrophy and AcervatorLoot share
// =============================================================================
// Every function is internal and pure, so solc inlines each call site and no
// library address is deployed or delegatecalled.
//
// attr, attrNum and attrSigned each build one ERC-721 / ERC-1155 attributes
// entry. formatBps prints a basis-point figure as a signed percentage, and
// bytes32ToHex prints a Merkle root.
// =============================================================================
pragma solidity 0.8.36;

import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";
import {SafeCast} from "@openzeppelin/contracts/utils/math/SafeCast.sol";
import {SignedMath} from "@openzeppelin/contracts/utils/math/SignedMath.sol";

/// @title  Acervator Metadata
/// @author Anthony L. Brown
/// @notice The on-chain JSON helpers AcervatorTrophy and AcervatorLoot share.
library MetadataLib {
    using Strings for uint256;

    /// Basis points in one per cent, which formatBps divides and remainders by.
    uint256 private constant BPS_IN_A_PERCENT = 100;

    /// @notice One attributes entry whose value is a JSON string.
    /// @param key   The trait_type name
    /// @param value The trait value, quoted in the output
    /// @return The entry as JSON text
    function attr(string memory key, string memory value)
        internal pure returns (string memory)
    {
        return string.concat(
            "{\"trait_type\":\"", key, "\",\"value\":\"", value, "\"}");
    }

    /// @notice One attributes entry whose value is an unsigned JSON number.
    /// @param key   The trait_type name
    /// @param value The trait value, unquoted in the output
    /// @return The entry as JSON text
    function attrNum(string memory key, uint256 value)
        internal pure returns (string memory)
    {
        return string.concat(
            "{\"trait_type\":\"", key, "\",\"value\":", value.toString(), "}");
    }

    /// @notice One attributes entry whose value is a signed JSON number.
    /// @dev    SignedMath.abs carries the full int256 range, so the most
    ///         negative value formats instead of reverting.
    /// @param key   The trait_type name
    /// @param value The trait value, unquoted in the output
    /// @return The entry as JSON text
    function attrSigned(string memory key, int256 value)
        internal pure returns (string memory)
    {
        string memory v = value >= 0
            ? SafeCast.toUint256(value).toString()
            : string.concat("-", SignedMath.abs(value).toString());
        return string.concat("{\"trait_type\":\"", key, "\",\"value\":", v, "}");
    }

    /// @notice A basis-point figure as a signed percentage, 2950 to "+29.50%".
    /// @dev    SignedMath.abs carries the full int256 range, so the most
    ///         negative basis-point value formats instead of reverting.
    /// @param bps The figure in basis points
    /// @return The percentage as text, always carrying a sign
    function formatBps(int256 bps) internal pure returns (string memory) {
        string memory sign   = bps >= 0 ? "+" : "-";
        uint256 absBps       = SignedMath.abs(bps);
        uint256 whole        = absBps / BPS_IN_A_PERCENT;
        uint256 frac         = absBps % BPS_IN_A_PERCENT;
        string memory fracStr = frac < 10
            ? string.concat("0", frac.toString())
            : frac.toString();
        return string.concat(sign, whole.toString(), ".", fracStr, "%");
    }

    /// @notice A bytes32 value as 64 lowercase hex characters, with no 0x prefix.
    /// @param b The value to print
    /// @return The hex text
    function bytes32ToHex(bytes32 b) internal pure returns (string memory) {
        bytes memory hexChars = "0123456789abcdef";
        bytes memory str = new bytes(64);
        for (uint256 i = 0; i < 32; i++) {
            str[i*2]   = hexChars[uint8(b[i]) >> 4];
            str[i*2+1] = hexChars[uint8(b[i]) & 0x0f];
        }
        return string(str);
    }
}
