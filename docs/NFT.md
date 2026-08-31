# PERSISTENT / vvNFT (Stellar Quest side quest)

Official checker (`ssq_01` / gist `803b72492199ef62f5f4333cfefc5e2f`) requires a SEP-39 NFT:

1. Quest account holds a non-XLM balance of exactly `0.0000001`.
2. That asset's **issuer** has `manageData` key `ipfshash`.
3. `https://ipfs.io/ipfs/<cid>` returns **JSON** with `issuer` + `code` matching the trustline.
4. That JSON's `url` fetches `200` (GitBook is used here).

A JPEG CID or an unpinned CID makes the checker throw **HTTP 500** (`Internal Server Error`) because `res.json()` rejects.

## Live mint (testnet, exact 3 ops)

| | |
|---|---|
| Asset | `vvNFT` |
| Amount | `0.0000001` |
| Issuer | `GBAKCSWCLLKGQUV2GYDAA7ETUYTVNUU5XQV4Y4PDICG255CODCB2WSK5` |
| Receiver | `GBNU76JVH7DC2HXFX2OCO4LEGJSBGQOLUFI7UAQGN4RD22W2LDI5ODBB` |
| ipfshash | `QmPKSEs7KXychweSp364bC3p62DQ4ZeFVheRXi7rFCsYad` |
| Metadata | [ipfs.io](https://ipfs.io/ipfs/QmPKSEs7KXychweSp364bC3p62DQ4ZeFVheRXi7rFCsYad) |
| url | https://pmll-persistent.vercel.app/ |
| Mint tx | [`98924533…`](https://stellar.expert/explorer/testnet/tx/98924533489e0c9ca2bd3437e10022d6685bcc1205d28e1a4d0a79d392acc8db) |

Ops: `manageData(ipfshash)` + `changeTrust` + `payment`. No `setOptions` (quest notes say not to use flags for this one).

GitBook: https://pmll-persistent.vercel.app/
