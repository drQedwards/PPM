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
Not done. The box has no funded Sepolia key.

## Run
    php anchor.php --dry                       # digests + root + manifest only
    anvil --fork-url <public RPC> --port 8547  # dev accounts are unlocked; no keys in code
    php anchor.php --rpc http://127.0.0.1:8547 --contract <PmllAnchor> --from <admin addr>
