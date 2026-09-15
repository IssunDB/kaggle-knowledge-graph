"""Shared driver for bulk-loading staged node/edge Parquet files into IssunDB.

Both `load_competition_kg.py` and `import_to_issundb.py` stage a different set of
node and edge files but load them the same way: generate a CLI script that
bulk-imports every file, declares uniqueness constraints and full-text indexes,
rebuilds the CSR snapshot, and prints statistics; then run the CLI, capture the
log, and validate that every node file imported in full, no edge row was
malformed, and no command errored.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

NODE_LINE = re.compile(r"imported (\d+) (\S+) nodes from (\S+)")
EDGE_LINE = re.compile(
    r"imported (\d+) (\S+) edges from (.+?) "
    r"\((\d+) unresolved endpoint\(s\), (\d+) malformed row\(s\)\)"
)


def count_data_rows(path: Path) -> int:
    """Count Parquet rows."""
    import polars as pl

    return int(pl.scan_parquet(path).select(pl.len()).collect().item())


def build_script(
    stage_dir: Path,
    node_files: list[tuple[str, str]],
    edge_files: list[tuple[str, str, str, str]],
    text_indexes: list[tuple[str, str]],
    missing_hint: str,
) -> tuple[str, dict[str, int]]:
    """Return the CLI script text and the expected per-file node row counts.

    Node files are listed before edges, so the edge importer can resolve
    endpoints by the auto-indexed `Id` property. `missing_hint` names the
    `make` target(s) to run first if a staged file is absent.
    """
    lines: list[str] = []
    expected_nodes: dict[str, int] = {}

    missing: list[str] = []
    for filename, label in node_files:
        path = (stage_dir / filename).resolve()
        if not path.exists():
            missing.append(filename)
            continue
        expected_nodes[filename] = count_data_rows(path)
        lines.append(f":import-nodes {path} {label}")
    for filename, src, dst, etype in edge_files:
        path = (stage_dir / filename).resolve()
        if not path.exists():
            missing.append(filename)
            continue
        lines.append(f":import-edges {path} {src} {dst} {etype}")

    if missing:
        raise SystemExit(f"missing staged files ({missing_hint}): " + ", ".join(missing))

    # Integrity: each table's id is unique, so a duplicate is a staging defect.
    for _, label in node_files:
        lines.append(f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.Id IS UNIQUE")
    # Full-text indexes for title and name search.
    for label, prop in text_indexes:
        lines.append(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")

    lines.append("rebuild-csr")
    lines.append("materialize-columns")
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

    seen_nodes: dict[str, int] = {}
    for imported, _label, path in NODE_LINE.findall(log_text):
        seen_nodes[Path(path).name] = int(imported)
    for filename, expected in expected_nodes.items():
        if filename not in seen_nodes:
            failures.append(f"{filename}: no import line found in log")
            continue
        imported = seen_nodes[filename]
        if imported != expected:
            failures.append(
                f"{filename}: imported {imported} nodes, expected {expected} staged rows"
            )

    for _imported, _etype, path, _unresolved, malformed in EDGE_LINE.findall(log_text):
        if int(malformed) != 0:
            failures.append(f"{Path(path).name}: {malformed} malformed edge row(s)")

    return failures


def run_cli(
    cli: Path, db: Path, map_size_gb: int, script_path: Path, log_path: Path
) -> tuple[int, str, float]:
    """Run the IssunDB CLI against `script_path`, recreating `db` from scratch.

    Returns (exit_code, log_text, elapsed_seconds).
    """
    if db.exists():
        shutil.rmtree(db)
    db.mkdir(parents=True, exist_ok=True)

    start = time.time()
    with (
        script_path.open("r", encoding="utf-8") as script,
        log_path.open("w", encoding="utf-8") as log,
    ):
        process = subprocess.run(
            [str(cli), "--map-size-gb", str(map_size_gb), str(db)],
            stdin=script,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    elapsed = time.time() - start
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    return process.returncode, log_text, elapsed


def load_and_validate(
    *,
    stage_dir: Path,
    db: Path,
    cli: Path,
    map_size_gb: int,
    script_path: Path,
    log_path: Path,
    node_files: list[tuple[str, str]],
    edge_files: list[tuple[str, str, str, str]],
    text_indexes: list[tuple[str, str]],
    missing_hint: str,
) -> int:
    """Build the load script, run the CLI, validate the result, and print a report.

    Returns the process exit code the caller should exit with (0 on success).
    """
    script_text, expected_nodes = build_script(
        stage_dir, node_files, edge_files, text_indexes, missing_hint
    )
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script_text, encoding="utf-8")
    print(f"Wrote load script to {script_path}")

    print(f"Loading into {db} (map size {map_size_gb} GiB)...")
    returncode, log_text, elapsed = run_cli(cli, db, map_size_gb, script_path, log_path)
    print(f"CLI finished in {elapsed:.1f}s (exit {returncode}); log at {log_path}")

    failures = validate(log_text, expected_nodes)

    # Echo the graph statistics block for a quick eyeball.
    stats_start = log_text.find("Database")
    if stats_start != -1:
        print("\n" + log_text[stats_start:].strip())

    if returncode != 0:
        failures.append(f"CLI exited with code {returncode}")
    if failures:
        print("\nCHECK FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nCHECK PASSED: all node files imported in full, no malformed edges, no errors.")
    return 0
