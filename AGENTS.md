# AGENTS.md

This file provides guidance to coding agents collaborating on this repository.

## Mission

This project builds graph databases from the [Meta Kaggle](https://www.kaggle.com/datasets/kaggle/meta-kaggle)
dataset and loads them into [IssunDB](https://github.com/habedi/issun-db), an embedded graph database.
The pipeline stages a scoped subset of the source CSVs with DuckDB, parses code imports with Polars, then bulk-loads nodes and
edges through the IssunDB CLI.
Priorities, in order:

1. Correct graph construction: every staged edge resolves to staged endpoints, ids stay unique per label, and node
   and edge counts reconcile with the source.
2. Reproducible builds: a rebuild from fixed source data produces the same graph, driven by `make` targets.
3. Scoped subsets before full scale: prove a small, well-defined slice before widening the seed.
4. Idiomatic Python: typed, linted, and formatted with the project toolchain.

## Core Rules

- Use English for code, comments, docs, and tests.
- Stage with DuckDB, parse code with Polars, and load through the IssunDB CLI; do not mix those roles.
- Bulk-load with `:import-nodes` and `:import-edges`, never with Cypher `UNWIND ... CREATE` (see Pipeline Constraints).
- Keep the source data out of the repository: the Meta Kaggle CSV and code trees are large, local, and gitignored.
- Make staging deterministic: a fixed seed rule and fixed source data must produce identical staged CSVs.
- Validate every staged edge against staged nodes before trusting a graph.
- Format with `ruff format` (`make format`) and lint with `ruff` (`make lint`) before declaring a change done.

Quick examples:

- Good: add a competition-scope tunable to `scripts/stage_competition_subset.py` and surface it as a `make` variable.
- Good: resolve edge endpoints by the auto-indexed `Id` property with `:import-edges file Src Dst TYPE`.
- Bad: bulk-load relationships with `UNWIND $rows AS r MATCH ... CREATE`, which plans full label scans and runs out of memory.
- Bad: hardcode an absolute data path in a script instead of reading `META_KAGGLE_DIR` or `META_KAGGLE_CODE_DIR`.

## Writing Style

- Use Oxford commas in inline lists: "a, b, and c" not "a, b, c".
- Do not use em dashes. Restructure the sentence, or use a colon or semicolon instead.
- Avoid colorful adjectives and adverbs. Write "adjacency query" not "blazing adjacency query".
- Prefer noun phrases for checklist items over imperative verbs. Write "temp directory teardown" not "tear down the temp directory".
- Headings in Markdown files must be in title case: "Build from Source" not "Build from source". Minor words (a, an, the, and, but, or, for, in, on,
  at, to, by, of) stay lowercase unless they are the first word.

## Data Locations

These are large, local, and gitignored. They are not part of the repository.

- Meta Kaggle CSV metadata: `/media/data/home/downloads/KW/meta-kaggle/` (override with `META_KAGGLE_DIR`).
- Meta Kaggle Code (notebook and script source): `/home/hassan/Downloads/KW/meta-kaggle-code/`, sharded as
  `<id zero-padded to 10>[:4]/[4:7]/<id>.{ipynb,py,r,rmd}` (override with `META_KAGGLE_CODE_DIR`).

## Repository Layout

- `scripts/inspect_metadata.py`: source CSV schema and row-count dump.
- `scripts/stage_kernel_subset.py`: kernel-centered staging (top-voted kernels).
- `scripts/stage_competition_subset.py`: competition-centered staging (post-2020 real competitions, ranked teams, scored submissions, top kernels, and
  discussions).
- `scripts/parse_imports.py`: Python and R import parsing over the code tree for the staged kernel versions, writing `nodes_library.csv` and
  `edges_kernel_version_imports_library.csv` into the stage directory.
- `scripts/load_competition_kg.py`: competition-graph loader; generates the CLI script (imports, uniqueness constraints, full-text indexes), runs it,
  and validates the result.
- `scripts/import_to_issundb.py`: kernel-graph loader.
- `tmp/issundb-cli`: prebuilt IssunDB CLI binary, built from the IssunDB repo at `~/Workspace/RustRoverProjects/issun-db` (
  `cargo build -p issundb-cli --release`, then copied here).
- `issundb/`: staged CSVs (`stage*/`) and the built graph database directories.
- `tmp/ISSUES.md`: recorded IssunDB load limitations and their workarounds.

## Build Targets

- `make graph-kc` builds the competition knowledge graph end to end into `issundb/competition-kg`: `comp-stage`,
  then `comp-parse-imports`, then `comp-load`. Tunables: `KERNELS_PER_COMPETITION`, `COMP_DB`, `MAP_SIZE_GB`.
- `make kg-stage-all` plus `scripts/import_to_issundb.py` builds the kernel graph.
- `make help` lists every target.

## Pipeline Constraints

- Node CSVs are `Id`-first with one property per column. The `Id` column is auto-indexed, and the edge importer resolves endpoints against it, so an
  edge CSV is two columns of source and destination `Id` keys plus a header.
- Unresolved edge endpoints are dropped and counted; they are expected for users and kernels outside the seed, and are not an error. Malformed rows
  are an error.
- Do not bulk-load relationships with Cypher `UNWIND ... CREATE`: it plans full label scans over millions of nodes and runs out of memory. Use
  `:import-edges` (see `tmp/ISSUES.md`).
- Node property lookups are auto-indexed, so a node `CREATE INDEX FOR (n:Label) ON (n.prop)` provisions a full-text index. Keep full-text indexes on
  short, clean fields. Raw HTML bodies such as forum messages carry tokens that exceed the LMDB full-text key-size limit, so search those with a
  `CONTAINS` scan.
- A `query` line takes its Cypher body verbatim, so a string literal such as `'pandas'` keeps its quotes.

## Workflow

Before coding:

1. Identification of whether the change is staging, code parsing, loading, indexing, or docs.
2. Reading of the touched script and the relevant source CSV schema in `tmp/metadata_inventory.md`.

Implementation:

1. A scoped change to one stage of the pipeline, with `make` variables for anything tunable.
2. A staging dry run on the chosen subset before a full load.
3. `make lint`, `make format`, and `make typecheck` before declaring a change done.
4. Update of `README.md`, this file, or `tmp/` planning notes when behavior or workflow changes.

## Testing Expectations

- The loader validates each build: every node file imports in full, no edge row is malformed, no command errors, and the per-label uniqueness
  constraints hold. A failed check exits non-zero so `make graph-kc` fails loudly.
- DuckDB is the independent oracle: reconcile staged node and edge counts and confirm no staged-edge points to a missing staged node.
- Keep `make test` (pytest) green for any Python helper that carries logic worth pinning.

## Documentation Expectations

- A change to the seed rule, the schema, or the build targets updates this file and `README.md` in the same change.
- A newly discovered IssunDB load limitation is recorded in `tmp/ISSUES.md` with its workaround.
