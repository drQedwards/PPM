# PMLL anchor results: items 1–3 (feat/php-js-depgraph)

Only SHA-256 digests are anchored. Payloads stay off-chain. No real funds were used.

- **id** = sha256("pmll:depgraph:feat/php-js-depgraph:items1-3") = `0xf6efc39c63a020558ee6b2b68786935b1ede3d7002cd68dfbecc16072a3796de`
- **root** (Merkle over 9 leaves, see anchor.php) = `0xe3632fd6ad6cfe927cf0977dc7b4195a60dbf47dd94dc9b703f33783230a51d9`

## Leaves (sha256)
- `file:fastroute_graph.json` `6788655d63767b70f8429c1d844374e2ec5dbac036bea9bec59326ee3260efe7`
- `file:fastroute_units.json` `d82ec140c49c3e4085450ae357acd51e4964981326161da50ddf1f4045908a02`
- `file:phantom-connect-sdk_graph.json` `04f1a930a8b7fddcb837751ff74a218d7b1e7ba29fa28ac416401a26e195f873`
- `file:phantom-connect-sdk_units.json` `0ea436cd4740c9ffb9bcc988581d57645ce377f85ca8fef40d03600b924744e9`
- `file:php-depgraph/README.md` `be15c359b32121fe5bc739a161ba8d7cbf20f44a1455854e595d22613a013cf3`
- `file:react-native-wallet-sdk-demo-app_graph.json` `660793a1d26a6fa2b8847a44a2fb6b15b3e6dea890ecbd527f6ce5792ae9c22d`
- `file:react-native-wallet-sdk-demo-app_units.json` `91687ab5597348ec2a2770b714cdcfe8c1ea5cf2954dc163c036168d3f29726c`
- `tree:pmll@feat/php-js-depgraph` `56b485c71059b3cd3fba129e221cd638f7cc10fc7f184582aff16cdc82748e6a`
- `tree:ppm@feat/php-js-depgraph` `d1256f2f70dc937b8dc3856ecc8041e582562df2d80562cf160e2809c40baa29`

The tree leaves are `sha256(git tree id)` of each branch *before* this commit. pmll tree is `394741d31452e095ecd3b8cafa94f1d7e70d7a45` and ppm tree is `1ff7856ffd550f59c60b12076b8a2d056caf7579`.

## Ethereum mainnet FORK (FORK-LOCAL, anvil, chain id 1, not on public mainnet)
- Fork of https://ethereum-rpc.publicnode.com at block **26247288** (hash `0x4e0b3ed0c303e40c2e5934c641b84aa2d87bf573d32e40029726af31b850fced`)
- PmllAnchor (fork-local): `0x024361c0eC3c1A9ED415E6ef3c859b48935DBe78`. Deploy tx (fork-local): `0x6e78d97a9605d374dfcea1727f8c00481de79bc639bcb9b8d3b5778c8f59e271`
- store tx (fork-local), sent by anchor.php: `0xa109acddbc0d29c2d06d28f51a724fe86ca5d8b7f4d91e9b4b8f34758a10ee77`, block 26247290, status 1
- anchor.php check: Anchor event (id, root) **OK**, get(id) read-back **OK**

