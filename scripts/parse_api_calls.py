"""Parse Python API invocations for staged kernel versions with Tree-sitter.

The parser builds an import alias map for each file and keeps only calls whose
root name resolves to an imported module. A call such as `np.mean(x)` after
`import numpy as np` becomes the qualified name `numpy.mean`, while calls to
local functions and methods on local variables are excluded. Tree-sitter
tolerates broken code blocks, so partial notebooks still yield calls from the
cells that parse.

Outputs, written to the stage directory:
- `nodes_api_call.parquet` with the qualified call name as `Id` and the
  top-level library as `Library`.
- `edges_kernel_version_calls_api_call.parquet` linking kernel versions to the
  API calls they make.
- `edges_api_call_in_library.parquet` linking API calls to staged libraries.

Run `parse_imports.py` first; the library edge endpoints are validated against
`nodes_library.parquet` so no staged edge points to a missing library node.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterator

import polars as pl
import tree_sitter_python
from tree_sitter import Language, Node, Parser

from parse_imports import (
    DEFAULT_CODE_DIR,
    DEFAULT_STAGE_DIR,
    candidate_paths,
    code_text,
    load_kernel_version_ids,
)

PYTHON_SUFFIXES = {".py", ".ipynb"}

_PARSER = Parser(Language(tree_sitter_python.language()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-dir", type=Path, default=DEFAULT_CODE_DIR)
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE_DIR)
    return parser.parse_args()


def _text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", errors="ignore")


def _walk(root: Node) -> Iterator[Node]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.named_children)


def _aliased_import_parts(node: Node) -> tuple[str, str] | None:
    """Return (alias, name) for an `aliased_import` node, or None if malformed."""
    name = node.child_by_field_name("name")
    alias = node.child_by_field_name("alias")
    if name is None or alias is None:
        return None
    return _text(alias), _text(name)


def _collect_import_statement(node: Node, aliases: dict[str, str]) -> None:
    for child in node.named_children:
        if child.type == "dotted_name":
            top = _text(child).split(".", maxsplit=1)[0]
            aliases[top] = top
        elif child.type == "aliased_import":
            parts = _aliased_import_parts(child)
            if parts is not None:
                aliases[parts[0]] = parts[1]


def _collect_import_from_statement(node: Node, aliases: dict[str, str]) -> None:
    module = node.child_by_field_name("module_name")
    if module is None or module.type != "dotted_name":
        return
    module_name = _text(module)
    for child in node.named_children:
        if child.id == module.id:
            continue
        if child.type == "dotted_name":
            aliases[_text(child)] = f"{module_name}.{_text(child)}"
        elif child.type == "aliased_import":
            parts = _aliased_import_parts(child)
            if parts is not None:
                aliases[parts[0]] = f"{module_name}.{parts[1]}"


def _aliases_from_root(root: Node) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in _walk(root):
        if node.type == "import_statement":
            _collect_import_statement(node, aliases)
        elif node.type == "import_from_statement":
            _collect_import_from_statement(node, aliases)
    return aliases


def import_aliases(text: str) -> dict[str, str]:
    """Map each locally bound import name to the qualified name it stands for."""
    tree = _PARSER.parse(text.encode("utf-8"))
    return _aliases_from_root(tree.root_node)


def _call_chain(node: Node | None) -> list[str] | None:
    """Return the dotted name chain of a call target, or None if it is not one."""
    if node is None:
        return None
    if node.type == "identifier":
        return [_text(node)]
    if node.type == "attribute":
        base = _call_chain(node.child_by_field_name("object"))
        attribute = node.child_by_field_name("attribute")
        if base is None or attribute is None:
            return None
        return [*base, _text(attribute)]
    return None


def api_calls(text: str) -> set[str]:
    """Return the qualified names of calls that resolve to an imported module."""
    tree = _PARSER.parse(text.encode("utf-8"))
    root = tree.root_node
    aliases = _aliases_from_root(root)
    calls: set[str] = set()
    for node in _walk(root):
        if node.type != "call":
            continue
        chain = _call_chain(node.child_by_field_name("function"))
        if not chain:
            continue
        head, *rest = chain
        if head not in aliases:
            continue
        calls.add(".".join([aliases[head], *rest]))
    return calls


def library_of(qualified_name: str) -> str:
    """Return the lowercased top-level library of a qualified call name."""
    return qualified_name.split(".", maxsplit=1)[0].lower()


def load_staged_library_ids(stage_dir: Path) -> set[str]:
    path = stage_dir / "nodes_library.parquet"
    if not path.exists():
        raise SystemExit(f"missing {path} (run `parse_imports.py` on this stage directory first)")
    return set(pl.read_parquet(path, columns=["Id"])["Id"].cast(pl.Utf8))


def main() -> None:
    args = parse_args()
    wanted_ids = load_kernel_version_ids(args.stage_dir)
    staged_libraries = load_staged_library_ids(args.stage_dir)
    rows: list[tuple[str, str]] = []

    for kernel_version_id in sorted(wanted_ids, key=int):
        for path in candidate_paths(args.code_dir, kernel_version_id):
            if path.suffix.lower() not in PYTHON_SUFFIXES or not path.exists():
                continue
            try:
                text = code_text(path)
            except OSError:
                continue
            for call in api_calls(text):
                rows.append((kernel_version_id, call))

    calls = pl.DataFrame(
        rows,
        schema={"KernelVersionId": pl.Utf8, "ApiCall": pl.Utf8},
        orient="row",
    )
    calls = calls.unique().sort(["KernelVersionId", "ApiCall"])

    nodes = (
        calls.select(pl.col("ApiCall").alias("Id"))
        .unique()
        .with_columns(pl.col("Id").map_elements(library_of, return_dtype=pl.Utf8).alias("Library"))
        .sort("Id")
    )
    nodes.write_parquet(args.stage_dir / "nodes_api_call.parquet")

    calls.rename(
        {"KernelVersionId": "from_kernel_version_id", "ApiCall": "to_api_call_id"}
    ).write_parquet(args.stage_dir / "edges_kernel_version_calls_api_call.parquet")

    in_library = (
        nodes.filter(pl.col("Library").is_in(sorted(staged_libraries)))
        .select(
            pl.col("Id").alias("from_api_call_id"),
            pl.col("Library").alias("to_library_id"),
        )
        .sort("from_api_call_id")
    )
    in_library.write_parquet(args.stage_dir / "edges_api_call_in_library.parquet")

    print(
        f"Wrote {nodes.height} API call nodes, {calls.height} call edges, "
        f"and {in_library.height} library edges"
    )


if __name__ == "__main__":
    main()
