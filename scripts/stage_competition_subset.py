"""Stage a competition-centered Meta Kaggle subset as node and edge Parquet files.

Scope (post-2020, curated):
- Competitions enabled on or after 2020-01-01, excluding Community/in-class events.
- Ranked or medal-winning teams in those competitions, plus their members and leaders.
- Selected and leaderboard submissions for those teams (the meaningful scores).
- Top kernels per competition by votes, with their competition-sourced versions and authors.
- Fork lineage between staged kernel versions.
- Datasets and dataset versions used by the staged kernel versions.
- Discussion forums, topics, and messages attached to those competitions, including each
  team's write-up topic.
- Tag taxonomy, host and dataset-owner organizations, and the users implicated by any of
  the above.

Library nodes and IMPORTS edges are produced separately by `parse_imports.py`, which
reads `nodes_kernel_version.parquet` from the same stage directory.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb

DEFAULT_META_DIR = Path(
    os.environ.get("META_KAGGLE_DIR", str(Path.home() / "downloads" / "KW" / "meta-kaggle"))
).expanduser()
DEFAULT_STAGE_DIR = Path(os.environ.get("STAGE_DIR", "databases/staging_data")).expanduser()

# Competitions enabled on or after this instant are in scope.
ENABLED_SINCE = "2020-01-01"
# Top kernels per competition by votes form the code layer.
KERNELS_PER_COMPETITION = 50


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta-dir", type=lambda v: Path(v).expanduser(), default=DEFAULT_META_DIR)
    parser.add_argument(
        "--stage-dir", type=lambda v: Path(v).expanduser(), default=DEFAULT_STAGE_DIR
    )
    parser.add_argument("--kernels-per-competition", type=int, default=KERNELS_PER_COMPETITION)
    parser.add_argument("--include-message-text", action="store_true")
    return parser.parse_args()


def sql_literal(path: Path | str) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def csv(meta_dir: Path, name: str) -> str:
    return f"read_csv_auto({sql_literal(meta_dir / name)}, max_line_size=16000000)"


def copy_parquet(con: duckdb.DuckDBPyConnection, query: str, output: Path) -> None:
    """Write `query` to a Parquet file, ordered by its first column.

    Every node query selects `Id` first and every edge query selects its source
    first, so one `ORDER BY 1` sorts both usefully. It is a load-time
    optimization rather than a cosmetic one, and the two halves only pay off
    together: the importer allocates node ids in file order, so sorting the node
    files makes an IssunDB id ascend with the domain `Id`, and sorting the edge
    files by source then makes the `out_adj` writes land in ascending key order
    instead of scattering across the tree. Measured on a synthetic 1 M-node,
    4 M-edge graph, that took the edge phase from 19.5 s to 14.0 s.

    Sorting costs a little here, where DuckDB is doing it over a columnar batch,
    and saves more there, where the alternative is random B-tree page access.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT * FROM ({query}) ORDER BY 1) TO {sql_literal(output)} (FORMAT PARQUET)"
    )


def warn_on_unparseable_enabled_dates(con: duckdb.DuckDBPyConnection, meta_dir: Path) -> None:
    """Warn about `EnabledDate` values the seed filter cannot parse.

    `try_strptime` silently yields NULL for a non-matching format, which the seed
    filter then excludes the same way it excludes a competition that predates the
    cutoff. Surface the difference instead of conflating the two.
    """
    unparseable_row = con.execute(
        f"""
        SELECT count(*)
        FROM {csv(meta_dir, "Competitions.csv")}
        WHERE EnabledDate IS NOT NULL
          AND try_strptime(EnabledDate, '%m/%d/%Y %H:%M:%S') IS NULL
        """
    ).fetchone()
    assert unparseable_row is not None
    unparseable = unparseable_row[0]
    if unparseable:
        print(
            f"warning: {unparseable} competition row(s) have an EnabledDate that does not "
            "match '%m/%d/%Y %H:%M:%S' and were excluded from the post-2020 scope",
            file=sys.stderr,
        )


