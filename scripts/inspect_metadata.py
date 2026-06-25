"""Inspect Meta Kaggle CSV schemas and row counts with DuckDB."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb

DEFAULT_META_DIR = Path(
    os.environ.get("META_KAGGLE_DIR", "/media/data/home/downloads/KW/meta-kaggle")
)
DEFAULT_OUTPUT = Path("databases/metadata_inventory.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta-dir", type=Path, default=DEFAULT_META_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sql_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def main() -> None:
    args = parse_args()
    csv_files = sorted(args.meta_dir.glob("*.csv"))
    if not csv_files:
        raise SystemExit(f"No CSV files found in {args.meta_dir}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    lines = [
        "# Meta Kaggle Metadata Inventory",
        "",
        f"Source directory: `{args.meta_dir}`",
        "",
        "| Table | Rows | Columns |",
        "| --- | ---: | --- |",
    ]
    details: list[str] = []

    for csv_file in csv_files:
        table = csv_file.name
        source = f"read_csv_auto({sql_literal(csv_file)}, max_line_size=16000000)"
        row_count = con.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
        schema = con.execute(f"DESCRIBE SELECT * FROM {source} LIMIT 0").fetchall()
        columns = ", ".join(f"`{name}`" for name, *_ in schema)
        lines.append(f"| `{table}` | {row_count:,} | {columns} |")

        details.extend(
            [
                "",
                f"## {table}",
                "",
                f"Rows: {row_count:,}",
                "",
                "| Column | Type |",
                "| --- | --- |",
            ]
        )
        for name, type_name, *_ in schema:
            details.append(f"| `{name}` | `{type_name}` |")

    args.output.write_text("\n".join(lines + details) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
