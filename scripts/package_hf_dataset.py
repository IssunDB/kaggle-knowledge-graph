"""Package the staged competition graph as a Hugging Face dataset release.

The release is a directory holding every staged node and edge Parquet file under
`data/`, a `README.md` dataset card with the Hugging Face front matter, and a
`manifest.json` with row counts, byte sizes, and SHA-256 digests. The card
declares one viewer configuration per table, so each file browses on Hugging Face.

Nothing is uploaded here. Push the directory with the Hugging Face CLI once you
have reviewed it (see `make hf-upload`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import polars as pl

from load_competition_kg import EDGE_FILES, NODE_FILES
from parse_imports import expanded_path

DEFAULT_STAGE_DIR = Path("databases/staging_data")
DEFAULT_OUTPUT = Path("databases/hf-dataset")
DEFAULT_REPO_ID = "habedi/kaggle-knowledge-graph"
SOURCE_REPO_URL = "https://github.com/IssunDB/kaggle-knowledge-graph"
META_KAGGLE_URL = "https://www.kaggle.com/datasets/kaggle/meta-kaggle"
META_KAGGLE_CODE_URL = "https://www.kaggle.com/datasets/kaggle/meta-kaggle-code"


@dataclass
class TableInfo:
    filename: str
    kind: str
    rows: int
    bytes: int
    sha256: str
    columns: list[tuple[str, str]]
    label: str | None = None
    src: str | None = None
    dst: str | None = None
    etype: str | None = None


@dataclass
class ReleaseMeta:
    repo_id: str
    version: str
    snapshot: str
    source_commit: str
    packaged_on: str = field(default_factory=lambda: date.today().isoformat())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=expanded_path, default=DEFAULT_STAGE_DIR)
    parser.add_argument("--output", type=expanded_path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Date of the Meta Kaggle export the graph was staged from (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Release version tag; defaults to the snapshot date.",
    )
    parser.add_argument(
        "--source-commit",
        default=None,
        help="Git commit of this repository that produced the staging; defaults to HEAD.",
    )
    return parser.parse_args()


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _describe(path: Path) -> tuple[int, list[tuple[str, str]], str]:
    frame = pl.scan_parquet(path)
    rows = int(frame.select(pl.len()).collect().item())
    columns = [(name, str(dtype)) for name, dtype in frame.collect_schema().items()]
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return rows, columns, digest.hexdigest()


def collect_tables(
    stage_dir: Path,
    node_files: list[tuple[str, str]],
    edge_files: list[tuple[str, str, str, str]],
) -> list[TableInfo]:
    """Describe every staged table, nodes first, failing if any file is absent."""
    missing = [
        filename
        for filename, *_ in [*node_files, *edge_files]
        if not (stage_dir / filename).exists()
    ]
    if missing:
        raise SystemExit("missing staged files (run `make graph-kc` first): " + ", ".join(missing))

    tables: list[TableInfo] = []
    for filename, label in node_files:
        path = stage_dir / filename
        rows, columns, sha256 = _describe(path)
        tables.append(
            TableInfo(filename, "node", rows, path.stat().st_size, sha256, columns, label=label)
        )
    for filename, src, dst, etype in edge_files:
        path = stage_dir / filename
        rows, columns, sha256 = _describe(path)
        tables.append(
            TableInfo(
                filename,
                "edge",
                rows,
                path.stat().st_size,
                sha256,
                columns,
                src=src,
                dst=dst,
                etype=etype,
            )
        )
    return tables


def _config_name(filename: str) -> str:
    return Path(filename).stem


def _size_category(total_rows: int) -> str:
    bounds = [
        (1_000, "n<1K"),
        (10_000, "1K<n<10K"),
        (100_000, "10K<n<100K"),
        (1_000_000, "100K<n<1M"),
        (10_000_000, "1M<n<10M"),
        (100_000_000, "10M<n<100M"),
    ]
    for bound, category in bounds:
        if total_rows < bound:
            return category
    return "100M<n<1B"


def _front_matter(tables: list[TableInfo]) -> str:
    total_rows = sum(t.rows for t in tables)
    lines = [
        "---",
        "license: cc-by-nc-sa-4.0",
        "pretty_name: Kaggle Knowledge Graph",
        "language:",
        "- en",
        "tags:",
        "- kaggle",
        "- knowledge-graph",
        "- graph",
        "- competitions",
        "size_categories:",
        f"- {_size_category(total_rows)}",
        "configs:",
    ]
    for table in tables:
        lines += [
            f"- config_name: {_config_name(table.filename)}",
            "  data_files:",
            "  - split: train",
            f"    path: data/{table.filename}",
        ]
    lines.append("---")
    return "\n".join(lines)


def _columns_cell(table: TableInfo) -> str:
    return ", ".join(f"`{name}`" for name, _ in table.columns)


def render_card(tables: list[TableInfo], meta: ReleaseMeta) -> str:
    """Render the dataset card as Markdown with Hugging Face front matter."""
    nodes = [t for t in tables if t.kind == "node"]
    edges = [t for t in tables if t.kind == "edge"]
    total_nodes = sum(t.rows for t in nodes)
    total_edges = sum(t.rows for t in edges)
    total_bytes = sum(t.bytes for t in tables)

    body = f"""
