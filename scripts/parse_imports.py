"""Parse Python/R package imports for staged kernel versions."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import polars as pl

DEFAULT_CODE_DIR = Path(
    os.environ.get(
        "META_KAGGLE_CODE_DIR", str(Path.home() / "Downloads" / "KW" / "meta-kaggle-code")
    )
)
DEFAULT_STAGE_DIR = Path(os.environ.get("STAGE_DIR", "stage"))

PY_IMPORT_RE = re.compile(r"^\s*import\s+(.+)$", re.MULTILINE)
PY_FROM_RE = re.compile(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\s+", re.MULTILINE)
R_IMPORT_RE = re.compile(r"\b(?:library|require)\s*\(\s*['\"]?([A-Za-z][\w.]*)['\"]?\s*\)")
PY_IMPORT_NAME_RE = re.compile(r"^([A-Za-z_][\w.]*)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-dir", type=Path, default=DEFAULT_CODE_DIR)
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE_DIR)
    return parser.parse_args()


def load_kernel_version_ids(stage_dir: Path) -> set[str]:
    path = stage_dir / "nodes_kernel_version.parquet"
    df = pl.read_parquet(path, columns=["Id"])
    return set(df["Id"].cast(pl.Utf8))


def candidate_paths(code_dir: Path, kernel_version_id: str) -> list[Path]:
    padded = kernel_version_id.zfill(10)
    shard = code_dir / padded[:4] / padded[4:7]
    return [
        shard / f"{kernel_version_id}.ipynb",
        shard / f"{kernel_version_id}.py",
        shard / f"{kernel_version_id}.r",
        shard / f"{kernel_version_id}.rmd",
    ]


def notebook_code_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        payload: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    chunks: list[str] = []
    for cell in payload.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            chunks.append("".join(str(part) for part in source))
        else:
            chunks.append(str(source))
    return "\n".join(chunks)


def code_text(path: Path) -> str:
    if path.suffix.lower() == ".ipynb":
        return notebook_code_text(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def _add_top_level(libs: set[str], name: str) -> None:
    top_level = name.split(".", maxsplit=1)[0].strip()
    if top_level and top_level != "__future__":
        libs.add(top_level.lower())


def _import_clause_names(clause: str) -> list[str]:
    """Split a comma-separated `import a, b as c` clause into module names."""
    names: list[str] = []
    for part in clause.split("#", maxsplit=1)[0].split(","):
        match = PY_IMPORT_NAME_RE.match(part.strip())
        if match:
            names.append(match.group(1))
    return names


def imported_libraries(text: str) -> set[str]:
    libs: set[str] = set()
    for clause in PY_IMPORT_RE.findall(text):
        for name in _import_clause_names(clause):
            _add_top_level(libs, name)
    for regex in (PY_FROM_RE, R_IMPORT_RE):
        for match in regex.findall(text):
            _add_top_level(libs, match)
    return libs


def main() -> None:
    args = parse_args()
    wanted_ids = load_kernel_version_ids(args.stage_dir)
    rows: list[tuple[str, str]] = []

    for kernel_version_id in sorted(wanted_ids, key=int):
        for path in candidate_paths(args.code_dir, kernel_version_id):
            if not path.exists():
                continue
            try:
                text = code_text(path)
            except OSError:
                continue
            for library in imported_libraries(text):
                rows.append((kernel_version_id, library))

    imports = pl.DataFrame(
        rows, schema={"KernelVersionId": pl.Utf8, "Library": pl.Utf8}, orient="row"
    )
    imports = imports.unique().sort(["KernelVersionId", "Library"])

    libraries = imports.select(pl.col("Library").alias("Id")).unique().sort("Id")
    libraries.write_parquet(args.stage_dir / "nodes_library.parquet")
    imports.rename(
        {"KernelVersionId": "from_kernel_version_id", "Library": "to_library_id"}
    ).write_parquet(args.stage_dir / "edges_kernel_version_imports_library.parquet")
    print(f"Wrote {imports.height} import edges and {libraries.height} libraries")


if __name__ == "__main__":
    main()
