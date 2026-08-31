# SCF Open Track brief — Secure Memory Persistence in Agentic Wallets

**Submitter:** Josef K. Edwards (`drQedwards`) · individual · no referral  
**Category on interest form:** End-User Application  
**Track:** Open Track  
**Requested budget:** $125,000 worth of XLM (Build Award cap is $150,000)  
**Status:** SCF Build **interest form submitted**. This file is the public technical brief for `#scf-general` and for a full Build form if/when invited.

This is **not** a claim that the project has been awarded. Interest-form confirmation is not a Build Award submission. SCF #45's full submission window closed 17 August 2026 (213 submissions). SCF #46 is open with an 8 November 2026 deadline. Community Vote for #45 is expected around 2 September 2026.

---

## One sentence

A C-core Python package manager plus an MCP memory layer for agents, with **off-chain payloads** and **live Stellar mainnet 32-byte SHA-256 commitments**, operated by a **human who signs every on-chain write**.

## Why this belongs on Stellar

Agent memory that dumps full context on-chain is an injection surface (prompt, NFT, Morse, social). The Stellar-shaped answer is the opposite:

1. Keep the episode **off-chain** (MCP silo + graph).
2. Commit only a **32-byte digest** on Soroban.
3. Require an **admin key held by a human** for `store` / `bump`.
4. Anyone can `get` and verify. Nobody has to trust the agent's story.

That is a novel primitive for **agentic wallets**: the wallet/agent can remember, but the chain only ever sees a hash the human authorized.

Open Track fit: this is not a wallet SDK wrap, not an existing DeFi building-block integration, and not an RFP response. It is a new commitment primitive for agent memory on Soroban.

---

## Live evidence (do not invent IDs)

