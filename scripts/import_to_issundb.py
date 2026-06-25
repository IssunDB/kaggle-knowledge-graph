"""Import Meta Kaggle staged nodes and edges into IssunDB.

Use the :import-nodes and :import-edges commands to load the data.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

# Paths relative to workspace root
STAGE_DIR = Path("databases/stage")
DB_PATH = Path("databases/issundb-data")
CLI_PATH = Path("bin/issundb-cli")
SCRIPT_PATH = Path("databases/import.issun")
LOG_PATH = Path("databases/import.log")

# Node files and their labels
node_files = [
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

# Edge files, their labels, and their relationship types
edge_files = [
    (
        "edges_user_authored_kernel.parquet",
        "User",
        "Kernel",
        "AUTHORED_KERNEL",
        "from_user_id",
        "to_kernel_id",
    ),
    (
        "edges_kernel_has_version.parquet",
        "Kernel",
        "KernelVersion",
        "HAS_VERSION",
        "from_kernel_id",
        "to_kernel_version_id",
    ),
    (
        "edges_kernel_current_version.parquet",
        "Kernel",
        "KernelVersion",
        "CURRENT_VERSION",
        "from_kernel_id",
        "to_kernel_version_id",
    ),
    (
        "edges_kernel_first_version.parquet",
        "Kernel",
        "KernelVersion",
        "FIRST_VERSION",
        "from_kernel_id",
        "to_kernel_version_id",
    ),
    (
        "edges_kernel_version_authored_by_user.parquet",
        "KernelVersion",
        "User",
        "AUTHORED_BY",
        "from_kernel_version_id",
        "to_user_id",
    ),
    (
        "edges_kernel_version_imports_library.parquet",
        "KernelVersion",
        "Library",
        "IMPORTS",
        "from_kernel_version_id",
        "to_library_id",
    ),
    (
        "edges_kernel_version_uses_dataset_version.parquet",
        "KernelVersion",
        "DatasetVersion",
        "USES_DATASET_VERSION",
        "from_kernel_version_id",
        "to_dataset_version_id",
    ),
    (
        "edges_dataset_has_version.parquet",
        "Dataset",
        "DatasetVersion",
        "HAS_VERSION",
        "from_dataset_id",
        "to_dataset_version_id",
    ),
    (
        "edges_dataset_current_version.parquet",
        "Dataset",
        "DatasetVersion",
        "CURRENT_VERSION",
        "from_dataset_id",
        "to_dataset_version_id",
    ),
    (
        "edges_kernel_version_uses_competition.parquet",
        "KernelVersion",
        "Competition",
        "USES_COMPETITION",
        "from_kernel_version_id",
        "to_competition_id",
    ),
    (
        "edges_kernel_tagged_with_tag.parquet",
        "Kernel",
        "Tag",
        "TAGGED_WITH",
        "from_kernel_id",
        "to_tag_id",
    ),
    (
        "edges_dataset_tagged_with_tag.parquet",
        "Dataset",
        "Tag",
        "TAGGED_WITH",
        "from_dataset_id",
        "to_tag_id",
    ),
    (
        "edges_competition_tagged_with_tag.parquet",
        "Competition",
        "Tag",
        "TAGGED_WITH",
        "from_competition_id",
        "to_tag_id",
    ),
    (
        "edges_competition_has_forum.parquet",
        "Competition",
        "Forum",
        "HAS_FORUM",
        "from_competition_id",
        "to_forum_id",
    ),
    (
        "edges_forum_has_topic.parquet",
        "Forum",
        "ForumTopic",
        "HAS_TOPIC",
        "from_forum_id",
        "to_forum_topic_id",
    ),
    (
        "edges_kernel_has_forum_topic.parquet",
        "Kernel",
        "ForumTopic",
        "HAS_FORUM_TOPIC",
        "from_kernel_id",
        "to_forum_topic_id",
    ),
    (
        "edges_forum_topic_has_message.parquet",
        "ForumTopic",
        "ForumMessage",
        "HAS_MESSAGE",
        "from_forum_topic_id",
        "to_forum_message_id",
    ),
    (
        "edges_user_posted_message.parquet",
        "User",
        "ForumMessage",
        "POSTED_MESSAGE",
        "from_user_id",
        "to_forum_message_id",
    ),
    (
        "edges_forum_message_replies_to.parquet",
        "ForumMessage",
        "ForumMessage",
        "REPLIES_TO",
        "from_forum_message_id",
        "to_forum_message_id",
    ),
]


def main() -> None:
    commands = []

    # Process nodes: each staged node file is a CSV with a header row and one
    # node per row. The label is passed to `:import-nodes` as an argument, so the
    # files are imported as-is with no rewriting. Every column becomes a node
    # property; IssunDB auto-indexes the `Id` column, which the edge importer
    # relies on to resolve endpoints.
    print("Processing nodes...")
    for filename, label in node_files:
        src_path = STAGE_DIR / filename

        if not src_path.exists():
            print(f"Skipping missing node file: {filename}")
            continue

        print(f"  Importing {filename} ({label})...")
        commands.append(f":import-nodes {src_path.resolve()} {label}")

    # Process edges: each staged edge file is already a 2-column CSV of domain
    # keys (src_id, dst_id), which maps exactly to one `:import-edges` command.
    # IssunDB resolves each key to a node id via the auto-indexed `Id` property
    # and bulk-inserts in batched transactions. There is no Python-side id
    # mapping and no per-edge `add-edge` commands.
    print("Processing edges...")
    for filename, src_label, dst_label, rel_type, _src_col, _dst_col in edge_files:
        src_path = STAGE_DIR / filename
        if not src_path.exists():
            print(f"Skipping missing edge file: {filename}")
            continue
        print(f"  Importing {filename} ({rel_type})...")
        commands.append(f":import-edges {src_path.resolve()} {src_label} {dst_label} {rel_type}")

    commands.append("rebuild-csr")
    commands.append("stats")
    commands.append("quit")

    # Write commands to script file
    SCRIPT_PATH.write_text("\n".join(commands) + "\n", encoding="utf-8")
    print(f"Wrote import script to {SCRIPT_PATH.resolve()}")

    # Execute IssunDB CLI
    print("Executing IssunDB CLI import process...")
    if DB_PATH.exists():
        import shutil

        print(f"Cleaning existing database directory {DB_PATH}...")
        shutil.rmtree(DB_PATH)

    start_time = time.time()
    with SCRIPT_PATH.open("r", encoding="utf-8") as sf, LOG_PATH.open("w", encoding="utf-8") as lf:
        process = subprocess.Popen(
            [str(CLI_PATH), "--map-size-gb", "8", str(DB_PATH)],
            stdin=sf,
            stdout=lf,
            stderr=lf,
        )
        process.wait()
    end_time = time.time()

    elapsed = end_time - start_time
    print(f"Import finished in {elapsed:.2f} seconds.")
    print(f"Logs are written to {LOG_PATH.resolve()}")


if __name__ == "__main__":
    main()
