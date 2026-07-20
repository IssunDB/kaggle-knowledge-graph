"""Load the staged kernel-centered subset into an IssunDB database.

This driver generates an IssunDB CLI script that bulk-imports the staged node and
edge Parquet files, declares uniqueness constraints and full-text indexes,
rebuilds the CSR snapshot, and prints statistics. It then runs the CLI, captures
the log, and validates the load: every node file must import in full, no edge
row may be malformed, and no command may error. The process exits non-zero if
any check fails, so a failed load cannot be mistaken for a successful one.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from issundb_load import load_and_validate

DEFAULT_STAGE_DIR = Path(os.environ.get("STAGE_DIR", "stage"))

# Node file names and the label each file's rows carry. Loaded before edges so
# the edge importer can resolve endpoints by the auto-indexed `Id` property.
NODE_FILES: list[tuple[str, str]] = [
    ("nodes_user.parquet", "User"),
    ("nodes_kernel.parquet", "Kernel"),
    ("nodes_kernel_version.parquet", "KernelVersion"),
    ("nodes_dataset.parquet", "Dataset"),
    ("nodes_dataset_version.parquet", "DatasetVersion"),
    ("nodes_competition.parquet", "Competition"),
    ("nodes_tag.parquet", "Tag"),
    ("nodes_library.parquet", "Library"),
    ("nodes_forum.parquet", "Forum"),
    ("nodes_forum_topic.parquet", "ForumTopic"),
    ("nodes_forum_message.parquet", "ForumMessage"),
]

# Edge file names with their source label, destination label, and type.
EDGE_FILES: list[tuple[str, str, str, str]] = [
    ("edges_user_authored_kernel.parquet", "User", "Kernel", "AUTHORED_KERNEL"),
    ("edges_kernel_has_version.parquet", "Kernel", "KernelVersion", "HAS_VERSION"),
    ("edges_kernel_current_version.parquet", "Kernel", "KernelVersion", "CURRENT_VERSION"),
    ("edges_kernel_first_version.parquet", "Kernel", "KernelVersion", "FIRST_VERSION"),
    ("edges_kernel_version_authored_by_user.parquet", "KernelVersion", "User", "AUTHORED_BY"),
    ("edges_kernel_version_imports_library.parquet", "KernelVersion", "Library", "IMPORTS"),
    (
        "edges_kernel_version_uses_dataset_version.parquet",
        "KernelVersion",
        "DatasetVersion",
        "USES_DATASET_VERSION",
    ),
    ("edges_dataset_has_version.parquet", "Dataset", "DatasetVersion", "HAS_VERSION"),
    ("edges_dataset_current_version.parquet", "Dataset", "DatasetVersion", "CURRENT_VERSION"),
    (
        "edges_kernel_version_uses_competition.parquet",
        "KernelVersion",
        "Competition",
        "USES_COMPETITION",
    ),
    ("edges_kernel_tagged_with_tag.parquet", "Kernel", "Tag", "TAGGED_WITH"),
    ("edges_dataset_tagged_with_tag.parquet", "Dataset", "Tag", "TAGGED_WITH"),
    ("edges_competition_tagged_with_tag.parquet", "Competition", "Tag", "TAGGED_WITH"),
    ("edges_competition_has_forum.parquet", "Competition", "Forum", "HAS_FORUM"),
    ("edges_forum_has_topic.parquet", "Forum", "ForumTopic", "HAS_TOPIC"),
    ("edges_kernel_has_forum_topic.parquet", "Kernel", "ForumTopic", "HAS_FORUM_TOPIC"),
    ("edges_forum_topic_has_message.parquet", "ForumTopic", "ForumMessage", "HAS_MESSAGE"),
    ("edges_user_posted_message.parquet", "User", "ForumMessage", "POSTED_MESSAGE"),
    ("edges_forum_message_replies_to.parquet", "ForumMessage", "ForumMessage", "REPLIES_TO"),
]

# Full-text indexes on short, clean text fields. ForumMessage.Message is
# deliberately omitted: it can exceed the LMDB full-text key-size limit and
# stays searchable through a `CONTAINS` scan instead.
TEXT_INDEXES: list[tuple[str, str]] = [
    ("Competition", "Title"),
    ("ForumTopic", "Title"),
    ("KernelVersion", "Title"),
    ("DatasetVersion", "Title"),
    ("User", "DisplayName"),
]

MISSING_HINT = "run `make kg-stage-all` first"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE_DIR)
    parser.add_argument("--db", type=Path, default=Path("databases/kernel-kg"))
    parser.add_argument("--cli", type=Path, default=Path("bin/issundb-cli"))
    parser.add_argument("--map-size-gb", type=int, default=8)
    parser.add_argument(
        "--script",
        type=Path,
        default=Path("databases/load_kernel_kg.issun"),
        help="Path the generated CLI script is written to.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("databases/load_kernel_kg.log"),
        help="Path the CLI output is captured to.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exit_code = load_and_validate(
        stage_dir=args.stage_dir,
        db=args.db,
        cli=args.cli,
        map_size_gb=args.map_size_gb,
        script_path=args.script,
        log_path=args.log,
        node_files=NODE_FILES,
        edge_files=EDGE_FILES,
        text_indexes=TEXT_INDEXES,
        missing_hint=MISSING_HINT,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
