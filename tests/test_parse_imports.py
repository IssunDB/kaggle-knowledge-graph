"""Tests for scripts/parse_imports.py."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

import parse_imports as pi


class TestImportedLibraries:
    def test_plain_import(self) -> None:
        assert pi.imported_libraries("import numpy") == {"numpy"}

    def test_dotted_import_keeps_top_level_only(self) -> None:
        assert pi.imported_libraries("import numpy.random") == {"numpy"}

    def test_from_import(self) -> None:
        assert pi.imported_libraries("from pandas import DataFrame") == {"pandas"}

    def test_aliased_import(self) -> None:
        assert pi.imported_libraries("import numpy as np") == {"numpy"}

    def test_comma_separated_import_captures_every_module(self) -> None:
        assert pi.imported_libraries("import os, sys") == {"os", "sys"}

    def test_comma_separated_import_with_aliases(self) -> None:
        assert pi.imported_libraries("import numpy as np, pandas as pd") == {"numpy", "pandas"}

    def test_indented_import_inside_block(self) -> None:
        text = "try:\n    import ujson\nexcept ImportError:\n    import json\n"
        assert pi.imported_libraries(text) == {"ujson", "json"}

    def test_future_import_is_ignored(self) -> None:
        assert pi.imported_libraries("from __future__ import annotations") == set()

    def test_library_names_are_lowercased(self) -> None:
        assert pi.imported_libraries("import NumPy") == {"numpy"}

    def test_r_library_call(self) -> None:
        assert pi.imported_libraries("library(dplyr)") == {"dplyr"}

    def test_r_require_call_with_quotes(self) -> None:
        assert pi.imported_libraries('require("ggplot2")') == {"ggplot2"}

    def test_mixed_python_and_r_style_noise_is_ignored(self) -> None:
        text = "x <- 1\nimport pandas\nlibrary(dplyr)\n"
        assert pi.imported_libraries(text) == {"pandas", "dplyr"}


class TestCandidatePaths:
    def test_shards_by_zero_padded_id(self) -> None:
        code_dir = Path("/data/meta-kaggle-code")
        paths = pi.candidate_paths(code_dir, "230026147")
        shard = code_dir / "0230" / "026"
        assert paths == [
            shard / "230026147.ipynb",
            shard / "230026147.py",
            shard / "230026147.r",
            shard / "230026147.rmd",
        ]

    def test_short_id_is_zero_padded(self) -> None:
        code_dir = Path("/data/meta-kaggle-code")
        paths = pi.candidate_paths(code_dir, "42")
        assert paths[0].parent == code_dir / "0000" / "000"


class TestNotebookCodeText:
    def test_extracts_only_code_cells(self, tmp_path: Path) -> None:
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title\n"]},
                {"cell_type": "code", "source": ["import pandas as pd\n", "pd.__version__\n"]},
                {"cell_type": "code", "source": "import numpy"},
            ]
        }
        path = tmp_path / "nb.ipynb"
        path.write_text(json.dumps(notebook), encoding="utf-8")
        text = pi.notebook_code_text(path)
        assert "import pandas as pd" in text
        assert "import numpy" in text
        assert "# Title" not in text

    def test_falls_back_to_raw_text_on_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.ipynb"
        path.write_text("import pandas as pd\nnot json", encoding="utf-8")
        assert pi.notebook_code_text(path) == "import pandas as pd\nnot json"


class TestCodeText:
    def test_dispatches_notebook_by_extension(self, tmp_path: Path) -> None:
        notebook = {"cells": [{"cell_type": "code", "source": "import torch"}]}
        path = tmp_path / "nb.ipynb"
        path.write_text(json.dumps(notebook), encoding="utf-8")
        assert pi.code_text(path) == "import torch"

    def test_reads_plain_script_verbatim(self, tmp_path: Path) -> None:
        path = tmp_path / "script.py"
        path.write_text("import torch\n", encoding="utf-8")
        assert pi.code_text(path) == "import torch\n"


class TestLoadKernelVersionIds:
    def test_reads_ids_as_strings(self, tmp_path: Path) -> None:
        stage_dir = tmp_path
        pl.DataFrame({"Id": [1, 2, 3]}).write_parquet(stage_dir / "nodes_kernel_version.parquet")
        assert pi.load_kernel_version_ids(stage_dir) == {"1", "2", "3"}


class TestMain:
    def test_writes_library_nodes_and_import_edges(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()
        code_dir = tmp_path / "code"
        (code_dir / "0000" / "000").mkdir(parents=True)

        pl.DataFrame({"Id": [1]}).write_parquet(stage_dir / "nodes_kernel_version.parquet")
        (code_dir / "0000" / "000" / "1.py").write_text(
            "import os, sys\nimport pandas as pd\n", encoding="utf-8"
        )

        monkeypatch.setattr(
            "sys.argv",
            [
                "parse_imports.py",
                "--code-dir",
                str(code_dir),
                "--stage-dir",
                str(stage_dir),
            ],
        )
        pi.main()

        libraries = pl.read_parquet(stage_dir / "nodes_library.parquet")
        assert set(libraries["Id"]) == {"os", "sys", "pandas"}

        edges = pl.read_parquet(stage_dir / "edges_kernel_version_imports_library.parquet")
        assert set(edges["to_library_id"]) == {"os", "sys", "pandas"}
        assert set(edges["from_kernel_version_id"]) == {"1"}

    def test_no_code_files_writes_typed_empty_outputs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        pl.DataFrame({"Id": [1]}).write_parquet(stage_dir / "nodes_kernel_version.parquet")

        monkeypatch.setattr(
            "sys.argv",
            ["parse_imports.py", "--code-dir", str(code_dir), "--stage-dir", str(stage_dir)],
        )
        pi.main()

        libraries = pl.read_parquet(stage_dir / "nodes_library.parquet")
        edges = pl.read_parquet(stage_dir / "edges_kernel_version_imports_library.parquet")
        assert libraries.height == 0
        assert libraries.schema["Id"] == pl.Utf8
        assert edges.schema["from_kernel_version_id"] == pl.Utf8
        assert edges.schema["to_library_id"] == pl.Utf8


class TestEnvPath:
    def test_expands_tilde_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SOME_DIR", "~/data/code")
        assert pi.env_path("SOME_DIR", Path("/unused")) == Path.home() / "data" / "code"

    def test_falls_back_to_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SOME_DIR", raising=False)
        assert pi.env_path("SOME_DIR", Path("~/fallback")) == Path.home() / "fallback"

    def test_expanded_path_type_for_cli_arguments(self) -> None:
        assert pi.expanded_path("~/x") == Path.home() / "x"
