"""Import Meta Kaggle staged nodes and edges into IssunDB via the :import-nodes and :import-edges commands."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

# Paths relative to workspace root
STAGE_DIR = Path("issundb/stage")
DB_PATH = Path("issundb/issundb-data")
CLI_PATH = Path("tmp/issundb-cli")
SCRIPT_PATH = Path("issundb/import.issun")
LOG_PATH = Path("issundb/import.log")

# Node files and their labels
node_files = [
    ("nodes_user.csv", "User"),
    ("nodes_kernel.csv", "Kernel"),
    ("nodes_kernel_version.csv", "KernelVersion"),
    ("nodes_dataset.csv", "Dataset"),
    ("nodes_dataset_version.csv", "DatasetVersion"),
    ("nodes_competition.csv", "Competition"),
    ("nodes_tag.csv", "Tag"),
    ("nodes_library.csv", "Library"),
    ("nodes_forum.csv", "Forum"),
    ("nodes_forum_topic.csv", "ForumTopic"),
    ("nodes_forum_message.csv", "ForumMessage"),
]

# Edge files, their labels, and their relationship types
edge_files = [
    (
        "edges_user_authored_kernel.csv",
        "User",
        "Kernel",
        "AUTHORED_KERNEL",
        "from_user_id",
        "to_kernel_id",
    ),
    (
        "edges_kernel_has_version.csv",
        "Kernel",
        "KernelVersion",
        "HAS_VERSION",
        "from_kernel_id",
        "to_kernel_version_id",
    ),
    (
        "edges_kernel_current_version.csv",
        "Kernel",
        "KernelVersion",
        "CURRENT_VERSION",
        "from_kernel_id",
        "to_kernel_version_id",
    ),
    (
        "edges_kernel_first_version.csv",
        "Kernel",
        "KernelVersion",
        "FIRST_VERSION",
        "from_kernel_id",
        "to_kernel_version_id",
    ),
    (
        "edges_kernel_version_authored_by_user.csv",
        "KernelVersion",
        "User",
        "AUTHORED_BY",
        "from_kernel_version_id",
        "to_user_id",
    ),
    (
        "edges_kernel_version_imports_library.csv",
        "KernelVersion",
        "Library",
        "IMPORTS",
        "from_kernel_version_id",
        "to_library_id",
    ),
    (
        "edges_kernel_version_uses_dataset_version.csv",
        "KernelVersion",
        "DatasetVersion",
        "USES_DATASET_VERSION",
        "from_kernel_version_id",
        "to_dataset_version_id",
    ),
    (
        "edges_dataset_has_version.csv",
        "Dataset",
        "DatasetVersion",
        "HAS_VERSION",
        "from_dataset_id",
        "to_dataset_version_id",
    ),
    (
        "edges_dataset_current_version.csv",
        "Dataset",
        "DatasetVersion",
        "CURRENT_VERSION",
        "from_dataset_id",
        "to_dataset_version_id",
    ),
    (
        "edges_kernel_version_uses_competition.csv",
        "KernelVersion",
        "Competition",
        "USES_COMPETITION",
        "from_kernel_version_id",
        "to_competition_id",
    ),
    (
        "edges_kernel_tagged_with_tag.csv",
        "Kernel",
        "Tag",
        "TAGGED_WITH",
        "from_kernel_id",
        "to_tag_id",
    ),
    (
        "edges_dataset_tagged_with_tag.csv",
        "Dataset",
        "Tag",
        "TAGGED_WITH",
        "from_dataset_id",
        "to_tag_id",
    ),
    (
        "edges_competition_tagged_with_tag.csv",
        "Competition",
        "Tag",
        "TAGGED_WITH",
        "from_competition_id",
        "to_tag_id",
    ),
    (
        "edges_competition_has_forum.csv",
        "Competition",
        "Forum",
        "HAS_FORUM",
        "from_competition_id",
        "to_forum_id",
    ),
    (
        "edges_forum_has_topic.csv",
        "Forum",
        "ForumTopic",
        "HAS_TOPIC",
        "from_forum_id",
        "to_forum_topic_id",
    ),
    (
        "edges_kernel_has_forum_topic.csv",
        "Kernel",
        "ForumTopic",
        "HAS_FORUM_TOPIC",
        "from_kernel_id",
        "to_forum_topic_id",
    ),
    (
        "edges_forum_topic_has_message.csv",
        "ForumTopic",
        "ForumMessage",
        "HAS_MESSAGE",
        "from_forum_topic_id",
        "to_forum_message_id",
    ),
    (
        "edges_user_posted_message.csv",
        "User",
        "ForumMessage",
        "POSTED_MESSAGE",
        "from_user_id",
        "to_forum_message_id",
    ),
    (
        "edges_forum_message_replies_to.csv",
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

    print(
        f"Import process finished in {end_time - start_time:.2f} seconds. Logs written to {LOG_PATH.resolve()}"
    )


if __name__ == "__main__":
    main()
