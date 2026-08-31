# PERSISTENT NFT (testnet commemorative)

Stellar Quest [side quest 2](https://quest.stellar.org/side-quests/2) plaque for the live `pmll-anchor` milestone. **Not an oracle input.** Mainnet `pmll-anchor` still stores only 32-byte SHA-256 commitments.

GitBook (hosted): https://pmll-persistent.vercel.app/

| | |
|---|---|
| Network | **TESTNET** |
| Asset code | `PERSISTENT` |
| Amount | `0.0000001` |
| Issuer | `GDDXIJYA67VDS7EMN5OZKV7P6RCDNMV3SMYVLBPSRCNRXRYRFO5MVY4B` |
| Receiver (quest account) | `GBNU76JVH7DC2HXFX2OCO4LEGJSBGQOLUFI7UAQGN4RD22W2LDI5ODBB` |
| `ipfshash` | `QmRgvFjDY7JAChw2D7Y7MHdMjbNFDsUjta4kkWPYqmZVNH` |
| Issuer `home_domain` | `pmll-persistent.vercel.app` |
| Mint tx | [`eccc575f…`](https://stellar.expert/explorer/testnet/tx/eccc575fae9d6cb9f26607f65a24339f5693e2748dde7084d63db07accf01a80) |
| SEP-1 | https://pmll-persistent.vercel.app/.well-known/stellar.toml |
| Metadata | https://pmll-persistent.vercel.app/nft/metadata.json |

Issuer secret is **not** in this repo. Local operator file (chmod 600): `~/.stellar/persistent-nft-issuer.json`.

Quest account secret was used once to sign `changeTrust` + receive. **Rotate that key** if it was pasted into chat.
