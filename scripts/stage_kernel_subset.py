"""Stage a kernel-centered Meta Kaggle subset as node and edge CSVs."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb

DEFAULT_META_DIR = Path(
    os.environ.get("META_KAGGLE_DIR", "/media/data/home/downloads/KW/meta-kaggle")
)
DEFAULT_STAGE_DIR = Path(os.environ.get("STAGE_DIR", "stage"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta-dir", type=Path, default=DEFAULT_META_DIR)
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE_DIR)
    parser.add_argument("--kernel-limit", type=int, default=10_000)
    parser.add_argument("--include-message-text", action="store_true")
    return parser.parse_args()


def sql_literal(path: Path | str) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def csv(meta_dir: Path, name: str) -> str:
    return f"read_csv_auto({sql_literal(meta_dir / name)}, max_line_size=16000000)"


def copy_parquet(con: duckdb.DuckDBPyConnection, query: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({query}) TO {sql_literal(output)} (FORMAT PARQUET)")


def create_seed_tables(con: duckdb.DuckDBPyConnection, meta_dir: Path, kernel_limit: int) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_kernels AS
        SELECT *
        FROM {csv(meta_dir, "Kernels.csv")}
        WHERE coalesce(IsProjectLanguageTemplate, false) = false
        ORDER BY coalesce(TotalVotes, 0) DESC, coalesce(TotalViews, 0) DESC, Id
        LIMIT {kernel_limit}
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_kernel_versions AS
        SELECT kv.*
        FROM {csv(meta_dir, "KernelVersions.csv")} kv
        JOIN seed_kernels k ON kv.ScriptId = k.Id
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_dataset_versions AS
        SELECT DISTINCT dv.*
        FROM {csv(meta_dir, "DatasetVersions.csv")} dv
        JOIN {csv(meta_dir, "KernelVersionDatasetSources.csv")} src
          ON src.SourceDatasetVersionId = dv.Id
        JOIN seed_kernel_versions kv ON kv.Id = src.KernelVersionId
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE seed_dataset_ids AS
        SELECT DISTINCT DatasetId AS Id
        FROM seed_dataset_versions
        WHERE DatasetId IS NOT NULL
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_competitions AS
        SELECT DISTINCT c.*
        FROM {csv(meta_dir, "Competitions.csv")} c
        JOIN {csv(meta_dir, "KernelVersionCompetitionSources.csv")} src
          ON src.SourceCompetitionId = c.Id
        JOIN seed_kernel_versions kv ON kv.Id = src.KernelVersionId
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_forum_topics AS
        SELECT DISTINCT ft.*
        FROM {csv(meta_dir, "ForumTopics.csv")} ft
        LEFT JOIN seed_kernels k ON ft.Id = k.ForumTopicId OR ft.KernelId = k.Id
        LEFT JOIN seed_competitions c ON ft.ForumId = c.ForumId
        WHERE k.Id IS NOT NULL OR c.Id IS NOT NULL
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_forum_messages AS
        SELECT DISTINCT fm.*
        FROM {csv(meta_dir, "ForumMessages.csv")} fm
        JOIN seed_forum_topics ft ON fm.ForumTopicId = ft.Id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE seed_user_ids AS
        SELECT DISTINCT UserId AS Id
        FROM (
            SELECT AuthorUserId AS UserId FROM seed_kernels
            UNION ALL
            SELECT AuthorUserId AS UserId FROM seed_kernel_versions
            UNION ALL
            SELECT CreatorUserId AS UserId FROM seed_dataset_versions
            UNION ALL
            SELECT PostUserId AS UserId FROM seed_forum_messages
        )
        WHERE UserId IS NOT NULL
        """
    )