Full explorer table: [`docs/STELLAR.md`](STELLAR.md). Invoke API: [`pmll/SKILL.md`](https://github.com/drQedwards/pmll/blob/main/SKILL.md).

| | |
|---|---|
| **Mainnet contract** | [`CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF`](https://stellar.expert/explorer/public/contract/CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF) |
| Testnet contract | [`CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU`](https://stellar.expert/explorer/testnet/contract/CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU) |
| Admin | `GBFOFCD3XDANQWSGMHKJJ2V3YXS2QQD7RNC4LMDBVNBTUJOQZ3RLSB3E` |
| Wasm hash | `1b6ad9c574e0f5c9e39968f836a410c03adcf057afa93a63d2710bd30fdd53ba` |
| Target | `wasm32v1-none` only (`soroban-sdk` 27.0.6) |
| Mainnet deploy | [`d76e622d…`](https://stellar.expert/explorer/public/tx/d76e622d641b2465d480470f851f604a8284427a4e680c872b3ff8209c825943) |
| Mainnet init | [`ecf3a637…`](https://stellar.expert/explorer/public/tx/ecf3a637077d998febeac9ed5edd1a12582b5fc38db855633f2b48d40a5ba7a5) |
| First mainnet `store` | [`a64481fe…`](https://stellar.expert/explorer/public/tx/a64481feb3aaf8d4ee1a383dfb3b1633b23df5a38d1b61d7c07f9e672f144bbf) |
| First mainnet `get` | `1445bb037d8948ac03687ede656c27bc480a74db74a88224821379280d9e64d1` |

On-chain API: `init(admin)`, `store(id, commitment)`, `get(id)`, `bump(id)`. Events `(pmll, anchor)`. TTL ~30 days. **`store` / `bump` are admin-only.** There is no permissionless write path.

---

## Human-in-the-loop (the $125k differentiator)

Grant reviewers should see hustle, not an unsupervised agent with a key.

**Protocol the operator actually used this week:**

1. Agent may draft, hash, and print the exact `stellar contract invoke` line.
2. Human reviews the 32-byte commitment and the ID.
3. Human funds (here: Circle CCTP V2 Base → Stellar USDC → XLM).
4. Human signs deploy / init / store on **mainnet**.
5. Human (or agent under instruction) calls `get` and **refuses** the write if the digest does not match.
6. Human restores operator-facing docs when an agent clobbers them (PPM `README.md` was overwritten to a 23-byte placeholder on 2026-08-31 and restored from git history in commit [`e71765bc`](https://github.com/drQedwards/PPM/commit/e71765bc309ebf86cff51ae27190a22e7bd97d99)).

**Hard rules**

- Do not invent a contract ID.
- Do not put the memory payload on-chain.
- Do not give the agent the admin seed.
- Do not treat NFT / Morse / X-account objects as oracle inputs.
- Confirm every ID on [stellar.expert](https://stellar.expert) before depending on it.

This week the human path was: recover the workstation after a brick → authorize funding → CCTP hop → create the admin account → upload wasm → deploy → init → store → `get` → document. That is the hustle the Open Track is meant to see.

---

## Value as a tool-solver (Drips + Stellar Wave 8)

[Drips project](https://www.drips.network/app/projects/github/drQedwards/PPM?exact) is where the **C primitive** was listed for retroactive / streaming support (`drQedwards/PPM`, splits toward maintainers and `drQedwards/contextplus`).

[Stellar Wave 8](https://www.drips.network/wave/stellar) ran **24 Aug 12:00 – 31 Aug 12:00**, $75,000 contributor pool. Wave is a 7-day issue sprint: contributors fix, merge, earn points, get paid in USDC on Stellar.

**What PPM / PMLL solves for that loop**

Wave contributors and maintainers are already doing high-volume, short-lived agent-assisted work. The failure mode is hallucinated context: an agent that “remembers” a contract ID, an NFT, or a social payload and writes it into the next PR or the next on-chain call.

The solver:

| Layer | Role |
|-------|------|
| C core (`Ppm.c` / `PMLL.c`) | Deterministic local primitive (hermetic env, silo) |
| MCP (`pmll-memory-mcp`) | Agent `peek` before expensive tools; short-term KV + long-term graph |
| `pmll-anchor` | Optional Stellar receipt: 32-byte commitment the human authorized |
| Human | Navigates path, signs, refuses bad IDs |

We are **not** claiming a Wave 8 payout in this brief. We are claiming the **tooling shape** Wave-style work needs: a memory layer that cannot be NFT-injected, and a Stellar commitment that only a human can finalize.

---

## Original interest-form record (abridged, not inflated)

| Field | As submitted |
|-------|----------------|
| Title | Secure Memory Persistence in Agentic Wallets |
| Website | https://github.com/drqedwards/contextplus |
| Planned Stellar integration / origin | https://www.drips.network/app/projects/github/drQedwards/PPM?exact |
| Track | OpenTrack |
| Submitter | Individual |
| Referral | No |

Traction claims from the form (operator-attested, not independently audited here): agent workflows already consume the MCP memory layer; evaluated against real X-account / agent-interaction traffic during the Bankr.bot incidents with no observed memory leak and no successful prompt-injection side-effect from that surface; one Morse NFT-injection attempt against the persistent agent was flagged and ignored in logs.

Planned (not live): map an ERC-8004-style persistent-memory oracle **through Stellar's protocol**, still as 32-byte commitments, never as full payloads.

---

## Requested $125,000 — tranche map

Handbook structure (10 / 20 / 30 / 40). Project timeline ≤ 6 months. Subsequent tranche within 90 days of the previous payment.

| Tranche | % | USD-equivalent | Deliverable |
|---------|---|----------------|-------------|
| **#0** | 10% | $12,500 | Award acceptance. Operator runbook published. Keys remain human-held. |
| **#1 MVP** | 20% | $25,000 | Wallet-facing commitment UX: hash episode → show 32-byte digest → human confirm → `store`. Threat-model draft (Tranche #2 handbook requirement). |
| **#2 Testnet+** | 30% | $37,500 | Public testnet faucet path, bump/TTL policy, monitoring, and a written **human-in-the-loop** certification (agent cannot `store`). Testnet contract is already live; this tranche productizes it. |
| **#3 Mainnet** | 40% | $50,000 | Production operator docs, Audit Bank intake if eligible, measured on-chain `store`/`get` volume, no payload-on-chain regressions. **Mainnet contract is already live**; this tranche is product + safety, not a first deploy. |

Shipping mainnet *before* the award is the point: tranche money extends the primitive into wallets and Wave/maintainer workflows, it does not buy a first contract ID.

---

## AI disclosure (Open Track requirement)

Agents (including Grok in this operator's loop) **assist** with documentation, invoke-line formatting, and repo hygiene. They do **not** hold the admin key, do **not** invent contract IDs, and do **not** submit SCF forms. On 2026-08-31 an agent overwrite of `README.md` was caught and restored by the human via git history + GitHub Actions. That incident is treated as evidence for HITL, not as a feature.

---

## What we will not do

- Invent or “placeholder” a Soroban contract ID.
- Store memory payloads, NFTs, or prompt text on-chain.
- Build `wasm32-unknown-unknown` on Rust 1.82+.
- Hand the admin seed to an agent, a Discord bot, or an MCP tool.
- Claim a $125,000 award that has not been voted.

---

## Links

| | |
|---|---|
| This brief | https://github.com/drQedwards/PPM/blob/main/docs/SCF.md |
| Discord paste | https://github.com/drQedwards/PPM/blob/main/docs/SCF-DISCORD.md |
| Live IDs | https://github.com/drQedwards/PPM/blob/main/docs/STELLAR.md |
| Contract + skill | https://github.com/drQedwards/pmll |
| Drips origin | https://www.drips.network/app/projects/github/drQedwards/PPM?exact |
| Context+ (form website) | https://github.com/drQedwards/contextplus |
| Demo | https://ppm-one.vercel.app |
| MCP | `npx pmll-memory-mcp` · `pip install pmll-memory-mcp` |
| SCF handbook Open Track | https://stellar.gitbook.io/scf-handbook/scf-awards/build-award/open-track |
| Interest / dashboard | https://communityfund.stellar.org |

Paste the announcement in Stellar Dev Discord → `#scf-general` from [`docs/SCF-DISCORD.md`](SCF-DISCORD.md) (fits in one 2,000-character message).
