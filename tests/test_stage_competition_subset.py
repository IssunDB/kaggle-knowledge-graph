"""Tests for scripts/stage_competition_subset.py.

Builds a tiny synthetic Meta Kaggle CSV tree covering the post-2020,
non-Community competition scope, then exercises the full
create_seed_tables -> stage_nodes -> stage_edges pipeline against it with an
in-memory DuckDB connection.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl
import pytest
from csv_fixtures import write_csv

import stage_competition_subset as scs


@pytest.fixture
def meta_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "meta"
    directory.mkdir()

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
                "HostName": "Kaggle",
                "ForumId": 900,
                "OrganizationId": "",
                "EnabledDate": "01/15/2020 00:00:00",
                "DeadlineDate": "06/01/2020 00:00:00",
                "EvaluationAlgorithmName": "AUC",
                "EvaluationAlgorithmIsMax": True,
                "RewardType": "USD",
                "RewardQuantity": 1000,
                "MaxTeamSize": 5,
                "TotalTeams": 2,
                "TotalCompetitors": 2,
                "TotalSubmissions": 3,
            },
            {
                "Id": 2,
                "Slug": "comp2-pre-2020",
                "Title": "Pre-2020 Comp",
                "Subtitle": "",
                "HostSegmentTitle": "Featured",
                "HostName": "Kaggle",
                "ForumId": 902,
                "OrganizationId": "",
                "EnabledDate": "01/15/2019 00:00:00",
                "DeadlineDate": "06/01/2019 00:00:00",
                "EvaluationAlgorithmName": "AUC",
                "EvaluationAlgorithmIsMax": True,
                "RewardType": "USD",
                "RewardQuantity": 1000,
                "MaxTeamSize": 5,
                "TotalTeams": 1,
                "TotalCompetitors": 1,
                "TotalSubmissions": 1,
            },
            {
                "Id": 3,
                "Slug": "comp3-community",
                "Title": "Community Comp",
                "Subtitle": "",
                "HostSegmentTitle": "Community",
                "HostName": "Kaggle",
                "ForumId": 903,
                "OrganizationId": "",
                "EnabledDate": "01/15/2021 00:00:00",
                "DeadlineDate": "06/01/2021 00:00:00",
                "EvaluationAlgorithmName": "AUC",
                "EvaluationAlgorithmIsMax": True,
                "RewardType": "USD",
                "RewardQuantity": 1000,
                "MaxTeamSize": 5,
                "TotalTeams": 1,
                "TotalCompetitors": 1,
                "TotalSubmissions": 1,
            },
            {
                "Id": 4,
                "Slug": "comp4-bad-date",
                "Title": "Bad Date Comp",
                "Subtitle": "",
                "HostSegmentTitle": "Featured",
                "HostName": "Kaggle",
                "ForumId": 904,
                "OrganizationId": "",
                "EnabledDate": "not-a-date",
                "DeadlineDate": "06/01/2021 00:00:00",
                "EvaluationAlgorithmName": "AUC",
                "EvaluationAlgorithmIsMax": True,
                "RewardType": "USD",
                "RewardQuantity": 1000,
                "MaxTeamSize": 5,
                "TotalTeams": 1,
                "TotalCompetitors": 1,
                "TotalSubmissions": 1,
            },
        ],
    )
    write_csv(
        directory,
        "Teams.csv",
        [
            {
                "Id": 101,
                "CompetitionId": 1,
                "TeamName": "Team One",
                "Medal": "",
                "PublicLeaderboardRank": 1,
                "PrivateLeaderboardRank": 1,
                "ScoreFirstSubmittedDate": "2020-02-01",
                "LastSubmissionDate": "2020-02-02",
                "IsBenchmark": False,
                "TeamLeaderId": 200,
                "PublicLeaderboardSubmissionId": 301,
                "PrivateLeaderboardSubmissionId": 302,
            },
            {
                "Id": 102,
                "CompetitionId": 1,
                "TeamName": "Unranked Team",
                "Medal": "",
                "PublicLeaderboardRank": "",
                "PrivateLeaderboardRank": "",
                "ScoreFirstSubmittedDate": "2020-02-01",
                "LastSubmissionDate": "2020-02-02",
                "IsBenchmark": False,
                "TeamLeaderId": 202,
                "PublicLeaderboardSubmissionId": "",
                "PrivateLeaderboardSubmissionId": "",
            },
        ],
    )
    write_csv(
        directory,
        "TeamMemberships.csv",
        [{"Id": 1, "TeamId": 101, "UserId": 201}],
    )
    write_csv(
        directory,
        "Submissions.csv",
        [
            {
                "Id": 301,
                "TeamId": 101,
                "SubmittedUserId": 201,
                "SourceKernelVersionId": 11,
                "SubmissionDate": "2020-02-01",
                "ScoreDate": "2020-02-01",
                "IsAfterDeadline": False,
                "IsSelected": False,
                "PublicScoreFullPrecision": 0.9,
                "PrivateScoreFullPrecision": 0.9,
            },
            {
                "Id": 302,
                "TeamId": 101,
                "SubmittedUserId": 201,
                "SourceKernelVersionId": "",
                "SubmissionDate": "2020-02-02",
                "ScoreDate": "2020-02-02",
                "IsAfterDeadline": False,
                "IsSelected": True,
                "PublicScoreFullPrecision": 0.95,
                "PrivateScoreFullPrecision": 0.95,
            },
            {
                "Id": 303,
                "TeamId": 102,
                "SubmittedUserId": 202,
                "SourceKernelVersionId": "",
                "SubmissionDate": "2020-02-03",
                "ScoreDate": "2020-02-03",
                "IsAfterDeadline": False,
                "IsSelected": True,
                "PublicScoreFullPrecision": 0.5,
                "PrivateScoreFullPrecision": 0.5,
            },
        ],
    )
    write_csv(
        directory,
        "KernelVersionCompetitionSources.csv",
        [
            {"KernelVersionId": 11, "SourceCompetitionId": 1},
            {"KernelVersionId": 21, "SourceCompetitionId": 1},
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
                "CreationDate": "2020-02-01",
                "TotalLines": 50,
                "TotalVotes": 10,
                "IsInternetEnabled": False,
                "RunningTimeInMilliseconds": 1000,
                "DockerImage": "img1",
                "AuthorUserId": 200,
            },
            {
                "Id": 21,
                "ScriptId": 2,
                "VersionNumber": 1,
                "Title": "Second Kernel",
                "CreationDate": "2020-02-01",
                "TotalLines": 10,
                "TotalVotes": 5,
                "IsInternetEnabled": False,
                "RunningTimeInMilliseconds": 200,
                "DockerImage": "img1",
                "AuthorUserId": 201,
            },
        ],
    )
    write_csv(
        directory,
        "Kernels.csv",
        [
            {
                "Id": 1,
                "AuthorUserId": 200,
                "CurrentKernelVersionId": 11,
                "FirstKernelVersionId": 11,
                "ForumTopicId": "",
                "CreationDate": "2020-02-01",
                "Medal": "",
                "TotalViews": 100,
                "TotalComments": 1,
                "TotalVotes": 10,
                "CurrentUrlSlug": "house-prices",
            },
            {
                "Id": 2,
                "AuthorUserId": 201,
                "CurrentKernelVersionId": 21,
                "FirstKernelVersionId": 21,
                "ForumTopicId": "",
                "CreationDate": "2020-02-01",
                "Medal": "",
                "TotalViews": 20,
                "TotalComments": 0,
                "TotalVotes": 5,
                "CurrentUrlSlug": "second-kernel",
            },
        ],
    )
    write_csv(
        directory,
        "Forums.csv",
        [
            {"Id": 900, "ParentForumId": "", "Title": "Comp Forum"},
            {"Id": 901, "ParentForumId": "", "Title": "Unrelated Forum"},
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
                "CreationDate": "2020-02-05",
                "LastCommentDate": "2020-02-06",
                "Title": "Discussion",
                "IsSticky": False,
                "TotalViews": 10,
                "Score": 0,
                "TotalMessages": 1,
                "TotalReplies": 0,
            },
            {
                "Id": 2002,
                "ForumId": 901,
                "KernelId": "",
                "CreationDate": "2020-02-05",
                "LastCommentDate": "2020-02-06",
                "Title": "Unrelated Topic",
                "IsSticky": False,
                "TotalViews": 0,
                "Score": 0,
                "TotalMessages": 0,
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
                "PostUserId": 201,
                "PostDate": "2020-02-05",
                "ReplyToForumMessageId": "",
                "Message": "Nice work!\nKeep it up.",
                "RawMarkdown": "Nice work!\nKeep it up.",
                "Medal": "",
                "MedalAwardDate": "",
            },
            {
                "Id": 3002,
                "ForumTopicId": 2002,
                "PostUserId": 999,
                "PostDate": "2020-02-05",
                "ReplyToForumMessageId": "",
                "Message": "excluded",
                "RawMarkdown": "excluded",
                "Medal": "",
                "MedalAwardDate": "",
            },
        ],
    )
    write_csv(
        directory,
        "Users.csv",
        [
            {
                "Id": 200,
                "UserName": "alice",
                "DisplayName": "Alice A",
                "RegisterDate": "2019-01-01",
                "PerformanceTier": 2,
                "Country": "US",
            },
            {
                "Id": 201,
                "UserName": "bob",
                "DisplayName": "Bob B",
                "RegisterDate": "2019-01-02",
                "PerformanceTier": 1,
                "Country": "CA",
            },
            {
                "Id": 999,
                "UserName": "unrelated",
                "DisplayName": "Unrelated",
                "RegisterDate": "2019-01-03",
                "PerformanceTier": 0,
                "Country": "",
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
    write_csv(directory, "CompetitionTags.csv", [{"CompetitionId": 1, "TagId": 10}])
    return directory


def _run_pipeline(meta_dir: Path, stage_dir: Path, kernels_per_competition: int = 50) -> None:
    con = duckdb.connect()
    scs.create_seed_tables(con, meta_dir, kernels_per_competition)
    scs.stage_nodes(con, meta_dir, stage_dir, include_text=True)
    scs.stage_edges(con, meta_dir, stage_dir)


class TestCompetitionScope:
    def test_only_post_2020_non_community_competitions_are_seeded(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        competitions = pl.read_parquet(stage_dir / "nodes_competition.parquet")
        assert set(competitions["Id"]) == {1}

    def test_unparseable_enabled_date_warns_once(
        self, meta_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        con = duckdb.connect()
        scs.warn_on_unparseable_enabled_dates(con, meta_dir)
        captured = capsys.readouterr()
        assert "1 competition row(s)" in captured.err

    def test_no_warning_when_all_dates_parse(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        directory = tmp_path / "clean_meta"
        directory.mkdir()
        write_csv(
            directory,
            "Competitions.csv",
            [
                {
                    "Id": 1,
                    "Slug": "c",
                    "Title": "C",
                    "Subtitle": "",
                    "HostSegmentTitle": "Featured",
                    "HostName": "Kaggle",
                    "ForumId": 900,
                    "OrganizationId": "",
                    "EnabledDate": "01/15/2020 00:00:00",
                    "DeadlineDate": "06/01/2020 00:00:00",
                    "EvaluationAlgorithmName": "AUC",
                    "EvaluationAlgorithmIsMax": True,
                    "RewardType": "USD",
                    "RewardQuantity": 1000,
                    "MaxTeamSize": 5,
                    "TotalTeams": 1,
                    "TotalCompetitors": 1,
                    "TotalSubmissions": 1,
                }
            ],
        )
        con = duckdb.connect()
        scs.warn_on_unparseable_enabled_dates(con, directory)
        captured = capsys.readouterr()
        assert captured.err == ""


class TestTeamAndSubmissionScope:
    def test_only_ranked_or_medaled_teams_are_seeded(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        teams = pl.read_parquet(stage_dir / "nodes_team.parquet")
        assert set(teams["Id"]) == {101}

    def test_selected_and_leaderboard_submissions_are_seeded(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        submissions = pl.read_parquet(stage_dir / "nodes_submission.parquet")
        assert set(submissions["Id"]) == {301, 302}


class TestKernelRanking:
    def test_kernels_per_competition_limits_to_top_voted(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir, kernels_per_competition=1)
        kernels = pl.read_parquet(stage_dir / "nodes_kernel.parquet")
        assert set(kernels["Id"]) == {1}

    def test_higher_limit_includes_both_kernels(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir, kernels_per_competition=2)
        kernels = pl.read_parquet(stage_dir / "nodes_kernel.parquet")
        assert set(kernels["Id"]) == {1, 2}


class TestTextPreservation:
    def test_competition_title_keeps_literal_quotes(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        competitions = pl.read_parquet(stage_dir / "nodes_competition.parquet")
        assert competitions["Title"][0] == 'Comp "One"'

    def test_kernel_version_title_keeps_literal_quotes(
        self, meta_dir: Path, tmp_path: Path
    ) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir, kernels_per_competition=2)
        versions = pl.read_parquet(stage_dir / "nodes_kernel_version.parquet")
        title = versions.filter(pl.col("Id") == 11)["Title"][0]
        assert title == 'Predicting "House Prices"'

    def test_forum_message_keeps_embedded_newline(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        messages = pl.read_parquet(stage_dir / "nodes_forum_message.parquet")
        message = messages.filter(pl.col("Id") == 3001)["Message"][0]
        assert message == "Nice work!\nKeep it up."


class TestUserScoping:
    def test_users_scoped_to_referenced_ids(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        users = pl.read_parquet(stage_dir / "nodes_user.parquet")
        assert 999 not in set(users["Id"])
        assert {200, 201}.issubset(set(users["Id"]))


class TestEdges:
    def test_submission_from_kernel_version_resolves(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        edges = pl.read_parquet(stage_dir / "edges_submission_from_kernel_version.parquet")
        pairs = set(zip(edges["from_submission_id"], edges["to_kernel_version_id"], strict=True))
        assert pairs == {(301, 11)}

    def test_team_public_leaderboard_submission_edge(self, meta_dir: Path, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        _run_pipeline(meta_dir, stage_dir)
        edges = pl.read_parquet(stage_dir / "edges_team_public_leaderboard_submission.parquet")
        pairs = set(zip(edges["from_team_id"], edges["to_submission_id"], strict=True))
        assert pairs == {(101, 301)}
