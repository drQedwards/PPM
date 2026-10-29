# #71 wiring: ledger checkpoint, claim guard, throughput (2026-10-22, America/New_York)

All numbers are measured; nothing projected.

## 1. Coverage ledger checkpoint (`ledger_checkpoint.py`)
- Reads latest `Total` from keyhunt run.log, backs off 1% for thread-chunk overlap, appends a contiguous range from the last ledger `to`.
- Appended range 2: `0x77270a2348c6c9c3ed..0x77270a234e6c10b3af` = 24,247,726,018 keys (run total 24.49B at that log line).
- Ledger SHA-256: `0xd3f7e88c303aa428b4368fdcc0d95acdf1ace7613d33a1d498710f20172cb181`
- Anchored on Sepolia PmllAnchor `0x37Da96f2a88Ae7E67A7FB305891a8c433B8B5C8D`
  - id = sha256("pmll:btc-puzzle:71:coverage-ledger:2") = `0x4193f0eb6b295bf17ec97a25664e7a3c7dce9824d78d19b30ced716d4d7a4bd6`
  - tx `0x7c4af5d0d82ca6ce236a10bcf6510f8b6dbe1c1fde70e1aca45fe8b8c27b3e61`, block 11969208, status 1
  - `get(id)` readback returns (true, digest); digest matches.
- `--resume` restarts keyhunt from the ledger end only if found files are empty (not used in this run; keyhunt was not restarted).

## 2. Claim guard (`claim_guard.py`, read-only, never broadcasts)
- Watches found.txt / KEYFOUNDKEYFOUND.txt; on a hit writes ALERT.md (offline sign, private-relay submission only) and exits.
- Scores counterparties of 4 known sweepers/collectors with siphon-walk `rich_weight`, weights = learning-walk adaptive-prune best loop (loop 1, ratio 0.502).
- Pass 1: 400 edges (Ethereum via Blockscout; Base Blockscout returned 403 for all 8 calls), 225 counterparties, 168 not in the earlier siphon graph.
- Top: 1inch router 0x1111…2A65 (swaps by 0x09Cb…), delegate contract 0x7515…B698 receiving 12 txs from collector 0x8566… (latest 06:49 EDT today), lookalike-token (address-poisoning) senders 0x1597…2550 and 0xe0dd…4209.

## 3. Throughput
- 10-minute window (log t=240s→840s): 31,428,574 keys/s, nice 19, 6 threads.
- Daily odds = rate·86400 / 2^70 = 2.30e-9 ≈ 1 in 435M per day. found.txt empty.
