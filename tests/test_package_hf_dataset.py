"""Tests for scripts/package_hf_dataset.py."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl
import pytest

import package_hf_dataset as phd

NODE_FILES = [("nodes_person.parquet", "Person"), ("nodes_city.parquet", "City")]
EDGE_FILES = [("edges_person_lives_in_city.parquet", "Person", "City", "LIVES_IN")]


@pytest.fixture
def stage_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "stage"
    directory.mkdir()
    pl.DataFrame({"Id": [1, 2], "Name": ["alice", "bob"]}).write_parquet(
        directory / "nodes_person.parquet"
    )
    pl.DataFrame({"Id": [10], "Name": ["Oslo"]}).write_parquet(directory / "nodes_city.parquet")
    pl.DataFrame({"from_person_id": [1, 2], "to_city_id": [10, 10]}).write_parquet(
        directory / "edges_person_lives_in_city.parquet"
    )
    return directory


def _meta() -> phd.ReleaseMeta:
    return phd.ReleaseMeta(
        repo_id="someone/example-graph",
        version="2026-08",
        snapshot="2026-08-01",
        source_commit="abc1234",
    )


class TestCollectTables:
    def test_reports_rows_columns_and_kind(self, stage_dir: Path) -> None:
        tables = phd.collect_tables(stage_dir, NODE_FILES, EDGE_FILES)
        by_name = {t.filename: t for t in tables}
        person = by_name["nodes_person.parquet"]
        assert person.kind == "node"
        assert person.label == "Person"
        assert person.rows == 2
        assert [name for name, _ in person.columns] == ["Id", "Name"]
        edge = by_name["edges_person_lives_in_city.parquet"]
        assert edge.kind == "edge"
        assert edge.rows == 2
        assert (edge.src, edge.dst, edge.etype) == ("Person", "City", "LIVES_IN")

    def test_sha256_matches_file_bytes(self, stage_dir: Path) -> None:
        tables = phd.collect_tables(stage_dir, NODE_FILES, EDGE_FILES)
        person = next(t for t in tables if t.filename == "nodes_person.parquet")
        expected = hashlib.sha256((stage_dir / "nodes_person.parquet").read_bytes()).hexdigest()
        assert person.sha256 == expected

    def test_missing_file_raises(self, stage_dir: Path) -> None:
        (stage_dir / "nodes_city.parquet").unlink()
        with pytest.raises(SystemExit, match=r"nodes_city\.parquet"):
            phd.collect_tables(stage_dir, NODE_FILES, EDGE_FILES)


class TestRenderCard:
    def test_front_matter_declares_license_and_one_config_per_table(self, stage_dir: Path) -> None:
        tables = phd.collect_tables(stage_dir, NODE_FILES, EDGE_FILES)
        card = phd.render_card(tables, _meta())
        front_matter = card.split("---")[1]
        assert "license: cc-by-nc-sa-4.0" in front_matter
        assert front_matter.count("- config_name:") == 3
        assert "path: data/nodes_person.parquet" in front_matter
        assert "path: data/edges_person_lives_in_city.parquet" in front_matter

    def test_body_lists_tables_with_row_counts_and_columns(self, stage_dir: Path) -> None:
        tables = phd.collect_tables(stage_dir, NODE_FILES, EDGE_FILES)
        card = phd.render_card(tables, _meta())
        assert "| `Person` | `nodes_person.parquet` | 2 |" in card
        assert "`LIVES_IN`" in card
        assert "`Id`" in card and "`Name`" in card
        assert "2026-08-01" in card
        assert "abc1234" in card

    def test_card_uses_no_em_dashes(self, stage_dir: Path) -> None:
        tables = phd.collect_tables(stage_dir, NODE_FILES, EDGE_FILES)
        assert "—" not in phd.render_card(tables, _meta())


class TestMain:
    def test_writes_card_manifest_and_copies_parquet(
        self, stage_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        output = tmp_path / "release"
        monkeypatch.setattr(phd, "NODE_FILES", NODE_FILES)
        monkeypatch.setattr(phd, "EDGE_FILES", EDGE_FILES)
        monkeypatch.setattr(
            "sys.argv",
            [
                "package_hf_dataset.py",
                "--stage-dir",
                str(stage_dir),
                "--output",
                str(output),
                "--repo-id",
                "someone/example-graph",
                "--snapshot",
                "2026-08-01",
                "--version",
                "2026-08",
                "--source-commit",
                "abc1234",
            ],
        )
        phd.main()

        assert (output / "README.md").exists()
        for filename, *_ in [*NODE_FILES, *EDGE_FILES]:
            assert (output / "data" / filename).read_bytes() == (stage_dir / filename).read_bytes()
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["version"] == "2026-08"
        assert manifest["meta_kaggle_snapshot"] == "2026-08-01"
        assert manifest["source_commit"] == "abc1234"
        rows = {t["filename"]: t["rows"] for t in manifest["tables"]}
        assert rows["nodes_person.parquet"] == 2
        assert rows["edges_person_lives_in_city.parquet"] == 2
