# contracts/evm: PmllAnchor (EVM analogue of pmll_anchor)

`src/PmllAnchor.sol` ports the Soroban contract in [`pmll-anchor/src/lib.rs`](../../pmll-anchor/src/lib.rs)
to Solidity. Only 32-byte digests go on-chain; payloads (manifests, proofs, memory) stay off-chain.

| Soroban (`lib.rs`) | Solidity (`PmllAnchor.sol`) |
|---|---|
| `init(admin)`: once, `admin.require_auth()` | `constructor(admin_)`: `msg.sender` must equal `admin_`, non-zero. Folding init into deployment removes the window in which someone else could initialise first. |
| `store(id, commitment)`: admin auth, `persistent().set` (always overwrites), extends TTL, publishes topics `("pmll","anchor")` with data `(id, commitment)` | `store(bytes32 id, bytes32 commitment)`: `onlyAdmin`, always overwrites, emits `Anchor(bytes32 indexed id, bytes32 commitment)` |
| `get(id) -> Option<BytesN<32>>` | `get(bytes32 id) -> (bool found, bytes32 commitment)`, so "never stored" differs from a stored zero |
| `bump(id)`: admin auth, `extend_ttl`; the host fails with `Storage/MissingValue` for a missing entry; no event | `bump(bytes32 id)`: `onlyAdmin`, reverts `MissingValue(id)` if absent; no event. EVM storage has no TTL, so nothing else happens. |

## Test

```bash
cd contracts/evm
forge install foundry-rs/forge-std@v1.17.0 --no-git   # lib/ is git-ignored
forge test --gas-report
```

14 tests: constructor auth and zero-admin rejection, store/get round trip, `get` of a missing id,
storing a zero commitment, non-admin `store` and `bump` revert, overwrite replaces, the `Anchor`
event, `bump` on present and missing ids, and two fuzz tests (256 runs each).

No CI job runs these yet; adding one needs a `.github/workflows` change.

## Gas depends on the rule set

Measured on 2026-10-10 with geth 1.17.8 and solc 0.8.37 (gas used, not estimates, except the last column):

| Step | `geth --dev` (Bogota rules) | Amsterdam rules (simulated backend) | Osaka rules (simulated backend) | Sepolia `eth_estimateGas` |
|---|---|---|---|---|
| deploy | 317,760 | 2,067,258 | 317,760 | 2,084,614 |
| `store`, first write of an id | 244,572 | 238,572 | 68,632 | 241,633 (state override) |
| `store`, overwrite with the same value | 28,732 | 22,732 | 28,832 | not measured |
| `bump` | 24,215 | 18,215 | 24,215 | not measured |

`geth --dev` in 1.17.8 turns on every fork the client knows, including Bogota, which is not
scheduled on any public network. The Sepolia chainspec shipped with geth 1.17.8 has
`amsterdamTime` = 1791294816 (2026-10-06 09:53 ET), so Sepolia now runs Amsterdam rules.
Under Amsterdam, deploying this contract cost about 6.5x what it did under Osaka, and a first
write to an empty storage slot cost about 3.5x as much. Bogota (dev mode) prices that first write
about the same as Amsterdam but not the deployment. Use the column for the network you deploy to,
and re-estimate on the day. The Sepolia estimates were read-only calls; nothing was sent.

On a local `geth --dev` chain, the SAT proof manifest root from
[`proofs/sat-manifest`](../../proofs/sat-manifest) (re-verified with drat-trim first) was stored under id
`d9d20fc5…2425` and read back with `eth_call` as `true, 0x723cbe65…6078`.
That was a throwaway dev chain, not a public network.

`script/DeployAndAnchor.s.sol` and [`SEPOLIA.md`](SEPOLIA.md) describe a Sepolia deployment. It has not
been done. The script holds no key or RPC URL; the signer comes from the command line.
