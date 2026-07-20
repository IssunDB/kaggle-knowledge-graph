"""Tests for scripts/stage_kernel_subset.py.

Builds a tiny synthetic Meta Kaggle CSV tree covering kernels, kernel versions,
datasets, competitions, forums, and tags, then exercises the full
create_seed_tables -> stage_nodes -> stage_edges pipeline against it with an
in-memory DuckDB connection.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl
import pytest
from csv_fixtures import write_csv

import stage_kernel_subset as sks


@pytest.fixture
def meta_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "meta"
    directory.mkdir()

    write_csv(
        directory,
        "Kernels.csv",
        [
            {
                "Id": 1,
                "IsProjectLanguageTemplate": False,
                "TotalVotes": 10,
                "TotalViews": 100,
                "AuthorUserId": 100,
                "CurrentKernelVersionId": 11,
                "FirstKernelVersionId": 11,
                "ForumTopicId": "",
                "CreationDate": "2021-01-01",
                "EvaluationDate": "",
                "MadePublicDate": "",
                "Medal": "",
                "TotalComments": 2,
                "CurrentUrlSlug": "house-prices",
            },
            {
                "Id": 2,
                "IsProjectLanguageTemplate": False,
                "TotalVotes": 5,
                "TotalViews": 50,
                "AuthorUserId": 101,
                "CurrentKernelVersionId": 21,
                "FirstKernelVersionId": 21,
                "ForumTopicId": "",
                "CreationDate": "2021-01-02",
                "EvaluationDate": "",
                "MadePublicDate": "",
                "Medal": "",
                "TotalComments": 0,
                "CurrentUrlSlug": "simple-eda",
            },
            {
                "Id": 3,
                "IsProjectLanguageTemplate": True,
                "TotalVotes": 999,
                "TotalViews": 999,
                "AuthorUserId": 102,
                "CurrentKernelVersionId": "",
                "FirstKernelVersionId": "",
                "ForumTopicId": "",
                "CreationDate": "2021-01-03",
                "EvaluationDate": "",
                "MadePublicDate": "",
                "Medal": "",
                "TotalComments": 0,
                "CurrentUrlSlug": "template",
            },
            {
                "Id": 4,
                "IsProjectLanguageTemplate": False,
                "TotalVotes": 1,
                "TotalViews": 10,
                "AuthorUserId": 100,
                "CurrentKernelVersionId": 41,
                "FirstKernelVersionId": 41,
                "ForumTopicId": "",
                "CreationDate": "2021-01-04",
                "EvaluationDate": "",
                "MadePublicDate": "",
                "Medal": "",
                "TotalComments": 0,
                "CurrentUrlSlug": "low-vote",
            },
        ],
    )
    write_csv(
        directory,
        "KernelVersions.csv",
        [
            {
                "Id": 11,
                "ScriptId": 1,
                "VersionNumber": 1,
                "Title": 'Predicting "House Prices"',
                "CreationDate": "2021-01-01",
                "TotalLines": 50,
                "TotalVotes": 10,
                "IsInternetEnabled": False,
                "RunningTimeInMilliseconds": 1000,
                "DockerImage": "img1",
                "AuthorUserId": 100,
            },
            {
                "Id": 21,
                "ScriptId": 2,
                "VersionNumber": 1,
                "Title": "Simple EDA",
                "CreationDate": "2021-01-02",
                "TotalLines": 20,
                "TotalVotes": 5,
                "IsInternetEnabled": False,
                "RunningTimeInMilliseconds": 500,
                "DockerImage": "img1",
                "AuthorUserId": 101,
            },
            {
                "Id": 41,
                "ScriptId": 4,
                "VersionNumber": 1,
                "Title": "Excluded by kernel limit",
                "CreationDate": "2021-01-04",
                "TotalLines": 5,
                "TotalVotes": 1,
                "IsInternetEnabled": False,
                "RunningTimeInMilliseconds": 100,
                "DockerImage": "img1",
                "AuthorUserId": 100,
            },
        ],
    )
    write_csv(
        directory,
        "Users.csv",
        [
            {
                "Id": 100,
                "UserName": "alice",
                "DisplayName": "Alice A",
                "RegisterDate": "2020-01-01",
                "PerformanceTier": 2,
                "Country": "US",
            },
            {
                "Id": 101,
                "UserName": "bob",
                "DisplayName": "Bob B",
                "RegisterDate": "2020-01-02",
                "PerformanceTier": 1,
                "Country": "CA",
            },
            {
                "Id": 999,
                "UserName": "unrelated",
                "DisplayName": "Unrelated User",
                "RegisterDate": "2020-01-03",
                "PerformanceTier": 0,
                "Country": "",
            },
        ],
    )
    write_csv(
        directory,
        "Datasets.csv",
        [
            {
                "Id": 50,
                "CreatorUserId": 100,
                "OwnerUserId": 100,
                "OwnerOrganizationId": "",
                "CurrentDatasetVersionId": 501,
                "ForumId": "",
                "Type": 1,
                "CreationDate": "2020-06-01",
                "LastActivityDate": "2021-01-01",
                "TotalViews": 10,
                "TotalDownloads": 5,
                "TotalVotes": 3,
                "TotalKernels": 1,
                "Medal": "",
            }
        ],
    )
    write_csv(
        directory,
        "DatasetVersions.csv",
        [
            {
                "Id": 501,
                "DatasetId": 50,
                "CreatorUserId": 100,
                "LicenseName": "CC0",
                "CreationDate": "2020-06-01",
                "VersionNumber": 1,
                "Title": "Housing Data",
                "Slug": "housing-data",
                "Subtitle": "",
                "TotalCompressedBytes": 1000,
                "TotalUncompressedBytes": 2000,
            },
            {
                "Id": 502,
                "DatasetId": 51,
                "CreatorUserId": 100,
                "LicenseName": "CC0",
                "CreationDate": "2020-06-02",
                "VersionNumber": 1,
                "Title": "Unreferenced Data",
                "Slug": "unreferenced-data",
                "Subtitle": "",
                "TotalCompressedBytes": 1000,
                "TotalUncompressedBytes": 2000,
            },
        ],
    )
    write_csv(
        directory,
        "KernelVersionDatasetSources.csv",
        [{"KernelVersionId": 11, "SourceDatasetVersionId": 501}],
    )
    write_csv(
        directory,
        "Competitions.csv",
        [
            {
                "Id": 1,
                "Slug": "comp1",
                "Title": 'Comp "One"',
                "Subtitle": "",
                "HostSegmentTitle": "Featured",
                "ForumId": 900,
                "EnabledDate": "01/01/2021 00:00:00",
                "DeadlineDate": "06/01/2021 00:00:00",
                "EvaluationAlgorithmName": "AUC",
                "EvaluationAlgorithmIsMax": True,
                "RewardType": "USD",
                "RewardQuantity": 1000,
                "TotalTeams": 5,
                "TotalCompetitors": 5,
                "TotalSubmissions": 10,
            },
            {
                "Id": 2,
                "Slug": "comp2",
                "Title": "Unreferenced Comp",
                "Subtitle": "",
                "HostSegmentTitle": "Featured",
                "ForumId": 901,
                "EnabledDate": "01/01/2021 00:00:00",
                "DeadlineDate": "06/01/2021 00:00:00",
                "EvaluationAlgorithmName": "AUC",
                "EvaluationAlgorithmIsMax": True,
                "RewardType": "USD",
                "RewardQuantity": 1000,
                "TotalTeams": 5,
                "TotalCompetitors": 5,
                "TotalSubmissions": 10,
            },
        ],
    )
    write_csv(
        directory,
        "KernelVersionCompetitionSources.csv",
        [{"KernelVersionId": 11, "SourceCompetitionId": 1}],
    )
    write_csv(
        directory,
        "Forums.csv",
        [
            {"Id": 900, "ParentForumId": "", "Title": "Comp Forum"},
            {"Id": 901, "ParentForumId": "", "Title": "Unreferenced Forum"},
        ],
    )
    write_csv(
        directory,
        "ForumTopics.csv",
        [
            {
                "Id": 2001,
                "ForumId": 900,
                "KernelId": "",
                "CreationDate": "2021-01-05",
                "LastCommentDate": "2021-01-06",
                "Title": "Discussion",
                "IsSticky": False,
                "TotalViews": 10,
                "Score": 0,
                "TotalMessages": 3,
                "TotalReplies": 2,
            },
            {
                "Id": 2002,
                "ForumId": "",
                "KernelId": 1,
                "CreationDate": "2021-01-05",
                "LastCommentDate": "2021-01-06",
                "Title": "Kernel comments",
                "IsSticky": False,
                "TotalViews": 1,
                "Score": 0,
                "TotalMessages": 0,
                "TotalReplies": 0,
            },
            {
                "Id": 2003,
                "ForumId": 999,
                "KernelId": 999,
                "CreationDate": "2021-01-05",
                "LastCommentDate": "2021-01-06",
                "Title": "Unreferenced Topic",
                "IsSticky": False,
                "TotalViews": 0,
                "Score": 0,
                "TotalMessages": 1,
                "TotalReplies": 0,
            },
        ],
    )
    write_csv(
        directory,
        "ForumMessages.csv",
        [
            {
                "Id": 3001,
                "ForumTopicId": 2001,
                "PostUserId": 101,
                "PostDate": "2021-01-05",
                "ReplyToForumMessageId": "",
                "Message": "Great point!\nReally helpful.",
                "RawMarkdown": "Great point!\nReally helpful.",
                "Medal": "",
                "MedalAwardDate": "",
            },
            {
                "Id": 3002,
                "ForumTopicId": 2001,
                "PostUserId": 100,
                "PostDate": "2021-01-06",
                "ReplyToForumMessageId": 3001,
                "Message": "Thanks",
                "RawMarkdown": "Thanks",
                "Medal": "",
                "MedalAwardDate": "",
            },
            {
                "Id": 3003,
                "ForumTopicId": 2001,
                "PostUserId": 100,
                "PostDate": "2021-01-07",
                "ReplyToForumMessageId": 9999,
                "Message": "orphan reply",
                "RawMarkdown": "orphan reply",
                "Medal": "",
                "MedalAwardDate": "",
            },
            {
                "Id": 3004,
                "ForumTopicId": 2003,
                "PostUserId": 100,
                "PostDate": "2021-01-08",
                "ReplyToForumMessageId": "",
                "Message": "excluded topic message",
                "RawMarkdown": "excluded topic message",
                "Medal": "",
                "MedalAwardDate": "",
            },
        ],
    )
    write_csv(
        directory,
        "Tags.csv",
        [
            {
                "Id": 10,
                "ParentTagId": "",
                "Name": "tabular",
                "Slug": "tabular",
                "FullPath": "tabular",
                "Description": "desc",
            }
        ],
    )
    write_csv(directory, "KernelTags.csv", [{"KernelId": 1, "TagId": 10}])
    write_csv(directory, "DatasetTags.csv", [{"DatasetId": 50, "TagId": 10}])
    write_csv(directory, "CompetitionTags.csv", [{"CompetitionId": 1, "TagId": 10}])
    return directory


def _run_pipeline(meta_dir: Path, stage_dir: Path, kernel_limit: int = 2) -> None:
    con = duckdb.connect()
    sks.create_seed_tables(con, meta_dir, kernel_limit)
    sks.stage_nodes(con, meta_dir, stage_dir, include_text=True)
    sks.stage_edges(con, meta_dir, stage_dir)


class TestSqlLiteral:
    def test_escapes_single_quotes(self) -> None:
        assert sks.sql_literal("O'Brien's file.csv") == "'O''Brien''s file.csv'"


class TestKernelSeeding:
    def test_kernel_limit_and_vote_ordering(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir, kernel_limit=2)
        kernels = pl.read_parquet(stage_dir / "nodes_kernel.parquet")
        assert set(kernels["Id"]) == {1, 2}

    def test_project_language_template_is_always_excluded(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir, kernel_limit=100)
        kernels = pl.read_parquet(stage_dir / "nodes_kernel.parquet")
        assert 3 not in set(kernels["Id"])


class TestTextPreservation:
    def test_kernel_version_title_keeps_literal_quotes(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        versions = pl.read_parquet(stage_dir / "nodes_kernel_version.parquet")
        title = versions.filter(pl.col("Id") == 11)["Title"][0]
        assert title == 'Predicting "House Prices"'

    def test_competition_title_keeps_literal_quotes(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        competitions = pl.read_parquet(stage_dir / "nodes_competition.parquet")
        assert competitions["Title"][0] == 'Comp "One"'

    def test_forum_message_keeps_embedded_newline(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        messages = pl.read_parquet(stage_dir / "nodes_forum_message.parquet")
        message = messages.filter(pl.col("Id") == 3001)["Message"][0]
        assert message == "Great point!\nReally helpful."

    def test_include_text_false_nulls_out_message_body(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        con = duckdb.connect()
        sks.create_seed_tables(con, meta_dir, 2)
        sks.stage_nodes(con, meta_dir, stage_dir, include_text=False)
        messages = pl.read_parquet(stage_dir / "nodes_forum_message.parquet")
        assert messages["Message"].is_null().all()


class TestScoping:
    def test_users_scoped_to_referenced_ids(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        users = pl.read_parquet(stage_dir / "nodes_user.parquet")
        assert 999 not in set(users["Id"])
        assert {100, 101}.issubset(set(users["Id"]))

    def test_dataset_versions_scoped_to_referenced_kernel_versions(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        versions = pl.read_parquet(stage_dir / "nodes_dataset_version.parquet")
        assert set(versions["Id"]) == {501}

    def test_competitions_scoped_to_referenced_kernel_versions(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        competitions = pl.read_parquet(stage_dir / "nodes_competition.parquet")
        assert set(competitions["Id"]) == {1}

    def test_forum_topics_include_both_kernel_and_competition_linked_topics(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        topics = pl.read_parquet(stage_dir / "nodes_forum_topic.parquet")
        assert set(topics["Id"]) == {2001, 2002}

    def test_forum_messages_scoped_to_seeded_topics(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        messages = pl.read_parquet(stage_dir / "nodes_forum_message.parquet")
        assert set(messages["Id"]) == {3001, 3002, 3003}

    def test_forums_scoped_to_referenced_forum_ids(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        forums = pl.read_parquet(stage_dir / "nodes_forum.parquet")
        assert set(forums["Id"]) == {900}


class TestEdges:
    def test_unresolved_reply_edge_is_dropped(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        replies = pl.read_parquet(stage_dir / "edges_forum_message_replies_to.parquet")
        pairs = set(
            zip(replies["from_forum_message_id"], replies["to_forum_message_id"], strict=True)
        )
        assert pairs == {(3002, 3001)}

    def test_kernel_first_version_edge_excluded_by_kernel_limit(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir, kernel_limit=2)
        edges = pl.read_parquet(stage_dir / "edges_kernel_first_version.parquet")
        assert 4 not in set(edges["from_kernel_id"])

    def test_dataset_uses_edge_resolves_through_kernel_version(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        edges = pl.read_parquet(stage_dir / "edges_kernel_version_uses_dataset_version.parquet")
        pairs = set(
            zip(edges["from_kernel_version_id"], edges["to_dataset_version_id"], strict=True)
        )
        assert pairs == {(11, 501)}
