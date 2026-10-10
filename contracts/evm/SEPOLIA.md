# Sepolia deployment (prepared, not sent)

Nothing here has been broadcast. The deployer signs with their own key. No key, mnemonic or RPC
secret is stored in this repository; keep `$SEPOLIA_RPC` in your shell, not in a file here.

## Gas to budget

Sepolia runs Amsterdam rules (see [README](README.md#gas-depends-on-the-rule-set)). Read-only
`eth_estimateGas` against Sepolia on 2026-10-10 gave 2,084,614 for the deployment and 241,633 for
the first `store` (with a state override for the contract code). Budget about 2.4M gas for the
script, and check `cast gas-price --rpc-url $SEPOLIA_RPC` on the day.

## Steps

1. Verify the root, from the repository root:
   ```bash
   DRAT_TRIM=/path/to/drat-trim python tools/sat_proof/verify_manifest.py proofs/sat-manifest \
     --expect-root 723cbe658e875821ac2fbb5cd8bfd6937f3a61a1aba7e6665aa6ae5e2c6e6078
   ```
   and confirm the id: `printf '%s' "drQedwards/pmll:sat-proof:3-sat-exact@8e49955:manifest-v0" | sha256sum`
   gives `d9d20fc50041f65a6beeeeca27348ebaf0e6044b849e009a611601202ced2425`.
2. Create a Sepolia-only signer: `cast wallet import sepolia-anchor --interactive` (encrypted
   keystore), or use `--ledger`. Fund it with Sepolia ETH from a faucet.
3. Dry run (simulates, sends nothing):
   ```bash
   cd contracts/evm
   forge script script/DeployAndAnchor.s.sol --rpc-url $SEPOLIA_RPC --account sepolia-anchor
   ```
4. Broadcast: the same command with `--broadcast` (optionally `--verify --etherscan-api-key ...`).
5. Read back:
   ```bash
   cast call <PmllAnchor address> 'get(bytes32)(bool,bytes32)' \
     0xd9d20fc50041f65a6beeeeca27348ebaf0e6044b849e009a611601202ced2425 --rpc-url $SEPOLIA_RPC
   ```
   Expect `true` and `0x723cbe658e875821ac2fbb5cd8bfd6937f3a61a1aba7e6665aa6ae5e2c6e6078`.
