# AGENTS.md

This file provides guidance to coding agents collaborating on this repository.

## Mission

This project builds graph databases from the [Meta Kaggle](https://www.kaggle.com/datasets/kaggle/meta-kaggle) dataset and loads them
into [IssunDB](https://github.com/habedi/issun-db), an embedded graph database.
The pipeline stages source files with DuckDB, parses code imports with Polars, parses Python API calls with Tree-sitter, and bulk-loads nodes and edges through the IssunDB CLI.
The project priorities include correct graph construction, reproducible builds, scoped subset testing, and idiomatic Python.

## Core Rules

- Use English for code, comments, documentation, and tests.
- Stage with DuckDB, parse code imports with Polars, parse Python API calls with Tree-sitter, and load through the IssunDB command line interface. Do not mix these roles.
- Bulk-load nodes and edges with command line tools instead of Cypher queries.
- Keep the large local source data out of the repository.
- Ensure staging is deterministic by using a fixed seed rule and fixed source data.
- Validate staged edges against staged nodes before trusting a graph.
- Run `make format` and `make test` before declaring a change done.

## Practice Examples

- Good practices include adding competition-scope tunables to staging scripts and resolving edge endpoints by the auto-indexed `Id` property.
- Bad practices include bulk-loading relationships with Cypher queries and hardcoding absolute data paths.

## Writing Style

- Use Oxford commas in lists.
- Avoid em dashes by using semicolons or restructuring sentences.
- Avoid colorful adjectives and adverbs.
- Balance the use of noun phrases for checklist items and imperative verbs.
- Apply title case to headings in Markdown files.
- Use correct and complete sentences.
- Avoid made-up words, abbreviations, and colons in the middle of sentences.

## Data Locations

- Meta Kaggle dataset metadata is at `~/downloads/KW/meta-kaggle/` (override with `META_KAGGLE_DIR`).
- Meta Kaggle Code is sharded under `~/Downloads/KW/meta-kaggle-code/` (override with `META_KAGGLE_CODE_DIR`).

## Repository Layout

- `scripts/inspect_metadata.py` dumps schema and row counts.
- `scripts/stage_kernel_subset.py` stages top-voted kernels.
- `scripts/stage_competition_subset.py` stages competition metadata.
- `scripts/parse_imports.py` parses code imports.
- `scripts/parse_api_calls.py` parses Python API calls into `ApiCall` nodes and `CALLS` edges.
- `scripts/load_competition_kg.py` loads the Kaggle knowledge graph.
- `scripts/import_to_issundb.py` loads the kernel graph.
- `scripts/issundb_load.py` holds the loader logic shared by both load scripts.
- `databases/` includes staged files and graph databases.
- `bin/issundb-cli` includes the database command line tool binary.
- `bin/issundb-mcp` includes the MCP server binary.
- `examples/` includes Cypher query templates and MCP client configuration templates.

## Build Targets

- `make graph-kc` builds the Kaggle knowledge graph.
- `make comp-cli` opens the Kaggle knowledge graph in the IssunDB CLI.
- `make comp-mcp` runs the IssunDB MCP server for the Kaggle knowledge graph.
- `make kg-stage-all` stages the kernel graph.
- `make kg-load` loads the staged kernel graph, adds constraints and indexes, and validates the load.
- `make graph-kernel` builds the kernel knowledge graph end to end.
- `make kernel-cli` opens the kernel knowledge graph in the IssunDB CLI.
- `make kernel-mcp` runs the IssunDB MCP server for the kernel knowledge graph.
- `make help` lists all targets.

## Pipeline Constraints

- Node files are `Id`-first. The `Id` column is auto-indexed. Edge files contain source and destination `Id` keys.
- Unresolved edge endpoints are dropped. Malformed rows cause errors.
- Bulk loading must use `:import-edges` instead of Cypher `UNWIND ... CREATE` queries.
- Node property lookups use auto-indexed full-text indexes. Raw markup language bodies must be searched with `CONTAINS` scans.
- Cypher query lines take string literals verbatim.

## Workflow

The workflow includes stage identification before coding, schema checks in `databases/metadata_inventory.md`, scoped pipeline changes with tunable `make`
variables, dry run staging on subsets, code formatting, and repository documentation updates when behavior changes.

## Testing Expectations

- The database loader validates that every node file imports, no edge row is malformed, and constraints hold.
- DuckDB validates staged node and edge counts to confirm that no staged edge points to a missing node.
- Use red-green test-driven development (TDD) to write tests before implementing new features.
- Python helpers must pass `pytest` checks.

## Documentation Expectations

- Seed rule, schema, or build target changes require updates to `AGENTS.md` and `README.md`.
