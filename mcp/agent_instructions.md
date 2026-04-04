# Context+ MCP - Agent Workflow

## TODO for copilot

- [ ] Do this todo exactly in order from top to bottom
- [ ] Use `forloopscode/contextplus` or the fork `drqedwards/contextplus` repos as reference alongside this repo always
- [ ] Include PMLL 5 MCP TOOLS. Use `mcp/readme.md` to find the specific tool names and use that information to update this `agent_instructions.md` so that PMLL's MCP short term memory tools such as `peek[...]`
- [ ] Compare test runtime speed using only Context+'s MCP tools using the original baseline of no tools at all to start. It is to be expected Context+ runs faster than baseline (see contextplus's documentation)
- [ ] Read this article found in quotations as food for thought:

  > "Think of what I'm about to say as if we have three "agents"/"persons" that are about to go into committee to collaborate with the same goal in mind.
  >
  > So let us say you give the same prompt and the chain of reasoning of commands kick off. Say, you tell the Claudes to update your NPMJS package on the registry. One agent does one solution that takes one path, while another agent does another solution taking another path.
  >
  > However, we have yet to discuss separate project context memory: aka, different prompts. For this one, we want to peek in short term instead of committing to long term that memory: that way you avoid overwriting valuable long-term memory.
  >
  > This is for abstracted contexts without any means of scoring. The last part is Boolean: whether your context is abstract or concrete. So that means… semantically speaking, if your three Claudes [...]"

- [ ] Once all four TODOs are complete, complete this final todo by deleting the TODO section completely for the PR

## Purpose

Context+ gives you structural awareness of the entire codebase without reading every file. These tools replace your default search and read operations — use them as your primary interface to the codebase.

## Tool Priority (Mandatory)

You MUST use Context+ tools instead of native equivalents. Only fall back to native tools when a Context+ tool cannot fulfill the specific need.

| Instead of…              | MUST use…                    | Why                                          |
|--------------------------|------------------------------|----------------------------------------------|
| `grep`, `rg`, `ripgrep`  | `semantic_code_search`       | Finds by meaning, not just string match      |
| `find`, `ls`, `glob`     | `get_context_tree`           | Returns structure with symbols + line ranges |
| `cat`, `head`, read file | `get_file_skeleton` first    | Signatures without wasting context on bodies |
| manual symbol tracing    | `get_blast_radius`           | Traces all usages across the entire codebase |
| keyword search           | `semantic_identifier_search` | Ranked definitions + call chains             |
| directory browsing       | `semantic_navigate`          | Browse by meaning, not file paths            |

## Workflow

1. Start every task with `get_context_tree` or `get_file_skeleton` for structural overview
2. Use `semantic_code_search` or `semantic_identifier_search` to find code by meaning
3. Run `get_blast_radius` BEFORE modifying or deleting any symbol
4. Prefer structural tools over full-file reads — only read full files when signatures are insufficient
5. Run `run_static_analysis` after writing code
6. Use `search_memory_graph` at task start for prior context, `upsert_memory_node` after completing work

## Execution Rules

- Think less, execute sooner: make the smallest safe change that can be validated quickly
- Batch independent reads/searches in parallel — do not serialize them
- If a command fails, diagnose once, pivot strategy, continue — cap retries to 1-2
- Keep outputs concise: short status updates, no verbose reasoning

## Tool Reference

| Tool                        | When to Use                                                  |
|-----------------------------|--------------------------------------------------------------|
| `get_context_tree`          | Start of every task. Map files + symbols with line ranges.   |
| `get_file_skeleton`         | Before full reads. Get signatures + line ranges first.       |
| `semantic_code_search`      | Find relevant files by concept.                              |
| `semantic_identifier_search`| Find functions/classes/variables and their call chains.      |
| `semantic_navigate`         | Browse codebase by meaning, not directory structure.         |
| `get_blast_radius`          | Before deleting or modifying any symbol.                     |
| `get_feature_hub`           | Browse feature graph hubs. Find orphaned files.              |
| `run_static_analysis`       | After writing code. Catch errors deterministically.          |
| `propose_commit`            | Validate and save file changes.                              |
| `list_restore_points`       | See undo history.                                            |
| `undo_change`               | Revert a change without touching git.                        |
| `upsert_memory_node`        | Create/update memory nodes (concept, file, symbol, note).    |
| `create_relation`           | Create typed edges between memory nodes.                     |
| `search_memory_graph`       | Semantic search + graph traversal across neighbors.          |
| `prune_stale_links`         | Remove decayed edges and orphan nodes.                       |
| `add_interlinked_context`   | Bulk-add nodes with auto-similarity linking.                 |
| `retrieve_with_traversal`   | Walk outward from a node, return scored neighbors.           |

## Anti-Patterns

1. Reading entire files without checking the skeleton first
2. Deleting functions without checking blast radius
3. Running independent commands sequentially when they can be parallelized
4. Repeating failed commands without changing approach
