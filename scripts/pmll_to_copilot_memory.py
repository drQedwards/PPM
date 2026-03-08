"""
Bridge between pmll-memory-mcp's session KV store and GitHub Copilot's repository memory system.

This script reads a JSON snapshot of KV pairs produced by the PMLL Memory MCP server's `flush`
tool (or exported manually) and posts them as GitHub Copilot repository memories via the GitHub
REST API.

Usage
-----
From a snapshot file:
    python scripts/pmll_to_copilot_memory.py --snapshot snapshot.json --repo owner/repo

From stdin:
    echo '{"key": "value"}' | python scripts/pmll_to_copilot_memory.py --repo owner/repo

Dry-run (no API calls):
    python scripts/pmll_to_copilot_memory.py --snapshot snapshot.json --repo owner/repo --dry-run

Filter to specific keys:
    python scripts/pmll_to_copilot_memory.py --snapshot snapshot.json --repo owner/repo --keys key1 key2

Environment variables:
    GITHUB_TOKEN        GitHub personal access token (can also be passed via --token)
    GITHUB_REPOSITORY   Repository in owner/repo format (can also be passed via --repo)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

_MAX_VALUE_LEN = 500
_GITHUB_API_BASE = "https://api.github.com"
_API_VERSION = "2025-04-01"
_MIN_VALUE_LEN_FOR_IMPORTANCE = 20


def _is_important(key: str, value: str) -> bool:
    """Return True if the KV pair looks like a meaningful fact worth persisting."""
    if len(value) < _MIN_VALUE_LEN_FOR_IMPORTANCE:
        return False
    try:
        float(value.strip())
        return False
    except ValueError:
        pass
    return True


def _format_memory(key: str, value: str) -> str:
    """Format a KV pair as a Copilot memory string, truncating the value if needed."""
    if len(value) > _MAX_VALUE_LEN:
        value = value[:_MAX_VALUE_LEN]
    return f"{key}: {value}"


def _post_memory(token: str, repo: str, content: str, dry_run: bool) -> bool:
    """Post a single memory string to the GitHub Copilot memories API.

    Returns True on success, False on failure.
    """
    owner, _, repo_name = repo.partition("/")
    if not owner or not repo_name:
        print(f"ERROR: Invalid repo format '{repo}'. Expected 'owner/repo'.", file=sys.stderr)
        return False

    url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo_name}/copilot/memories"
    payload = json.dumps({"content": content}).encode("utf-8")

    if dry_run:
        print(f"[dry-run] POST {url}")
        print(f"  payload: {payload.decode('utf-8')}")
        return True

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": _API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            _ = resp.read()
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: HTTP {exc.code} posting memory '{content[:60]}…': {body}", file=sys.stderr)
        return False
    except urllib.error.URLError as exc:
        print(f"ERROR: Network error posting memory '{content[:60]}…': {exc.reason}", file=sys.stderr)
        return False


def _load_snapshot(snapshot_path: str | None) -> dict:
    """Load a JSON snapshot from a file path or stdin."""
    if snapshot_path:
        try:
            with open(snapshot_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: Could not load snapshot from '{snapshot_path}': {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print(f"ERROR: Could not parse JSON from stdin: {exc}", file=sys.stderr)
            sys.exit(1)

    if not isinstance(data, dict):
        print("ERROR: Snapshot must be a flat JSON object (key→value).", file=sys.stderr)
        sys.exit(1)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Flush pmll-memory-mcp KV pairs to GitHub Copilot repository memories."
    )
    parser.add_argument(
        "--snapshot",
        metavar="FILE",
        help="Path to a JSON snapshot file. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--repo",
        metavar="OWNER/REPO",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="Target repository (owner/repo). Defaults to $GITHUB_REPOSITORY.",
    )
    parser.add_argument(
        "--token",
        metavar="TOKEN",
        default=os.environ.get("GITHUB_TOKEN", ""),
        help="GitHub token. Defaults to $GITHUB_TOKEN.",
    )
    parser.add_argument(
        "--keys",
        nargs="*",
        metavar="KEY",
        help="Explicit list of keys to export. If omitted, all keys are candidates.",
    )
    parser.add_argument(
        "--min-importance",
        action="store_true",
        default=False,
        help="Skip trivially short or numeric values (heuristic importance filter).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be posted without calling the API.",
    )
    args = parser.parse_args(argv)

    if not args.repo:
        print(
            "ERROR: No repository specified. Use --repo owner/repo or set $GITHUB_REPOSITORY.",
            file=sys.stderr,
        )
        return 1

    if not args.dry_run and not args.token:
        print(
            "ERROR: No GitHub token specified. Use --token or set $GITHUB_TOKEN.",
            file=sys.stderr,
        )
        return 1

    snapshot = _load_snapshot(args.snapshot)

    # Determine which keys to process
    if args.keys:
        keys = [k for k in args.keys if k in snapshot]
        missing = [k for k in args.keys if k not in snapshot]
        if missing:
            print(f"WARNING: Keys not found in snapshot: {', '.join(missing)}", file=sys.stderr)
    else:
        keys = list(snapshot.keys())

    # Apply importance filter if requested
    if args.min_importance:
        keys = [k for k in keys if _is_important(k, str(snapshot[k]))]

    if not keys:
        print("No keys to export after filtering.", file=sys.stderr)
        return 0

    succeeded = 0
    failed = 0
    for key in keys:
        value = str(snapshot[key])
        memory_str = _format_memory(key, value)
        ok = _post_memory(args.token, args.repo, memory_str, dry_run=args.dry_run)
        if ok:
            succeeded += 1
        else:
            failed += 1

    label = "[dry-run] Would post" if args.dry_run else "Posted"
    print(f"{label} {succeeded} memor{'y' if succeeded == 1 else 'ies'} successfully.", end="")
    if failed:
        print(f" {failed} failed.", end="")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
