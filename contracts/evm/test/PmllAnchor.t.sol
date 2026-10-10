// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "forge-std/Test.sol";
import "../src/PmllAnchor.sol";

contract PmllAnchorTest is Test {
    event Anchor(bytes32 indexed id, bytes32 commitment);
    PmllAnchor a;
    address admin = address(0xA11CE);
    address eve = address(0xE7E);
    bytes32 constant ID = 0xd9d20fc50041f65a6beeeeca27348ebaf0e6044b849e009a611601202ced2425;
    bytes32 constant ROOT = 0x723cbe658e875821ac2fbb5cd8bfd6937f3a61a1aba7e6665aa6ae5e2c6e6078;

    function setUp() public {
        vm.prank(admin);
        a = new PmllAnchor(admin);
    }

    function test_ConstructorSetsAdmin() public view {
        assertEq(a.admin(), admin);
    }

    function test_ConstructorRequiresAdminAuth() public {
        vm.prank(eve);
        vm.expectRevert(PmllAnchor.Unauthorized.selector);
        new PmllAnchor(admin);
    }

    function test_ConstructorRejectsZero() public {
        vm.expectRevert(PmllAnchor.ZeroAdmin.selector);
        new PmllAnchor(address(0));
    }

    function test_StoreGetRoundTrip() public {
        vm.prank(admin);
        a.store(ID, ROOT);
        (bool f, bytes32 c) = a.get(ID);
        assertTrue(f);
        assertEq(c, ROOT);
    }

    function test_GetMissingIsNone() public view {
        (bool f, bytes32 c) = a.get(ID);
        assertFalse(f);
        assertEq(c, bytes32(0));
    }

    function test_StoreZeroCommitmentIsSome() public {
        vm.prank(admin);
        a.store(ID, bytes32(0));
        (bool f, bytes32 c) = a.get(ID);
        assertTrue(f);
        assertEq(c, bytes32(0));
    }

    function test_NonAdminStoreReverts() public {
        vm.prank(eve);
        vm.expectRevert(PmllAnchor.Unauthorized.selector);
        a.store(ID, ROOT);
        (bool f,) = a.get(ID);
        assertFalse(f);
    }

    function test_OverwriteReplaces() public {
        vm.startPrank(admin);
        a.store(ID, ROOT);
        a.store(ID, bytes32(uint256(1)));
        vm.stopPrank();
        (, bytes32 c) = a.get(ID);
        assertEq(c, bytes32(uint256(1)));
    }

    function test_StoreEmitsAnchor() public {
        vm.expectEmit(true, false, false, true, address(a));
        emit Anchor(ID, ROOT);
        vm.prank(admin);
        a.store(ID, ROOT);
    }

    function test_BumpExisting() public {
        vm.startPrank(admin);
        a.store(ID, ROOT);
        a.bump(ID);
        vm.stopPrank();
    }

    function test_BumpMissingReverts() public {
        vm.prank(admin);
        vm.expectRevert(abi.encodeWithSelector(PmllAnchor.MissingValue.selector, ID));
        a.bump(ID);
    }

    function test_BumpNonAdminReverts() public {
        vm.prank(admin);
        a.store(ID, ROOT);
        vm.prank(eve);
        vm.expectRevert(PmllAnchor.Unauthorized.selector);
        a.bump(ID);
    }

    function testFuzz_RoundTrip(bytes32 id, bytes32 c) public {
        vm.prank(admin);
        a.store(id, c);
        (bool f, bytes32 g) = a.get(id);
        assertTrue(f);
        assertEq(g, c);
    }

    function testFuzz_NonAdminNeverWrites(address who, bytes32 id, bytes32 c) public {
        vm.assume(who != admin);
        vm.prank(who);
        vm.expectRevert(PmllAnchor.Unauthorized.selector);
        a.store(id, c);
    }
}
