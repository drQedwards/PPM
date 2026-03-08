# scripts/

Utility scripts for the PPM / PMLL Memory MCP project.

---

## `pmll_to_copilot_memory.py`

**Purpose**: Bridge between `pmll-memory-mcp`'s in-session KV store and GitHub Copilot's
repository memory system.  After a Copilot Coding Agent task completes and calls the `flush`
tool, this script reads the exported KV snapshot and posts each pair as a Copilot repository
memory via the GitHub REST API.

### Requirements

| Requirement | Details |
|-------------|---------|
| Python | 3.10 + (uses stdlib only — no pip installs needed) |
| `GITHUB_TOKEN` | A GitHub personal-access-token with `repo` scope (or Copilot memory scope) |
| `GITHUB_REPOSITORY` | Target repo in `owner/repo` format |

### Usage examples

```bash
# From a snapshot file
python scripts/pmll_to_copilot_memory.py \
    --snapshot snapshot.json \
    --repo drQedwards/PPM

# From stdin (e.g. piped from flush output)
echo '{"arch": "x86_64", "model": "gpt-4o"}' | \
    python scripts/pmll_to_copilot_memory.py --repo drQedwards/PPM

# Dry-run — prints what would be posted without hitting the API
python scripts/pmll_to_copilot_memory.py \
    --snapshot snapshot.json \
    --repo drQedwards/PPM \
    --dry-run

# Export only specific keys
python scripts/pmll_to_copilot_memory.py \
    --snapshot snapshot.json \
    --repo drQedwards/PPM \
    --keys arch model task_summary

# Skip trivially short / numeric values
python scripts/pmll_to_copilot_memory.py \
    --snapshot snapshot.json \
    --repo drQedwards/PPM \
    --min-importance

# Provide token explicitly (overrides $GITHUB_TOKEN)
python scripts/pmll_to_copilot_memory.py \
    --snapshot snapshot.json \
    --repo drQedwards/PPM \
    --token ghp_xxxxxxxxxxxx
```

### CLI reference

| Flag | Default | Description |
|------|---------|-------------|
| `--snapshot FILE` | stdin | Path to a JSON file containing the KV snapshot (`{"key": "value", ...}`) |
| `--repo OWNER/REPO` | `$GITHUB_REPOSITORY` | Target GitHub repository |
| `--token TOKEN` | `$GITHUB_TOKEN` | GitHub auth token |
| `--keys KEY [KEY ...]` | all keys | Explicit list of keys to export |
| `--min-importance` | off | Heuristic filter: skip values shorter than 20 chars or purely numeric |
| `--dry-run` | off | Print payloads without calling the API |

---

## Full Integration Flow

```
Agent task start
  └── Copilot Coding Agent loads pmll-memory-mcp (via .github/copilot/mcp.json)
        └── agent calls init → peek → set → ... → flush
              └── run: python scripts/pmll_to_copilot_memory.py \
                            --snapshot snapshot.json \
                            --repo owner/repo
                    └── GitHub Copilot Memory updated ✓
```

### Step-by-step

1. **Task start** — Copilot Coding Agent boots and reads `.github/copilot/mcp.json`, which
   starts the `pmll-memory-mcp` stdio server via `npx pmll-memory-mcp`.

2. **`init`** — Agent calls `init(session_id)` to allocate a 256-slot PMLL memory silo for
   the current task session.

3. **`peek` / `set` loop** — Before each expensive operation (API call, file read, computation),
   the agent calls `peek(session_id, key)`. On a cache miss it performs the operation, then
   `set(session_id, key, result)` to cache it for the rest of the task.

4. **`flush`** — At task completion the agent calls `flush(session_id)`.  The server returns
   `{"status": "flushed", "cleared_count": N}`.  Before clearing, save the session snapshot to
   a JSON file (see the server's `_slots` dict in `mcp/pmll_memory_mcp/kv_store.py`).

5. **Bridge script** — Run `pmll_to_copilot_memory.py` with the snapshot to promote important
   KV pairs to durable GitHub Copilot repository memories, so they survive across future
   agent sessions.