## Stellar TESTNET (Soroban pmll_anchor, public testnet, friendbot-funded)
- Admin: `GD5N56NTVLX62OLUCDFBQJQ4F7NIBMLSFBC2L3XJYFF4SP4RDOB7LOMI`
- Contract: `CBMEMR3R5DYQIDDV26HSDTY4H3XIUDRZFJ76MNVFLOTRRTUMYBN7LNVG` (https://lab.stellar.org/r/testnet/contract/CBMEMR3R5DYQIDDV26HSDTY4H3XIUDRZFJ76MNVFLOTRRTUMYBN7LNVG)
- Deploy: https://stellar.expert/explorer/testnet/tx/0141eb6d3469ed2567e9fea0826a371d8d0006d40b3fe20fc394dfefd531fed0
- init: https://stellar.expert/explorer/testnet/tx/dfa25836773299a6b6b9ed79fc6031ffbc862ac352069dddb1e7a21fd51efb2f
- store: https://stellar.expert/explorer/testnet/tx/61544caae68b0cf75c7a98936377dc875d4f6fbc07afa4385be5fe8591bff115. The event `("pmll","anchor") = (id, root)` was emitted, and `get(id)` returns the root.

## Sepolia
This is now done. See the Sepolia section below.

## Run
    php anchor.php --dry                       # digests + root + manifest only
    anvil --fork-url <public RPC> --port 8547  # dev accounts are unlocked; no keys in code
    php anchor.php --rpc http://127.0.0.1:8547 --contract <PmllAnchor> --from <admin addr>

## Sepolia: public Ethereum testnet (both roots)
- Deployer/admin: `0x90610806f81974Ce692242391c12Df675b229A68` (faucet-funded SepETH, key never committed)
- PmllAnchor: [`0x37Da96f2a88Ae7E67A7FB305891a8c433B8B5C8D`](https://sepolia.etherscan.io/address/0x37Da96f2a88Ae7E67A7FB305891a8c433B8B5C8D). Deploy tx: [`0x0f7cb2dc…303a`](https://sepolia.etherscan.io/tx/0x0f7cb2dcb618e02fff29995922d4d989f24725213339fa29b94b73c2415a303a)
- Items 1–3 root (id `0xf6efc3…96de`): [`0x8c93a72dcd8aa395cf14a5507345873e31378b6c6241ede2c769056655d520f3`](https://sepolia.etherscan.io/tx/0x8c93a72dcd8aa395cf14a5507345873e31378b6c6241ede2c769056655d520f3), block 11968746. The Anchor event is **OK** and the get(id) read-back is **OK**.
- Crypto-repos root (id `0x7e25ec…d7a6`): [`0xd03525ae1d75e22ae10553bdfff3dd3ecdb4518dafd0030d63cc2b744150c78c`](https://sepolia.etherscan.io/tx/0xd03525ae1d75e22ae10553bdfff3dd3ecdb4518dafd0030d63cc2b744150c78c), block 11968747. The event is **OK** and the read-back is **OK**.
- Signed raw tx: `php anchor.php ... --key-env PRIVATE_KEY`. This runs `cast mktx` and then `eth_sendRawTransaction`. The items run uses `--manifest out/anchor_manifest.json` (frozen leaves).

# Crypto client repos (read-only shallow clones, nothing sent upstream)

| repo | commit | adapter | graph nodes / edges | build_to_memory nodes / edges / silo keys |
|---|---|---|---|---|
| ethereum/go-ethereum @ v1.17.9 | `9dffe6e976cbbb87a84c5fd395448f0950290def` | go_batch_build.py (-j8, --no-vet): 206 pkgs, 206 ok, build wall 157.47 s | (units only) | 513 / 2273 / 206 |
| jito-foundation/jito-solana (default branch) | `d33a18ac248053c269478163d9b3e601984a7676` | rust_depgraph.py (cargo metadata --no-deps) | 131 crates / 865 path-dep edges | 382 / 1169 / 131 |
| mempool/mempool backend (default branch) | `742955426d07a5b5f99cc02edb209e72bf2f143a` | js_depgraph.mjs | 386 / 1151 | 4 / 3 / 1 |
| mempool/mempool frontend | same | js_depgraph.mjs | 1287 / 2768 | 4 / 3 / 1 |

mempool has no root package.json, so backend/ and frontend/ were run separately. Each is a single package, so js_depgraph emits 1 unit, which explains the small build_to_memory counts.

- **id** = sha256("pmll:depgraph:crypto-repos:geth-jito-mempool") = `0x7e25ec0f47a9f4c2144a00b96fe10be36f9ad8368625da8555db351cddd2d7a6`
- **root** (10 leaves) = `0x8da01bfb39f4c5eae2bdc5ef28339ecca7702285e5d543a9a8a06493fdeb3faf`

- `commit:go-ethereum` `72ca688cbd1fe9d78d294f2f41d91e56892472e0ea1df66d554b6d4adff5b955`
- `commit:jito-solana` `e4d14c33ab0d81970221155f2f87c5bb6f34da9a98168f18cc8d6d8896ac8762`
- `commit:mempool` `c992a309e79cbcb609a5c82e1bb13ee2de1e51483b76114eed135056a07940ec`
- `file:go-ethereum_units.json` `1d20936f9f4844597726955b66e9ad92a655d58049dfc630e55b167b6bfc05db`
- `file:jito-solana_graph.json` `cc8474b89eadb8aa2e37ae902647aac1cfc4ae2a78e88ca06c8af31873154504`
- `file:jito-solana_units.json` `2b54687ef71b9250353cf1e7173ad333e684029c5bdb08c30b39007095e32c13`
- `file:mempool-backend_graph.json` `ce9a8c856b68ad14bdd1190a912df4dba91fbfd7f6fb1afcf41d536ec5de1638`
- `file:mempool-backend_units.json` `c95cad9e1d8cf746b73f2ad34589b0020fdd30624cae3f5d0d9e29aa39a0b872`
- `file:mempool-frontend_graph.json` `fea95443ee17f48a4ca3ea7f02d1041e81d98dc87bd9440ec18bf82fa3c16edb`
- `file:mempool-frontend_units.json` `62c8b6318b61f156c9476fe29ed461dcc5724a1532157253a1644bc66998d00c`
(commit leaves = sha256 of the 40-hex commit SHA string)

- Mainnet FORK (FORK-LOCAL anvil, same contract `0x024361c0eC3c1A9ED415E6ef3c859b48935DBe78`): tx `0x5e7c17273d742ca16cc2ae1a09c9cc5c26442bcd3910dd2aa4862df68bbc3e04`, block 26247291, status 1. The event is OK and the read-back is OK.
- Stellar TESTNET (`CBMEMR3R…LNVG`): https://stellar.expert/explorer/testnet/tx/4d44764eaaccd235805a666574afe214b8ca2787b3af557c62fb3876e3cd7761. The event is (id, root), and get(id) returns the root.
- Sepolia: see above.