# Kaggle Knowledge Graph

A knowledge graph built from Kaggle's public
[Meta Kaggle]({META_KAGGLE_URL}) (and [Meta Kaggle Code]({META_KAGGLE_CODE_URL})
datasets). It links competitions, teams, submissions, users, notebooks,
datasets, discussion forums, tags, organizations, and notebook code invocations.

**See the [project repository]({SOURCE_REPO_URL}) for build scripts and
documentation on the graph schema, data model, and usage examples.**

## Release

| Field | Value |
| --- | --- |
| Version | `{meta.version}` |
| Meta Kaggle snapshot | {meta.snapshot} |
| Build code | [{SOURCE_REPO_URL}]({SOURCE_REPO_URL}) at commit `{meta.source_commit}` |
| Nodes | {total_nodes:,} |
| Edges | {total_edges:,} |
| Size | {total_bytes / (1 << 20):,.0f} MiB |

File counts, byte sizes, and SHA-256 digests are recorded in `manifest.json`.

## Scope

The graph covers competitions enabled on or after 2020-01-01 (excluding Community events) and their
 associated entities:

- Ranked and medal-winning teams, their members, leaders, and leaderboard submissions.
- The 50 most-voted notebooks per competition, notebook version lineage, and referenced datasets.
- Competition discussion forums with topics, team write-ups, and messages (in raw HTML and Markdown).
- Tag taxonomy, host and owner organizations, imported libraries, and parsed Python API calls.

All edge endpoints resolve to nodes present in this release.

## Tables

### Nodes

| Label | File | Rows | Columns |
| --- | --- | ---: | --- |
"""
    for table in nodes:
        body += (
            f"| `{table.label}` | `{table.filename}` | {table.rows:,} | {_columns_cell(table)} |\n"
        )

    body += """
### Edges

| Type | From | To | File | Rows |
| --- | --- | --- | --- | ---: |
"""
    for table in edges:
        body += (
            f"| `{table.etype}` | `{table.src}` | `{table.dst}` | `{table.filename}` "
            f"| {table.rows:,} |\n"
        )

    body += f"""
## Usage

Query directly with DuckDB:

```python
import duckdb

duckdb.sql(\"\"\"
    SELECT c.Title, COUNT(*) AS teams
    FROM 'data/edges_team_competed_in_competition.parquet' e
    JOIN 'data/nodes_competition.parquet' c ON c.Id = e.to_competition_id
    GROUP BY c.Title
    ORDER BY teams DESC
    LIMIT 10
\"\"\").show()
```

Load with Hugging Face `datasets`:

```python
from datasets import load_dataset

competitions = load_dataset("{meta.repo_id}", "nodes_competition", split="train")
```

To query with Cypher, load the files into [IssunDB](https://github.com/IssunDB/issun-db) or
any other graph database of your choice.

## Limitations

- Snapshot from {meta.snapshot}; later Kaggle activity is not included.
- Covers competitions enabled on or after 2020-01-01 and at most 50 most-voted notebooks per competition.
- Library and API call tables cover only notebook versions available in Meta Kaggle Code.
- Forum messages are stored as raw Kaggle HTML and Markdown.

## Licensing and Privacy

Meta Kaggle data is licensed under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) for
non-commercial use with attribution.
Build scripts at [{SOURCE_REPO_URL}]({SOURCE_REPO_URL}) are licensed under the MIT License.
The dataset includes only public profile attributes and forum posts published by Kaggle.
"""
    return _front_matter(tables) + "\n" + body


def write_release(
    tables: list[TableInfo], meta: ReleaseMeta, stage_dir: Path, output: Path
) -> None:
    data_dir = output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for table in tables:
        shutil.copy2(stage_dir / table.filename, data_dir / table.filename)
    (output / "README.md").write_text(render_card(tables, meta), encoding="utf-8")
    manifest = {
        "repo_id": meta.repo_id,
        "version": meta.version,
        "meta_kaggle_snapshot": meta.snapshot,
        "packaged_on": meta.packaged_on,
        "source_commit": meta.source_commit,
        "license": "CC-BY-NC-SA-4.0",
        "tables": [asdict(table) for table in tables],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    meta = ReleaseMeta(
        repo_id=args.repo_id,
        version=args.version or args.snapshot,
        snapshot=args.snapshot,
        source_commit=args.source_commit or git_head(),
    )
    tables = collect_tables(args.stage_dir, NODE_FILES, EDGE_FILES)
    write_release(tables, meta, args.stage_dir, args.output)
    print(
        f"Packaged {len(tables)} tables ({sum(t.rows for t in tables):,} rows) into {args.output}"
    )


if __name__ == "__main__":
    main()
