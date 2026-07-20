"""Tests for scripts/inspect_metadata.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from csv_fixtures import write_csv

import inspect_metadata as im


class TestSqlLiteral:
    def test_escapes_single_quotes(self) -> None:
        assert im.sql_literal(Path("O'Brien's file.csv")) == "'O''Brien''s file.csv'"


class TestMain:
    def test_writes_row_counts_and_column_names(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir()
        write_csv(
            meta_dir, "Kernels.csv", [{"Id": 1, "TotalVotes": 10}, {"Id": 2, "TotalVotes": 5}]
        )
        write_csv(meta_dir, "Users.csv", [{"Id": 1, "UserName": "alice"}])

        output = tmp_path / "inventory.md"
        monkeypatch.setattr(
            "sys.argv",
            ["inspect_metadata.py", "--meta-dir", str(meta_dir), "--output", str(output)],
        )
        im.main()

        text = output.read_text(encoding="utf-8")
        assert "Kernels.csv" in text
        assert "Users.csv" in text
        assert "2" in text
        assert "`Id`" in text
        assert "`UserName`" in text

    def test_raises_when_meta_dir_has_no_csvs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setattr(
            "sys.argv",
            [
                "inspect_metadata.py",
                "--meta-dir",
                str(empty_dir),
                "--output",
                str(tmp_path / "out.md"),
            ],
        )
        with pytest.raises(SystemExit):
            im.main()