def stage_nodes(
    con: duckdb.DuckDBPyConnection, meta_dir: Path, stage_dir: Path, include_text: bool
) -> None:
    copy_parquet(
        con,
        """
        SELECT Id, AuthorUserId, CurrentKernelVersionId, FirstKernelVersionId, ForumTopicId,
               CreationDate, EvaluationDate, MadePublicDate, Medal, TotalViews, TotalComments, TotalVotes, CurrentUrlSlug
        FROM seed_kernels
        """,
        stage_dir / "nodes_kernel.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id, ScriptId, VersionNumber, replace(Title, '"', chr(39)) AS Title, CreationDate, TotalLines, TotalVotes,
               IsInternetEnabled, RunningTimeInMilliseconds, DockerImage, AuthorUserId
        FROM seed_kernel_versions
        """,
        stage_dir / "nodes_kernel_version.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT u.Id AS Id, replace(UserName, '"', chr(39)) AS UserName, replace(DisplayName, '"', chr(39)) AS DisplayName,
               RegisterDate, PerformanceTier, Country
        FROM {csv(meta_dir, "Users.csv")} u
        JOIN seed_user_ids s ON u.Id = s.Id
        """,
        stage_dir / "nodes_user.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT d.Id AS Id, CreatorUserId, OwnerUserId, OwnerOrganizationId, CurrentDatasetVersionId,
               ForumId, Type, CreationDate, LastActivityDate, TotalViews, TotalDownloads, TotalVotes, TotalKernels, Medal
        FROM {csv(meta_dir, "Datasets.csv")} d
        JOIN seed_dataset_ids s ON d.Id = s.Id
        """,
        stage_dir / "nodes_dataset.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id, DatasetId, CreatorUserId, LicenseName, CreationDate, VersionNumber,
               replace(Title, '"', chr(39)) AS Title, Slug, replace(Subtitle, '"', chr(39)) AS Subtitle,
               TotalCompressedBytes, TotalUncompressedBytes
        FROM seed_dataset_versions
        """,
        stage_dir / "nodes_dataset_version.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id, Slug, replace(Title, '"', chr(39)) AS Title, replace(Subtitle, '"', chr(39)) AS Subtitle,
               HostSegmentTitle, ForumId, EnabledDate, DeadlineDate,
               EvaluationAlgorithmName, EvaluationAlgorithmIsMax, RewardType, RewardQuantity,
               TotalTeams, TotalCompetitors, TotalSubmissions
        FROM seed_competitions
        """,
        stage_dir / "nodes_competition.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT Id, ParentTagId, replace(Name, '"', chr(39)) AS Name, Slug, FullPath,
               replace(Description, '"', chr(39)) AS Description
        FROM {csv(meta_dir, "Tags.csv")}
        """,
        stage_dir / "nodes_tag.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT DISTINCT f.Id AS Id, ParentForumId, replace(Title, '"', chr(39)) AS Title
        FROM {csv(meta_dir, "Forums.csv")} f
        WHERE f.Id IN (
            SELECT ForumId FROM seed_competitions WHERE ForumId IS NOT NULL
            UNION
            SELECT ForumId FROM seed_forum_topics WHERE ForumId IS NOT NULL
        )
        """,
        stage_dir / "nodes_forum.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id, ForumId, KernelId, CreationDate, LastCommentDate, replace(Title, '"', chr(39)) AS Title,
               IsSticky, TotalViews, Score, TotalMessages, TotalReplies
        FROM seed_forum_topics
        """,
        stage_dir / "nodes_forum_topic.parquet",
    )

    if include_text:
        message_query = """
            SELECT Id, ForumTopicId, PostUserId, PostDate, ReplyToForumMessageId,
                   replace(Message, '"', chr(39)) AS Message, replace(RawMarkdown, '"', chr(39)) AS RawMarkdown,
                   Medal, MedalAwardDate
            FROM seed_forum_messages
        """
    else:
        message_query = """
            SELECT Id, ForumTopicId, PostUserId, PostDate, ReplyToForumMessageId,
                   cast(NULL as VARCHAR) AS Message, cast(NULL as VARCHAR) AS RawMarkdown,
                   Medal, MedalAwardDate
            FROM seed_forum_messages
        """
    copy_parquet(con, message_query, stage_dir / "nodes_forum_message.parquet")


