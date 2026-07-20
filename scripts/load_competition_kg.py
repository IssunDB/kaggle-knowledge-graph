"""Load the staged competition subset into an IssunDB database.

This driver generates an IssunDB CLI script that bulk-imports the staged node and
edge CSVs, declares uniqueness constraints and full-text indexes, rebuilds the CSR
snapshot, and prints statistics. It then runs the CLI, captures the log, and
validates the load: every node file must import in full, no edge row may be
malformed, and no command may error (a failed uniqueness constraint means the
source had duplicate ids). The process exits non-zero if any check fails, so
`make graph-kc` fails loudly rather than leaving a half-built graph.

Full-text indexes are declared only on short, clean text fields. `ForumMessage`
bodies and the long-form `Competition` text (`Overview`, `Rules`,
`DatasetDescription`) are deliberately left out: their raw HTML carries unbroken
tokens (long URLs and base64) that exceed the LMDB full-text key-size limit.
Both stay searchable through a `CONTAINS` scan.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from issundb_load import load_and_validate

# Node CSV file names and the label each file's rows carry. Loaded before edges
# so the edge importer can resolve endpoints by the auto-indexed `Id` property.
NODE_FILES: list[tuple[str, str]] = [
    ("nodes_competition.parquet", "Competition"),
    ("nodes_team.parquet", "Team"),
    ("nodes_user.parquet", "User"),
    ("nodes_submission.parquet", "Submission"),
    ("nodes_kernel.parquet", "Kernel"),
    ("nodes_kernel_version.parquet", "KernelVersion"),
    ("nodes_dataset.parquet", "Dataset"),
    ("nodes_dataset_version.parquet", "DatasetVersion"),
    ("nodes_tag.parquet", "Tag"),
    ("nodes_forum.parquet", "Forum"),
    ("nodes_forum_topic.parquet", "ForumTopic"),
    ("nodes_forum_message.parquet", "ForumMessage"),
    ("nodes_library.parquet", "Library"),
    ("nodes_api_call.parquet", "ApiCall"),
    ("nodes_organization.parquet", "Organization"),
]

# Edge CSV file names with their source label, destination label, and type.
EDGE_FILES: list[tuple[str, str, str, str]] = [
    ("edges_team_competed_in_competition.parquet", "Team", "Competition", "COMPETED_IN"),
    ("edges_user_member_of_team.parquet", "User", "Team", "MEMBER_OF_TEAM"),
    ("edges_user_led_team.parquet", "User", "Team", "LED_TEAM"),
    ("edges_submission_for_team.parquet", "Submission", "Team", "FOR_TEAM"),
    ("edges_user_submitted.parquet", "User", "Submission", "SUBMITTED"),
    (
        "edges_submission_from_kernel_version.parquet",
        "Submission",
        "KernelVersion",
        "FROM_KERNEL_VERSION",
    ),
    (
        "edges_team_public_leaderboard_submission.parquet",
        "Team",
        "Submission",
        "PUBLIC_LEADERBOARD_SUBMISSION",
    ),
    (
        "edges_team_private_leaderboard_submission.parquet",
        "Team",
        "Submission",
        "PRIVATE_LEADERBOARD_SUBMISSION",
    ),
    ("edges_user_authored_kernel.parquet", "User", "Kernel", "AUTHORED_KERNEL"),
    ("edges_kernel_has_version.parquet", "Kernel", "KernelVersion", "HAS_VERSION"),
    ("edges_kernel_current_version.parquet", "Kernel", "KernelVersion", "CURRENT_VERSION"),
    ("edges_kernel_version_authored_by_user.parquet", "KernelVersion", "User", "AUTHORED_BY"),
    (
        "edges_kernel_version_forked_from.parquet",
        "KernelVersion",
        "KernelVersion",
        "FORKED_FROM",
    ),
    (
        "edges_kernel_version_uses_competition.parquet",
        "KernelVersion",
        "Competition",
        "USES_COMPETITION",
    ),
    ("edges_kernel_version_imports_library.parquet", "KernelVersion", "Library", "IMPORTS"),
    ("edges_kernel_version_calls_api_call.parquet", "KernelVersion", "ApiCall", "CALLS"),
    ("edges_api_call_in_library.parquet", "ApiCall", "Library", "IN_LIBRARY"),
    (
        "edges_kernel_version_uses_dataset_version.parquet",
        "KernelVersion",
        "DatasetVersion",
        "USES_DATASET_VERSION",
    ),
    ("edges_dataset_has_version.parquet", "Dataset", "DatasetVersion", "HAS_VERSION"),
    ("edges_dataset_current_version.parquet", "Dataset", "DatasetVersion", "CURRENT_VERSION"),
    (
        "edges_dataset_owned_by_organization.parquet",
        "Dataset",
        "Organization",
        "OWNED_BY_ORGANIZATION",
    ),
    ("edges_kernel_tagged_with_tag.parquet", "Kernel", "Tag", "TAGGED_WITH"),
    ("edges_dataset_tagged_with_tag.parquet", "Dataset", "Tag", "TAGGED_WITH"),
    ("edges_competition_tagged_with_tag.parquet", "Competition", "Tag", "TAGGED_WITH"),
    ("edges_competition_has_forum.parquet", "Competition", "Forum", "HAS_FORUM"),
    (
        "edges_competition_has_organization.parquet",
        "Competition",
        "Organization",
        "HAS_ORGANIZATION",
    ),
    (
        "edges_user_member_of_organization.parquet",
        "User",
        "Organization",
        "MEMBER_OF_ORGANIZATION",
    ),
    ("edges_forum_has_topic.parquet", "Forum", "ForumTopic", "HAS_TOPIC"),
    ("edges_team_has_writeup_topic.parquet", "Team", "ForumTopic", "HAS_WRITEUP"),
    ("edges_forum_topic_has_message.parquet", "ForumTopic", "ForumMessage", "HAS_MESSAGE"),
    ("edges_user_posted_message.parquet", "User", "ForumMessage", "POSTED_MESSAGE"),
    ("edges_forum_message_replies_to.parquet", "ForumMessage", "ForumMessage", "REPLIES_TO"),
]

# Full-text indexes on short, clean text fields. ForumMessage.Message and the
# long-form Competition text (Overview, Rules, DatasetDescription) are omitted
# on purpose (see the module docstring); they stay searchable via CONTAINS.
TEXT_INDEXES: list[tuple[str, str]] = [
    ("Competition", "Title"),
    ("ForumTopic", "Title"),
    ("KernelVersion", "Title"),
    ("DatasetVersion", "Title"),
    ("User", "DisplayName"),
    ("Organization", "Name"),
]

MISSING_HINT = "run `make comp-stage comp-parse-imports comp-parse-api-calls` first"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, default=Path("databases/staging_data"))
    parser.add_argument("--db", type=Path, default=Path("databases/comp-kg"))
    parser.add_argument("--cli", type=Path, default=Path("bin/issundb-cli"))
    parser.add_argument("--map-size-gb", type=int, default=8)
    parser.add_argument(
        "--script",
        type=Path,
        default=Path("databases/load_competition_kg.issun"),
        help="Path the generated CLI script is written to.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("databases/load_competition_kg.log"),
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