def create_seed_tables(
    con: duckdb.DuckDBPyConnection, meta_dir: Path, kernels_per_competition: int
) -> None:
    warn_on_unparseable_enabled_dates(con, meta_dir)
    # Seed competitions: enabled on or after the cutoff, excluding Community events.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_competitions AS
        SELECT *
        FROM {csv(meta_dir, "Competitions.csv")}
        WHERE try_strptime(EnabledDate, '%m/%d/%Y %H:%M:%S') >= TIMESTAMP '{ENABLED_SINCE}'
          AND coalesce(HostSegmentTitle, '') <> 'Community'
        """
    )
    # Seed organizations are created after the dataset layer, because they
    # include both competition hosts and dataset owners.
    # Seed teams: ranked or medal-winning teams in the seed competitions.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_teams AS
        SELECT t.*
        FROM {csv(meta_dir, "Teams.csv")} t
        JOIN seed_competitions c ON t.CompetitionId = c.Id
        WHERE t.PrivateLeaderboardRank IS NOT NULL
           OR t.PublicLeaderboardRank IS NOT NULL
           OR t.Medal IS NOT NULL
           OR t.PublicLeaderboardSubmissionId IS NOT NULL
           OR t.PrivateLeaderboardSubmissionId IS NOT NULL
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_team_memberships AS
        SELECT tm.*
        FROM {csv(meta_dir, "TeamMemberships.csv")} tm
        JOIN seed_teams t ON tm.TeamId = t.Id
        """
    )
    # Seed submissions: selected submissions plus each team's leaderboard submissions.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_submissions AS
        SELECT s.*
        FROM {csv(meta_dir, "Submissions.csv")} s
        JOIN seed_teams t ON s.TeamId = t.Id
        WHERE s.IsSelected = true
           OR s.Id = t.PublicLeaderboardSubmissionId
           OR s.Id = t.PrivateLeaderboardSubmissionId
        """
    )
    # Seed kernels: top N kernels per competition by votes.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_kernels AS
        WITH kernel_competition AS (
            SELECT DISTINCT src.SourceCompetitionId AS competition_id, kv.ScriptId AS kernel_id
            FROM {csv(meta_dir, "KernelVersionCompetitionSources.csv")} src
            JOIN seed_competitions c ON c.Id = src.SourceCompetitionId
            JOIN {csv(meta_dir, "KernelVersions.csv")} kv ON kv.Id = src.KernelVersionId
        ),
        ranked AS (
            SELECT kc.competition_id, kc.kernel_id, coalesce(k.TotalVotes, 0) AS votes,
                   row_number() OVER (
                       PARTITION BY kc.competition_id
                       ORDER BY coalesce(k.TotalVotes, 0) DESC, kc.kernel_id
                   ) AS rn
            FROM kernel_competition kc
            JOIN {csv(meta_dir, "Kernels.csv")} k ON k.Id = kc.kernel_id
        )
        SELECT DISTINCT k.*
        FROM {csv(meta_dir, "Kernels.csv")} k
        JOIN (SELECT DISTINCT kernel_id FROM ranked WHERE rn <= {kernels_per_competition}) sel
          ON sel.kernel_id = k.Id
        """
    )
    # Seed kernel versions: competition-sourced versions of the seed kernels.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_kernel_versions AS
        SELECT DISTINCT kv.*
        FROM {csv(meta_dir, "KernelVersions.csv")} kv
        JOIN {csv(meta_dir, "KernelVersionCompetitionSources.csv")} src
          ON src.KernelVersionId = kv.Id
        JOIN seed_competitions c ON c.Id = src.SourceCompetitionId
        JOIN seed_kernels k ON k.Id = kv.ScriptId
        """
    )
    # Seed datasets: dataset versions used by the seed kernel versions.
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
    # Seed organizations: competition hosts and dataset-owner organizations.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_organization_ids AS
        SELECT DISTINCT OrganizationId AS Id
        FROM (
            SELECT OrganizationId FROM seed_competitions
            UNION ALL
            SELECT d.OwnerOrganizationId AS OrganizationId
            FROM {csv(meta_dir, "Datasets.csv")} d
            JOIN seed_dataset_ids s ON d.Id = s.Id
        )
        WHERE OrganizationId IN (SELECT Id FROM {csv(meta_dir, "Organizations.csv")})
        """
    )
    # Seed discussion: forum topics and messages attached to the seed competitions.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_forum_topics AS
        SELECT DISTINCT ft.*
        FROM {csv(meta_dir, "ForumTopics.csv")} ft
        JOIN seed_competitions c ON ft.ForumId = c.ForumId
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
    # Seed users: users associated with the teams, submissions, kernels, or discussion.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE seed_user_ids AS
        SELECT DISTINCT UserId AS Id
        FROM (
            SELECT UserId FROM seed_team_memberships
            UNION ALL
            SELECT TeamLeaderId AS UserId FROM seed_teams
            UNION ALL
            SELECT SubmittedUserId AS UserId FROM seed_submissions
            UNION ALL
            SELECT AuthorUserId AS UserId FROM seed_kernels
            UNION ALL
            SELECT AuthorUserId AS UserId FROM seed_kernel_versions
            UNION ALL
            SELECT CreatorUserId AS UserId FROM seed_dataset_versions
            UNION ALL
            SELECT PostUserId AS UserId FROM seed_forum_messages
        )
        WHERE UserId IN (SELECT Id FROM {csv(meta_dir, "Users.csv")})
        """
    )


def stage_nodes(
    con: duckdb.DuckDBPyConnection, meta_dir: Path, stage_dir: Path, include_text: bool
) -> None:
    copy_parquet(
        con,
        """
        SELECT Id, Slug, Title, Subtitle, HostSegmentTitle, HostName, ForumId, OrganizationId,
               EnabledDate, DeadlineDate, EvaluationAlgorithmName, EvaluationAlgorithmDescription,
               EvaluationAlgorithmIsMax, RewardType, RewardQuantity, MaxTeamSize,
               TotalTeams, TotalCompetitors, TotalSubmissions, Overview, Rules, DatasetDescription
        FROM seed_competitions
        """,
        stage_dir / "nodes_competition.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id, CompetitionId, TeamName, Medal,
               PublicLeaderboardRank, PrivateLeaderboardRank, ScoreFirstSubmittedDate,
               LastSubmissionDate, IsBenchmark
        FROM seed_teams
        """,
        stage_dir / "nodes_team.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT u.Id AS Id, UserName, DisplayName, RegisterDate, PerformanceTier, Country
        FROM {csv(meta_dir, "Users.csv")} u
        JOIN seed_user_ids s ON u.Id = s.Id
        """,
        stage_dir / "nodes_user.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id, TeamId, SubmittedUserId, SourceKernelVersionId, SubmissionDate, ScoreDate,
               IsAfterDeadline, IsSelected, PublicScoreFullPrecision, PrivateScoreFullPrecision
        FROM seed_submissions
        """,
        stage_dir / "nodes_submission.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id, AuthorUserId, CurrentKernelVersionId, FirstKernelVersionId, ForumTopicId,
               CreationDate, Medal, TotalViews, TotalComments, TotalVotes, CurrentUrlSlug
        FROM seed_kernels
        """,
        stage_dir / "nodes_kernel.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT kv.Id, kv.ScriptId, kv.VersionNumber, kv.Title, kv.CreationDate, kv.TotalLines,
               kv.TotalVotes, kv.IsInternetEnabled, kv.RunningTimeInMilliseconds, kv.DockerImage,
               kv.AuthorUserId, kl.DisplayName AS ScriptLanguage, kat.Label AS AcceleratorType
        FROM seed_kernel_versions kv
        LEFT JOIN {csv(meta_dir, "KernelLanguages.csv")} kl ON kl.Id = kv.ScriptLanguageId
        LEFT JOIN {csv(meta_dir, "KernelAcceleratorTypes.csv")} kat ON kat.Id = kv.AcceleratorTypeId
        """,
        stage_dir / "nodes_kernel_version.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT d.Id AS Id, CreatorUserId, OwnerUserId, OwnerOrganizationId, CurrentDatasetVersionId,
               ForumId, Type, CreationDate, LastActivityDate, TotalViews, TotalDownloads,
               TotalVotes, TotalKernels, Medal
        FROM {csv(meta_dir, "Datasets.csv")} d
        JOIN seed_dataset_ids s ON d.Id = s.Id
        """,
        stage_dir / "nodes_dataset.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id, DatasetId, CreatorUserId, LicenseName, CreationDate, VersionNumber,
               Title, Slug, Subtitle, Description, VersionNotes,
               TotalCompressedBytes, TotalUncompressedBytes
        FROM seed_dataset_versions
        """,
        stage_dir / "nodes_dataset_version.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT Id, ParentTagId, Name, Slug, FullPath, Description
        FROM {csv(meta_dir, "Tags.csv")}
        """,
        stage_dir / "nodes_tag.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT o.Id AS Id, Name, Slug, CreationDate, Description
        FROM {csv(meta_dir, "Organizations.csv")} o
        JOIN seed_organization_ids s ON o.Id = s.Id
        """,
        stage_dir / "nodes_organization.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT DISTINCT f.Id AS Id, ParentForumId, Title
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
        SELECT Id, ForumId, KernelId, CreationDate, LastCommentDate, Title,
               IsSticky, TotalViews, Score, TotalMessages, TotalReplies
        FROM seed_forum_topics
        """,
        stage_dir / "nodes_forum_topic.parquet",
    )
    if include_text:
        message_query = """
            SELECT Id, ForumTopicId, PostUserId, PostDate, ReplyToForumMessageId,
                   Message, RawMarkdown, Medal, MedalAwardDate
            FROM seed_forum_messages
        """
    else:
        message_query = """
            SELECT Id, ForumTopicId, PostUserId, PostDate, ReplyToForumMessageId,
                   cast(NULL AS VARCHAR) AS Message, cast(NULL AS VARCHAR) AS RawMarkdown,
                   Medal, MedalAwardDate
            FROM seed_forum_messages
        """
    copy_parquet(con, message_query, stage_dir / "nodes_forum_message.parquet")


def stage_edges(con: duckdb.DuckDBPyConnection, meta_dir: Path, stage_dir: Path) -> None:
    # Participation and scores.
    copy_parquet(
        con,
        """
        SELECT Id AS from_team_id, CompetitionId AS to_competition_id
        FROM seed_teams
        WHERE CompetitionId IS NOT NULL
        """,
        stage_dir / "edges_team_competed_in_competition.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT UserId AS from_user_id, TeamId AS to_team_id
        FROM seed_team_memberships
        WHERE UserId IN (SELECT Id FROM seed_user_ids)
        """,
        stage_dir / "edges_user_member_of_team.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT TeamLeaderId AS from_user_id, Id AS to_team_id
        FROM seed_teams
        WHERE TeamLeaderId IN (SELECT Id FROM seed_user_ids)
        """,
        stage_dir / "edges_user_led_team.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_team_id, WriteUpForumTopicId AS to_forum_topic_id
        FROM seed_teams
        WHERE WriteUpForumTopicId IS NOT NULL
        """,
        stage_dir / "edges_team_has_writeup_topic.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_submission_id, TeamId AS to_team_id
        FROM seed_submissions
        WHERE TeamId IS NOT NULL
        """,
        stage_dir / "edges_submission_for_team.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT SubmittedUserId AS from_user_id, Id AS to_submission_id
        FROM seed_submissions
        WHERE SubmittedUserId IN (SELECT Id FROM seed_user_ids)
        """,
        stage_dir / "edges_user_submitted.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT s.Id AS from_submission_id,
               cast(s.SourceKernelVersionId AS BIGINT) AS to_kernel_version_id
        FROM seed_submissions s
        WHERE try_cast(s.SourceKernelVersionId AS BIGINT) IN (SELECT Id FROM seed_kernel_versions)
        """,
        stage_dir / "edges_submission_from_kernel_version.parquet",
    )
    # Team leaderboard submission edges (Team -> Submission), only where the submission is staged.
    copy_parquet(
        con,
        """
        SELECT t.Id AS from_team_id, t.PublicLeaderboardSubmissionId AS to_submission_id
        FROM seed_teams t
        WHERE t.PublicLeaderboardSubmissionId IN (SELECT Id FROM seed_submissions)
        """,
        stage_dir / "edges_team_public_leaderboard_submission.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT t.Id AS from_team_id, t.PrivateLeaderboardSubmissionId AS to_submission_id
        FROM seed_teams t
        WHERE t.PrivateLeaderboardSubmissionId IN (SELECT Id FROM seed_submissions)
        """,
        stage_dir / "edges_team_private_leaderboard_submission.parquet",
    )
    # Code layer.
    copy_parquet(
        con,
        """
        SELECT AuthorUserId AS from_user_id, Id AS to_kernel_id
        FROM seed_kernels
        WHERE AuthorUserId IN (SELECT Id FROM seed_user_ids)
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
        WHERE CurrentKernelVersionId IN (SELECT Id FROM seed_kernel_versions)
        """,
        stage_dir / "edges_kernel_current_version.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_kernel_version_id, AuthorUserId AS to_user_id
        FROM seed_kernel_versions
        WHERE AuthorUserId IN (SELECT Id FROM seed_user_ids)
        """,
        stage_dir / "edges_kernel_version_authored_by_user.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT src.KernelVersionId AS from_kernel_version_id,
               src.SourceKernelVersionId AS to_kernel_version_id
        FROM {csv(meta_dir, "KernelVersionKernelSources.csv")} src
        JOIN seed_kernel_versions kv ON kv.Id = src.KernelVersionId
        JOIN seed_kernel_versions kv2 ON kv2.Id = src.SourceKernelVersionId
        """,
        stage_dir / "edges_kernel_version_forked_from.parquet",
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
    # Dataset layer.
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
        SELECT d.Id AS from_dataset_id, d.OwnerOrganizationId AS to_organization_id
        FROM {csv(meta_dir, "Datasets.csv")} d
        JOIN seed_dataset_ids s ON d.Id = s.Id
        WHERE d.OwnerOrganizationId IN (SELECT Id FROM seed_organization_ids)
        """,
        stage_dir / "edges_dataset_owned_by_organization.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_competition_id, OrganizationId AS to_organization_id
        FROM seed_competitions
        WHERE OrganizationId IN (SELECT Id FROM seed_organization_ids)
        """,
        stage_dir / "edges_competition_has_organization.parquet",
    )
    copy_parquet(
        con,
        f"""
        SELECT uo.UserId AS from_user_id, uo.OrganizationId AS to_organization_id
        FROM {csv(meta_dir, "UserOrganizations.csv")} uo
        JOIN seed_user_ids u ON u.Id = uo.UserId
        JOIN seed_organization_ids o ON o.Id = uo.OrganizationId
        """,
        stage_dir / "edges_user_member_of_organization.parquet",
    )
    # Tags.
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
    # Discussion.
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
        WHERE PostUserId IN (SELECT Id FROM seed_user_ids)
        """,
        stage_dir / "edges_user_posted_message.parquet",
    )
    copy_parquet(
        con,
        """
        SELECT Id AS from_forum_message_id,
               cast(ReplyToForumMessageId AS BIGINT) AS to_forum_message_id
        FROM seed_forum_messages
        WHERE try_cast(ReplyToForumMessageId AS BIGINT) IN (SELECT Id FROM seed_forum_messages)
        """,
        stage_dir / "edges_forum_message_replies_to.parquet",
    )


def main() -> None:
    args = parse_args()
    args.stage_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    create_seed_tables(con, args.meta_dir, args.kernels_per_competition)
    stage_nodes(con, args.meta_dir, args.stage_dir, args.include_message_text)
    stage_edges(con, args.meta_dir, args.stage_dir)
    print(f"Wrote staged competition subset to {args.stage_dir}")


if __name__ == "__main__":
    main()