def stage_edges(con: duckdb.DuckDBPyConnection, meta_dir: Path, stage_dir: Path) -> None:
    copy_parquet(
        con,
        """
        SELECT AuthorUserId AS from_user_id, Id AS to_kernel_id
        FROM seed_kernels
        WHERE AuthorUserId IS NOT NULL
        """,
        stage_dir / "edges_user_authored_kernel.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT ScriptId AS from_kernel_id, Id AS to_kernel_version_id
        FROM seed_kernel_versions
        WHERE ScriptId IS NOT NULL
        """,
        stage_dir / "edges_kernel_has_version.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_kernel_id, CurrentKernelVersionId AS to_kernel_version_id
        FROM seed_kernels
        WHERE CurrentKernelVersionId IS NOT NULL
        """,
        stage_dir / "edges_kernel_current_version.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_kernel_id, FirstKernelVersionId AS to_kernel_version_id
        FROM seed_kernels
        WHERE FirstKernelVersionId IS NOT NULL
        """,
        stage_dir / "edges_kernel_first_version.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_kernel_version_id, AuthorUserId AS to_user_id
        FROM seed_kernel_versions
        WHERE AuthorUserId IS NOT NULL
        """,
        stage_dir / "edges_kernel_version_authored_by_user.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT src.KernelVersionId AS from_kernel_version_id,
               src.SourceDatasetVersionId AS to_dataset_version_id
        FROM {csv(meta_dir, "KernelVersionDatasetSources.csv")} src
        JOIN seed_kernel_versions kv ON kv.Id = src.KernelVersionId
        JOIN seed_dataset_versions dv ON dv.Id = src.SourceDatasetVersionId
        """,
        stage_dir / "edges_kernel_version_uses_dataset_version.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT DatasetId AS from_dataset_id, Id AS to_dataset_version_id
        FROM seed_dataset_versions
        WHERE DatasetId IS NOT NULL
        """,
        stage_dir / "edges_dataset_has_version.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT d.Id AS from_dataset_id, d.CurrentDatasetVersionId AS to_dataset_version_id
        FROM {csv(meta_dir, "Datasets.csv")} d
        JOIN seed_dataset_ids s ON d.Id = s.Id
        JOIN seed_dataset_versions dv ON dv.Id = d.CurrentDatasetVersionId
        """,
        stage_dir / "edges_dataset_current_version.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT src.KernelVersionId AS from_kernel_version_id,
               src.SourceCompetitionId AS to_competition_id
        FROM {csv(meta_dir, "KernelVersionCompetitionSources.csv")} src
        JOIN seed_kernel_versions kv ON kv.Id = src.KernelVersionId
        JOIN seed_competitions c ON c.Id = src.SourceCompetitionId
        """,
        stage_dir / "edges_kernel_version_uses_competition.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT kt.KernelId AS from_kernel_id, kt.TagId AS to_tag_id
        FROM {csv(meta_dir, "KernelTags.csv")} kt
        JOIN seed_kernels k ON k.Id = kt.KernelId
        """,
        stage_dir / "edges_kernel_tagged_with_tag.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT dt.DatasetId AS from_dataset_id, dt.TagId AS to_tag_id
        FROM {csv(meta_dir, "DatasetTags.csv")} dt
        JOIN seed_dataset_ids d ON d.Id = dt.DatasetId
        """,
        stage_dir / "edges_dataset_tagged_with_tag.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT ct.CompetitionId AS from_competition_id, ct.TagId AS to_tag_id
        FROM {csv(meta_dir, "CompetitionTags.csv")} ct
        JOIN seed_competitions c ON c.Id = ct.CompetitionId
        """,
        stage_dir / "edges_competition_tagged_with_tag.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_competition_id, ForumId AS to_forum_id
        FROM seed_competitions
        WHERE ForumId IS NOT NULL
        """,
        stage_dir / "edges_competition_has_forum.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT ForumId AS from_forum_id, Id AS to_forum_topic_id
        FROM seed_forum_topics
        WHERE ForumId IS NOT NULL
        """,
        stage_dir / "edges_forum_has_topic.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT KernelId AS from_kernel_id, Id AS to_forum_topic_id
        FROM seed_forum_topics
        WHERE KernelId IS NOT NULL
        """,
        stage_dir / "edges_kernel_has_forum_topic.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT ForumTopicId AS from_forum_topic_id, Id AS to_forum_message_id
        FROM seed_forum_messages
        WHERE ForumTopicId IS NOT NULL
        """,
        stage_dir / "edges_forum_topic_has_message.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT PostUserId AS from_user_id, Id AS to_forum_message_id
        FROM seed_forum_messages
        WHERE PostUserId IS NOT NULL
        """,
        stage_dir / "edges_user_posted_message.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_forum_message_id,
               cast(ReplyToForumMessageId AS BIGINT) AS to_forum_message_id
        FROM seed_forum_messages
        WHERE try_cast(ReplyToForumMessageId AS BIGINT) IN (
            SELECT Id FROM seed_forum_messages
        )
        """,
        stage_dir / "edges_forum_message_replies_to.parquet",
    )


def main() -> None:
    args = parse_args()
    args.stage_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    create_seed_tables(con, args.meta_dir, args.kernel_limit)
    stage_nodes(con, args.meta_dir, args.stage_dir, args.include_message_text)
    stage_edges(con, args.meta_dir, args.stage_dir)
    print(f"Wrote staged subset to {args.stage_dir}")


if __name__ == "__main__":
    main()
