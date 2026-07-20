"""Tests for scripts/issundb_load.py, the shared IssunDB bulk-load driver."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

import issundb_load as il

REPO_ROOT = Path(__file__).resolve().parent.parent
ISSUNDB_CLI = REPO_ROOT / "bin" / "issundb-cli"

requires_cli = pytest.mark.skipif(
    not ISSUNDB_CLI.exists(), reason="bin/issundb-cli binary is not present"
)


class TestCountDataRows:
    def test_counts_parquet_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "nodes.parquet"
        pl.DataFrame({"Id": [1, 2, 3]}).write_parquet(path)
        assert il.count_data_rows(path) == 3


class TestBuildScript:
    def test_orders_nodes_before_edges_and_appends_constraints(self, tmp_path: Path) -> None:
        pl.DataFrame({"Id": [1, 2]}).write_parquet(tmp_path / "nodes_a.parquet")
        pl.DataFrame({"from_a_id": [1], "to_a_id": [2]}).write_parquet(tmp_path / "edges_a.parquet")
        script, expected_nodes = il.build_script(
            tmp_path,
            node_files=[("nodes_a.parquet", "A")],
            edge_files=[("edges_a.parquet", "A", "A", "SELF")],
            text_indexes=[("A", "Name")],
            missing_hint="run make x",
        )
        lines = script.splitlines()
        assert lines[0] == f":import-nodes {(tmp_path / 'nodes_a.parquet').resolve()} A"
        assert lines[1] == f":import-edges {(tmp_path / 'edges_a.parquet').resolve()} A A SELF"
        assert "CREATE CONSTRAINT ON (n:A) ASSERT n.Id IS UNIQUE" in lines
        assert "CREATE INDEX FOR (n:A) ON (n.Name)" in lines
        assert lines[-3:] == ["rebuild-csr", "stats", "quit"]
        assert expected_nodes == {"nodes_a.parquet": 2}

    def test_missing_node_file_raises_with_hint(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="run make x"):
            il.build_script(
                tmp_path,
                node_files=[("nodes_missing.parquet", "A")],
                edge_files=[],
                text_indexes=[],
                missing_hint="run make x",
            )

    def test_missing_edge_file_raises_with_hint(self, tmp_path: Path) -> None:
        pl.DataFrame({"Id": [1]}).write_parquet(tmp_path / "nodes_a.parquet")
        with pytest.raises(SystemExit, match="run make x"):
            il.build_script(
                tmp_path,
                node_files=[("nodes_a.parquet", "A")],
                edge_files=[("edges_missing.parquet", "A", "A", "SELF")],
                text_indexes=[],
                missing_hint="run make x",
            )


class TestValidate:
    def test_passes_when_counts_match_and_no_errors(self) -> None:
        log = (
            "imported 2 A nodes from /tmp/nodes_a.parquet\n"
            "imported 1 SELF edges from /tmp/edges_a.parquet "
            "(0 unresolved endpoint(s), 0 malformed row(s))\n"
        )
        assert il.validate(log, {"nodes_a.parquet": 2}) == []

    def test_flags_import_count_below_expected(self) -> None:
        log = "imported 1 A nodes from /tmp/nodes_a.parquet\n"
        failures = il.validate(log, {"nodes_a.parquet": 2})
        assert any("imported 1 nodes, expected 2 staged rows" in f for f in failures)

    def test_flags_malformed_edge_rows(self) -> None:
        log = "imported 1 SELF edges from /tmp/edges_a.parquet (0 unresolved endpoint(s), 2 malformed row(s))\n"
        failures = il.validate(log, {})
        assert any("2 malformed edge row(s)" in f for f in failures)

    def test_flags_command_error_lines(self) -> None:
        log = "Error: constraint violation\n"
        failures = il.validate(log, {})
        assert any("command error" in f for f in failures)

    def test_flags_missing_import_line_for_expected_file(self) -> None:
        failures = il.validate("", {"nodes_a.parquet": 2})
        assert any("no import line found in log" in f for f in failures)


@requires_cli
class TestLoadAndValidateIntegration:
    def test_successful_load_passes_validation(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()
        pl.DataFrame({"Id": [1, 2], "Name": ["alice", "bob"]}).write_parquet(
            stage_dir / "nodes_person.parquet"
        )
        pl.DataFrame({"from_person_id": [1], "to_person_id": [2]}).write_parquet(
            stage_dir / "edges_knows.parquet"
        )

        exit_code = il.load_and_validate(
            stage_dir=stage_dir,
            db=tmp_path / "db",
            cli=ISSUNDB_CLI,
            map_size_gb=1,
            script_path=tmp_path / "load.issun",
            log_path=tmp_path / "load.log",
            node_files=[("nodes_person.parquet", "Person")],
            edge_files=[("edges_knows.parquet", "Person", "Person", "KNOWS")],
            text_indexes=[("Person", "Name")],
            missing_hint="n/a",
        )
        assert exit_code == 0
        log_text = (tmp_path / "load.log").read_text(encoding="utf-8")
        assert "0 malformed row(s)" in log_text

    def test_duplicate_id_fails_the_uniqueness_constraint(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()
        pl.DataFrame({"Id": [1, 1], "Name": ["alice", "alice-dup"]}).write_parquet(
            stage_dir / "nodes_person.parquet"
        )

        exit_code = il.load_and_validate(
            stage_dir=stage_dir,
            db=tmp_path / "db",
            cli=ISSUNDB_CLI,
            map_size_gb=1,
            script_path=tmp_path / "load.issun",
            log_path=tmp_path / "load.log",
            node_files=[("nodes_person.parquet", "Person")],
            edge_files=[],
            text_indexes=[],
            missing_hint="n/a",
        )
        assert exit_code == 1
