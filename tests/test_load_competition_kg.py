"""Tests for scripts/load_competition_kg.py."""

from __future__ import annotations

from pathlib import Path

import pytest

import load_competition_kg as lck


class TestFileListConsistency:
    def test_every_edge_endpoint_label_has_a_node_file(self) -> None:
        node_labels = {label for _, label in lck.NODE_FILES}
        for filename, src, dst, _etype in lck.EDGE_FILES:
            assert src in node_labels, f"{filename}: source label {src!r} has no node file"
            assert dst in node_labels, f"{filename}: dest label {dst!r} has no node file"

    def test_every_text_index_label_has_a_node_file(self) -> None:
        node_labels = {label for _, label in lck.NODE_FILES}
        for label, _prop in lck.TEXT_INDEXES:
            assert label in node_labels, f"TEXT_INDEXES: label {label!r} has no node file"

    def test_no_duplicate_node_filenames(self) -> None:
        filenames = [filename for filename, _ in lck.NODE_FILES]
        assert len(filenames) == len(set(filenames))

    def test_no_duplicate_edge_filenames(self) -> None:
        filenames = [filename for filename, *_ in lck.EDGE_FILES]
        assert len(filenames) == len(set(filenames))

    def test_forum_message_body_has_no_text_index(self) -> None:
        # ForumMessage bodies are deliberately excluded (see module docstring):
        # raw HTML can exceed the LMDB full-text key-size limit.
        assert ("ForumMessage", "Message") not in lck.TEXT_INDEXES


class TestParseArgs:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.argv", ["load_competition_kg.py"])
        args = lck.parse_args()
        assert args.stage_dir == Path("databases/staging_data")
        assert args.db == Path("databases/comp-kg")
        assert args.cli == Path("bin/issundb-cli")
        assert args.map_size_gb == 8


class TestMain:
    def test_forwards_args_to_load_and_validate_and_propagates_exit_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_load_and_validate(**kwargs: object) -> int:
            captured.update(kwargs)
            return 1

        monkeypatch.setattr(lck, "load_and_validate", fake_load_and_validate)
        monkeypatch.setattr(
            "sys.argv",
            ["load_competition_kg.py", "--stage-dir", "/tmp/stage", "--db", "/tmp/db"],
        )
        with pytest.raises(SystemExit) as exc_info:
            lck.main()

        assert exc_info.value.code == 1
        assert captured["stage_dir"] == Path("/tmp/stage")
        assert captured["db"] == Path("/tmp/db")
        assert captured["node_files"] == lck.NODE_FILES
        assert captured["edge_files"] == lck.EDGE_FILES
        assert captured["text_indexes"] == lck.TEXT_INDEXES
