"""Load the staged competition subset into an IssunDB database.

This driver generates an IssunDB CLI script that bulk-imports the staged node and
edge CSVs, declares uniqueness constraints and full-text indexes, rebuilds the CSR
snapshot, and prints statistics. It then runs the CLI, captures the log, and
validates the load: every node file must import in full, no edge row may be
malformed, and no command may error (a failed uniqueness constraint means the
source had duplicate ids). The process exits non-zero if any check fails, so
`make graph-kc` fails loudly rather than leaving a half-built graph.

Full-text indexes are declared only on short, clean text fields. `ForumMessage`
bodies are deliberately left out: their raw HTML carries unbroken tokens (long
URLs and base64) that exceed the LMDB full-text key-size limit. Message bodies
stay searchable through a `CONTAINS` scan.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Node CSV file names and the label each file's rows carry. Loaded before edges
# so the edge importer can resolve endpoints by the auto-indexed `Id` property.
NODE_FILES: list[tuple[str, str]] = [
    ("nodes_competition.parquet", "Competition"),
    ("nodes_team.parquet", "Team"),
    ("nodes_user.parquet", "User"),
    ("nodes_submission.parquet", "Submission"),
    ("nodes_kernel.parquet", "Kernel"),
    ("nodes_kernel_version.parquet", "KernelVersion"),
    ("nodes_tag.parquet", "Tag"),
    ("nodes_forum.parquet", "Forum"),
    ("nodes_forum_topic.parquet", "ForumTopic"),
    ("nodes_forum_message.parquet", "ForumMessage"),
    ("nodes_library.parquet", "Library"),
]

# Edge CSV file names with their source label, destination label, and type.
EDGE_FILES: list[tuple[str, str, str, str]] = [
    ("edges_team_competed_in_competition.parquet", "Team", "Competition", "COMPETED_IN"),
    ("edges_user_member_of_team.parquet", "User", "Team", "MEMBER_OF_TEAM"),
    ("edges_user_led_team.parquet", "User", "Team", "LED_TEAM"),
    ("edges_submission_for_team.parquet", "Submission", "Team", "FOR_TEAM"),
    ("edges_user_submitted.parquet", "User", "Submission", "SUBMITTED"),
    (
        "edges_submission_from_kernel_version.parquet",
        "Submission",
        "KernelVersion",
        "FROM_KERNEL_VERSION",
    ),
    (
        "edges_team_public_leaderboard_submission.parquet",
        "Team",
        "Submission",
        "PUBLIC_LEADERBOARD_SUBMISSION",
    ),
    (
        "edges_team_private_leaderboard_submission.parquet",
        "Team",
        "Submission",
        "PRIVATE_LEADERBOARD_SUBMISSION",
    ),
    ("edges_user_authored_kernel.parquet", "User", "Kernel", "AUTHORED_KERNEL"),
    ("edges_kernel_has_version.parquet", "Kernel", "KernelVersion", "HAS_VERSION"),
    ("edges_kernel_current_version.parquet", "Kernel", "KernelVersion", "CURRENT_VERSION"),
    ("edges_kernel_version_authored_by_user.parquet", "KernelVersion", "User", "AUTHORED_BY"),
    (
        "edges_kernel_version_uses_competition.parquet",
        "KernelVersion",
        "Competition",
        "USES_COMPETITION",
    ),
    ("edges_kernel_version_imports_library.parquet", "KernelVersion", "Library", "IMPORTS"),
    ("edges_kernel_tagged_with_tag.parquet", "Kernel", "Tag", "TAGGED_WITH"),
    ("edges_competition_tagged_with_tag.parquet", "Competition", "Tag", "TAGGED_WITH"),
    ("edges_competition_has_forum.parquet", "Competition", "Forum", "HAS_FORUM"),
    ("edges_forum_has_topic.parquet", "Forum", "ForumTopic", "HAS_TOPIC"),
    ("edges_forum_topic_has_message.parquet", "ForumTopic", "ForumMessage", "HAS_MESSAGE"),
    ("edges_user_posted_message.parquet", "User", "ForumMessage", "POSTED_MESSAGE"),
    ("edges_forum_message_replies_to.parquet", "ForumMessage", "ForumMessage", "REPLIES_TO"),
]

# Full-text indexes on short, clean text fields. ForumMessage.Message is omitted
# on purpose (see the module docstring).
TEXT_INDEXES: list[tuple[str, str]] = [
    ("Competition", "Title"),
    ("ForumTopic", "Title"),
    ("KernelVersion", "Title"),
    ("User", "DisplayName"),
]

NODE_LINE = re.compile(r"imported (\d+)/(\d+) (\S+) nodes from (\S+)")
EDGE_LINE = re.compile(
    r"imported (\d+) (\S+) edges from (.+?) "
    r"\((\d+) unresolved endpoint\(s\), (\d+) malformed row\(s\)\)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, default=Path("databases/staging_data"))
    parser.add_argument("--db", type=Path, default=Path("databases/comp-kg"))
    parser.add_argument("--cli", type=Path, default=Path("bin/issundb-cli"))
    parser.add_argument("--map-size-gb", type=int, default=8)
    parser.add_argument(
        "--script",
        type=Path,
        default=Path("databases/load_competition_kg.issun"),
        help="Path the generated CLI script is written to.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("databases/load_competition_kg.log"),
        help="Path the CLI output is captured to.",
    )
    return parser.parse_args()


def count_data_rows(path: Path) -> int:
    """Count Parquet rows."""
    import polars as pl

    return pl.scan_parquet(path).select(pl.len()).collect().item()


def build_script(stage_dir: Path) -> tuple[str, dict[str, int]]:
    """Return the CLI script text and the expected per-file node row counts."""
    lines: list[str] = []
    expected_nodes: dict[str, int] = {}

    missing: list[str] = []
    for filename, label in NODE_FILES:
        path = (stage_dir / filename).resolve()
        if not path.exists():
            missing.append(filename)
            continue
        expected_nodes[filename] = count_data_rows(path)
        lines.append(f":import-nodes {path} {label}")
    for filename, src, dst, etype in EDGE_FILES:
        path = (stage_dir / filename).resolve()
        if not path.exists():
            missing.append(filename)
            continue
        lines.append(f":import-edges {path} {src} {dst} {etype}")

    if missing:
        raise SystemExit(
            "missing staged files (run `make comp-stage comp-parse-imports` first): "
            + ", ".join(missing)
        )

    # Integrity: each table's id is unique, so a duplicate is a staging defect.
    for _, label in NODE_FILES:
        lines.append(f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.Id IS UNIQUE")
    # Full-text indexes for title and name search.
    for label, prop in TEXT_INDEXES:
        lines.append(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")

    lines.append("rebuild-csr")
    lines.append("stats")
    lines.append("quit")
    return "\n".join(lines) + "\n", expected_nodes


def validate(log_text: str, expected_nodes: dict[str, int]) -> list[str]:
    """Return a list of failure messages; empty means the load passed."""
    failures: list[str] = []

    # Any command-level error fails the load (including a rejected constraint).
    for line in log_text.splitlines():
        low = line.lower()
        if low.startswith("error") or "mdb_" in low or "storage dependency error" in low:
            failures.append(f"command error: {line.strip()}")

    seen_nodes: dict[str, tuple[int, int]] = {}
    for imported, total, _label, path in NODE_LINE.findall(log_text):
        seen_nodes[Path(path).name] = (int(imported), int(total))
    for filename, expected in expected_nodes.items():
        if filename not in seen_nodes:
            failures.append(f"{filename}: no import line found in log")
            continue
        imported, total = seen_nodes[filename]
        if imported != total:
            failures.append(f"{filename}: imported {imported} of {total} nodes")
        if total != expected:
            failures.append(f"{filename}: imported {total} nodes, expected {expected} staged rows")

    for _imported, _etype, path, _unresolved, malformed in EDGE_LINE.findall(log_text):
        if int(malformed) != 0:
            failures.append(f"{Path(path).name}: {malformed} malformed edge row(s)")

    return failures


def main() -> None:
    args = parse_args()
    script_text, expected_nodes = build_script(args.stage_dir)
    args.script.parent.mkdir(parents=True, exist_ok=True)
    args.script.write_text(script_text, encoding="utf-8")
    print(f"Wrote load script to {args.script}")

    if args.db.exists():
        print(f"Removing existing database directory {args.db}")
        shutil.rmtree(args.db)
    args.db.mkdir(parents=True, exist_ok=True)

    print(f"Loading into {args.db} (map size {args.map_size_gb} GiB)...")
    start = time.time()
    with (
        args.script.open("r", encoding="utf-8") as script,
        args.log.open("w", encoding="utf-8") as log,
    ):
        process = subprocess.run(
            [str(args.cli), "--map-size-gb", str(args.map_size_gb), str(args.db)],
            stdin=script,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    elapsed = time.time() - start
    print(f"CLI finished in {elapsed:.1f}s (exit {process.returncode}); log at {args.log}")

    log_text = args.log.read_text(encoding="utf-8", errors="replace")
    failures = validate(log_text, expected_nodes)

    # Echo the graph statistics block for a quick eyeball.
    stats_start = log_text.find("Database")
    if stats_start != -1:
        print("\n" + log_text[stats_start:].strip())

    if process.returncode != 0:
        failures.append(f"CLI exited with code {process.returncode}")
    if failures:
        print("\nCHECK FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)
    print("\nCHECK PASSED: all node files imported in full, no malformed edges, no errors.")


if __name__ == "__main__":
    main()
