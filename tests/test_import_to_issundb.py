"""Tests for scripts/import_to_issundb.py."""

from __future__ import annotations

from pathlib import Path

import pytest

import import_to_issundb as iti


class TestFileListConsistency:
    def test_every_edge_endpoint_label_has_a_node_file(self) -> None:
        node_labels = {label for _, label in iti.NODE_FILES}
        for filename, src, dst, _etype in iti.EDGE_FILES:
            assert src in node_labels, f"{filename}: source label {src!r} has no node file"
            assert dst in node_labels, f"{filename}: dest label {dst!r} has no node file"

    def test_every_text_index_label_has_a_node_file(self) -> None:
        node_labels = {label for _, label in iti.NODE_FILES}
        for label, _prop in iti.TEXT_INDEXES:
            assert label in node_labels, f"TEXT_INDEXES: label {label!r} has no node file"

    def test_no_duplicate_node_filenames(self) -> None:
        filenames = [filename for filename, _ in iti.NODE_FILES]
        assert len(filenames) == len(set(filenames))

    def test_no_duplicate_edge_filenames(self) -> None:
        filenames = [filename for filename, *_ in iti.EDGE_FILES]
        assert len(filenames) == len(set(filenames))


class TestParseArgs:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STAGE_DIR", raising=False)
        monkeypatch.setattr("sys.argv", ["import_to_issundb.py"])
        args = iti.parse_args()
        assert args.stage_dir == Path("stage")
        assert args.db == Path("databases/kernel-kg")
        assert args.cli == Path("bin/issundb-cli")
        assert args.map_size_gb == 8

    def test_stage_dir_flag_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sys.argv", ["import_to_issundb.py", "--stage-dir", "/tmp/custom-stage"]
        )
        args = iti.parse_args()
        assert args.stage_dir == Path("/tmp/custom-stage")


class TestMain:
    def test_forwards_args_to_load_and_validate_and_propagates_exit_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_load_and_validate(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(iti, "load_and_validate", fake_load_and_validate)
        monkeypatch.setattr("sys.argv", ["import_to_issundb.py"])
        with pytest.raises(SystemExit) as exc_info:
            iti.main()

        assert exc_info.value.code == 0
        assert captured["node_files"] == iti.NODE_FILES
        assert captured["edge_files"] == iti.EDGE_FILES
        assert captured["text_indexes"] == iti.TEXT_INDEXES
