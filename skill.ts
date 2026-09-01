/**
 * skill.ts — typed off-chain codework / episode payload for pmll-anchor.
 *
 * Read https://skills.stellar.org before building on Stellar.
 *
 * Soroban contract ABI (pmll-anchor) stores ONLY a 32-byte commitment:
 *   init(admin) | store(id, commitment) | get(id) | bump(id)
 * Events: (pmll, anchor) → (id, commitment)
 *
 * This module types the OFF-CHAIN payload that SHA-256 hashes into that
 * commitment. It mirrors the post-merge C API in PMLL.h / PMLL.c
 * (semantic silo, peek dual-path, init_pml assignment=-1, SAT bridge)
 * and the MCP surface (MCPServer with FastMCP fallback).
 *
 * Do NOT invent on-chain fields. Verified contract IDs come from
 * stellar.toml / SKILL.md only.
 *
 * Shared byte-aligned across drQedwards/pmll and drQedwards/ppm.
 */

/** Fixed embedding dimensionality (PMLL_EMBED_DIM in PMLL.h). */
export const PMLL_EMBED_DIM = 32 as const;

/** Verified pmll-anchor deploys (2026-08-31). Confirm on explorer before use. */
export const PMLL_ANCHOR = {
  mainnet: {
    contractId: "CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF",
    admin: "GBFOFCD3XDANQWSGMHKJJ2V3YXS2QQD7RNC4LMDBVNBTUJOQZ3RLSB3E",
    wasmHash:
      "1b6ad9c574e0f5c9e39968f836a410c03adcf057afa93a63d2710bd30fdd53ba",
  },
  testnet: {
    contractId: "CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU",
    admin: "GBFOFCD3XDANQWSGMHKJJ2V3YXS2QQD7RNC4LMDBVNBTUJOQZ3RLSB3E",
    wasmHash:
      "1b6ad9c574e0f5c9e39968f836a410c03adcf057afa93a63d2710bd30fdd53ba",
  },
} as const;

/** Contract methods — matches pmll-anchor/src/lib.rs exactly. */
export type PmllAnchorMethod = "init" | "store" | "get" | "bump";

/** On-chain store args: two BytesN<32> only. */
export interface PmllAnchorStoreArgs {
  id: string; // 32-byte hex
  commitment: string; // 32-byte hex = SHA-256(serializeCodework(...))
}

/** -1 undecided, 0 false, 1 true — init_pml sets every assignment[i] = -1. */
export type AssignmentValue = -1 | 0 | 1;

/** One associative / semantic slot parallel to a tree index (silo_slot_t). */
export interface SiloSlot {
  key: string | null;
  content: string | null;
  /** L2-normalized vector, length embed_dim (PMLL_EMBED_DIM). */
  embedding: number[];
  resolved: boolean;
}

/**
 * memory_silo_t — integer tree + semantic slots.
 * tree is propagated layout (capacity size*2), not a 1:1 assignment mirror.
 */
export interface MemorySilo {
  tree: number[];
  size: number;
  slots: SiloSlot[];
  embed_dim: typeof PMLL_EMBED_DIM;
  slot_count: number;
}

/** pml_t core state after init_pml / refine. */
export interface PmlState {
  num_vars: number;
  num_clauses: number;
  assignment: AssignmentValue[];
  silo: MemorySilo;
  /** 1 = solved / terminated (NOT an assignment value). */
  flag: 0 | 1;
}

/**
 * peek dual-path (PMLL.c::peek) + semantic cosine path (peek_semantic).
 * MCP peek mirrors the key path; C also supports index + semantic.
 */
export type PeekPath = "key" | "index" | "semantic";

export interface PeekHit {
  hit: true;
  path: PeekPath;
  value: string;
  index: number;
  /** Present when path === "semantic" (cosine similarity). */
  sim?: number;
}

export interface PeekMiss {
  hit: false;
}

export type PeekResult = PeekHit | PeekMiss;

/** SAT stack bridge: 3SAT / boolean tokens → associative memory strings. */
export type SatBridgeKind =
  | "literal"
  | "clause"
  | "assignment_meanings";

export interface SatBridgeSnapshot {
  kind: SatBridgeKind;
  /** Associative memory string literals written via silo_set. */
  meanings: string[];
}

/** C API surface reflected for agents / lattice (names match PMLL.h). */
export const PMLL_C_API = [
  "init_silo",
  "update_silo",
  "free_silo",
  "silo_set",
  "peek",
  "peek_semantic",
  "silo_embed_text",
  "silo_cosine_similarity",
  "sat_bridge_literal",
  "sat_bridge_clause",
  "sat_bridge_assignment_meanings",
  "check_conflict",
  "pml_refine",
  "pml_logic_loop",
  "init_pml",
  "free_pml",
  "output_to_ppm",
] as const;

export type PmllCApiName = (typeof PMLL_C_API)[number];

/**
 * MCP server construction: prefer mcp 2.x MCPServer, fall back to FastMCP (1.x).
 * Matches mcp/pmll_memory_mcp/server.py and Ppm-lib/pmll_mcp/pmll_mcp_server.py.
 */
export const MCP_SERVER_COMPAT = {
  preferred: "mcp.server.mcpserver.MCPServer",
  fallback: "mcp.server.fastmcp.FastMCP",
  packageCaret: "^2.0.0",
} as const;

