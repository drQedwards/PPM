// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "forge-std/Script.sol";
import "../src/PmllAnchor.sol";

/// Deploys PmllAnchor with the broadcaster as admin, then stores the SAT manifest root.
/// The signer is supplied on the command line (--account / --ledger); no key lives here.
contract DeployAndAnchor is Script {
    bytes32 constant ID = 0xd9d20fc50041f65a6beeeeca27348ebaf0e6044b849e009a611601202ced2425;
    bytes32 constant ROOT = 0x723cbe658e875821ac2fbb5cd8bfd6937f3a61a1aba7e6665aa6ae5e2c6e6078;

    function run() external returns (PmllAnchor a) {
        vm.startBroadcast();
        a = new PmllAnchor(msg.sender);
        a.store(ID, ROOT);
        vm.stopBroadcast();
        (bool found, bytes32 c) = a.get(ID);
        require(found && c == ROOT, "readback mismatch");
        console.log("PmllAnchor:", address(a));
    }
}
