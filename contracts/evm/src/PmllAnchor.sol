// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title PmllAnchor (EVM analogue of the Soroban pmll_anchor contract)
/// @notice Ported from drQedwards/pmll pmll-anchor/src/lib.rs (main b48a0d2).
///         Only 32-byte digests are ever written on-chain; payloads stay off-chain.
///
/// Semantics mirrored from the Soroban source:
///  - store(id, commitment): admin-only; unconditional overwrite of any previous
///    commitment for `id` (Soroban: persistent().set); emits the anchor event
///    (Soroban topics ("pmll","anchor"), data (id, commitment)).
///  - get(id): public read; returns Option<BytesN<32>> -> (found, commitment).
///  - bump(id): admin-only; Soroban extends the entry TTL and fails with
///    Storage/MissingValue if the entry does not exist. EVM storage has no TTL,
///    so bump only checks auth + existence (reverts MissingValue otherwise).
///    Soroban bump publishes no event, so neither does this.
///  - init(admin): Soroban does a one-time init gated by admin.require_auth().
///    EVM deviation: init is folded into the constructor (msg.sender must equal
///    admin_), which removes the window where someone else could init first.
contract PmllAnchor {
    address public immutable admin;

    mapping(bytes32 => bytes32) private _commitment;
    mapping(bytes32 => bool) private _exists;

    /// @dev Mirrors Soroban event topics ("pmll", "anchor") with data (id, commitment).
    event Anchor(bytes32 indexed id, bytes32 commitment);

    error Unauthorized();
    error ZeroAdmin();
    error MissingValue(bytes32 id);

    constructor(address admin_) {
        if (admin_ == address(0)) revert ZeroAdmin();
        if (msg.sender != admin_) revert Unauthorized(); // admin.require_auth()
        admin = admin_;
    }

    modifier onlyAdmin() {
        if (msg.sender != admin) revert Unauthorized();
        _;
    }

    /// Atomic write of a 32-byte memory commitment. Payload stays off-chain.
    function store(bytes32 id, bytes32 commitment) external onlyAdmin {
        _commitment[id] = commitment;
        _exists[id] = true;
        emit Anchor(id, commitment);
    }

    function get(bytes32 id) external view returns (bool found, bytes32 commitment) {
        return (_exists[id], _commitment[id]);
    }

    function bump(bytes32 id) external view onlyAdmin {
        if (!_exists[id]) revert MissingValue(id);
    }
}