export type SkillId = "pmll" | "ppm" | "pmll-anchor" | "ARC-AGI-3" | string;

/**
 * Off-chain codework / episode payload.
 * serializeCodework() produces the UTF-8 bytes that hash to the 32-byte commitment.
 * Optional structured fields stay OFF-CHAIN forever — only the digest is stored.
 */
export interface CodeworkPayload {
  kind: "episode" | "codework";
  /** ISO-8601 UTC, e.g. 2026-08-31T19:42Z */
  iso: string;
  agent: string;
  skill: SkillId;
  event?: string;
  nodeId?: string;
  note?: string;
  title?: string;
  summary?: string;
  /** Optional structured snapshot (never sent on-chain). */
  memory?: {
    silo?: Pick<MemorySilo, "size" | "embed_dim" | "slot_count"> & {
      /** Compact slot view without full embedding vectors when hashing text form. */
      slots?: Array<Pick<SiloSlot, "key" | "content" | "resolved">>;
    };
    peek?: PeekResult;
    sat?: SatBridgeSnapshot;
    /** Document that init_pml left undecided literals at -1. */
    assignment_init?: -1;
  };
}

/**
 * Compose the canonical episode / codework text line(s).
 * Compatible with lattice composeEpisode and first-mainnet-store examples:
 *   episode:<iso> agent=<agent> [node=…] [skill=…] [event=…]
 */
export function serializeCodework(p: CodeworkPayload): string {
  const head = [`${p.kind}:${p.iso} agent=${p.agent}`];
  let line = head[0];
  if (p.nodeId) line += ` node=${p.nodeId}`;
  if (p.skill) line += ` skill=${p.skill}`;
  if (p.event) line += ` event=${p.event}`;
  const body: string[] = [line];
  if (p.note?.trim()) body.push(p.note.trim());
  if (p.title) body.push(p.title);
  if (p.summary) body.push(p.summary);
  if (p.memory) {
    const m = p.memory;
    const bits: string[] = [];
    if (m.assignment_init === -1) bits.push("assignment_init=-1");
    if (m.silo) {
      bits.push(
        `silo size=${m.silo.size} embed_dim=${m.silo.embed_dim ?? PMLL_EMBED_DIM} slot_count=${m.silo.slot_count}`,
      );
    }
    if (m.peek?.hit) {
      bits.push(
        `peek path=${m.peek.path} index=${m.peek.index}` +
          (m.peek.sim !== undefined ? ` sim=${m.peek.sim}` : ""),
      );
    }
    if (m.sat) {
      bits.push(`sat_bridge kind=${m.sat.kind} meanings=${m.sat.meanings.length}`);
    }
    if (bits.length) body.push(`memory: ${bits.join("; ")}`);
  }
  return body.join("\n");
}

export interface HashResult {
  payload: string;
  /** 64-char lowercase hex — SHA-256 of UTF-8 payload bytes. */
  commitment: string;
  /** 64-char lowercase hex — SHA-256(idHint) or SHA-256(commitment bytes). */
  id: string;
}

function toHex(bytes: Uint8Array): string {
  let out = "";
  for (const b of bytes) out += b.toString(16).padStart(2, "0");
  return out;
}

/**
 * Browser / Node 19+ subtle-crypto hash. Matches pmll-anchor/helper and
 * lattice/src/lib/pmll-anchor.ts hashPayload semantics.
 */
export async function hashCodework(
  payload: CodeworkPayload | string,
  idHint?: string,
): Promise<HashResult> {
  const text =
    typeof payload === "string" ? payload : serializeCodework(payload);
  const enc = new TextEncoder();
  const commitmentBytes = new Uint8Array(
    await crypto.subtle.digest("SHA-256", enc.encode(text)),
  );
  const idBytes = idHint
    ? new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(idHint)))
    : new Uint8Array(
        await crypto.subtle.digest("SHA-256", commitmentBytes as BufferSource),
      );
  return {
    payload: text,
    commitment: toHex(commitmentBytes),
    id: toHex(idBytes),
  };
}

/** Build store args for stellar contract invoke — no new ABI fields. */
export function toStoreArgs(hash: HashResult): PmllAnchorStoreArgs {
  return { id: hash.id, commitment: hash.commitment };
}

/**
 * Example post-merge codework describing semantic-silo reality.
 * Useful for docs / lattice sealed receipts — not auto-submitted.
 */
export function exampleSemanticSiloCodework(opts?: {
  iso?: string;
  agent?: string;
  skill?: SkillId;
}): CodeworkPayload {
  return {
    kind: "codework",
    iso: opts?.iso ?? "2026-08-31T22:30Z",
    agent: opts?.agent ?? "pmll-admin",
    skill: opts?.skill ?? "pmll",
    event: "align-skill-stellar-payload",
    note: "Post-merge semantic silo + peek dual-path + init_pml -1 + SAT bridge + MCPServer/FastMCP compat",
    memory: {
      assignment_init: -1,
      silo: {
        size: 8,
        embed_dim: PMLL_EMBED_DIM,
        slot_count: 0,
      },
      sat: {
        kind: "assignment_meanings",
        meanings: [],
      },
    },
  };
}
