"""Tests for scripts/parse_api_calls.py."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

import parse_api_calls as pac


class TestImportAliases:
    def test_plain_import_maps_to_itself(self) -> None:
        assert pac.import_aliases("import numpy") == {"numpy": "numpy"}

    def test_aliased_import(self) -> None:
        assert pac.import_aliases("import numpy as np") == {"np": "numpy"}

    def test_dotted_import_maps_top_name_to_top_module(self) -> None:
        assert pac.import_aliases("import matplotlib.pyplot") == {"matplotlib": "matplotlib"}

    def test_dotted_aliased_import_keeps_full_path(self) -> None:
        assert pac.import_aliases("import matplotlib.pyplot as plt") == {"plt": "matplotlib.pyplot"}

    def test_from_import(self) -> None:
        aliases = pac.import_aliases("from sklearn.ensemble import RandomForestClassifier")
        assert aliases == {"RandomForestClassifier": "sklearn.ensemble.RandomForestClassifier"}

    def test_from_import_with_alias(self) -> None:
        aliases = pac.import_aliases("from pandas import read_csv as rc")
        assert aliases == {"rc": "pandas.read_csv"}

    def test_comma_separated_imports(self) -> None:
        aliases = pac.import_aliases("import os, sys")
        assert aliases == {"os": "os", "sys": "sys"}

    def test_relative_import_is_skipped(self) -> None:
        assert pac.import_aliases("from . import helpers") == {}

    def test_wildcard_import_is_skipped(self) -> None:
        assert pac.import_aliases("from numpy import *") == {}


class TestApiCalls:
    def test_aliased_module_call_is_qualified(self) -> None:
        text = "import numpy as np\nnp.mean([1, 2])\n"
        assert pac.api_calls(text) == {"numpy.mean"}

    def test_nested_attribute_chain_is_qualified(self) -> None:
        text = "import numpy as np\nnp.random.seed(0)\n"
        assert pac.api_calls(text) == {"numpy.random.seed"}

    def test_from_import_call_is_qualified(self) -> None:
        text = (
            "from sklearn.ensemble import RandomForestClassifier\n"
            "model = RandomForestClassifier(n_estimators=100)\n"
        )
        assert pac.api_calls(text) == {"sklearn.ensemble.RandomForestClassifier"}

    def test_local_function_call_is_excluded(self) -> None:
        text = "def foo():\n    return 1\n\nfoo()\n"
        assert pac.api_calls(text) == set()

    def test_method_call_on_local_variable_is_excluded(self) -> None:
        text = "import pandas as pd\ndf = pd.read_csv('x.csv')\ndf.head()\n"
        assert pac.api_calls(text) == {"pandas.read_csv"}

    def test_call_on_call_result_is_excluded(self) -> None:
        text = "import pandas as pd\npd.read_csv('x.csv').head()\n"
        assert pac.api_calls(text) == {"pandas.read_csv"}

    def test_broken_code_still_yields_calls_from_valid_parts(self) -> None:
        text = "import numpy as np\nnp.mean([1, 2])\ndef broken(:\n"
        assert "numpy.mean" in pac.api_calls(text)

    def test_r_code_yields_no_calls(self) -> None:
        text = "library(dplyr)\nx <- mean(c(1, 2))\n"
        assert pac.api_calls(text) == set()


class TestLibraryOf:
    def test_top_level_module_lowercased(self) -> None:
        assert pac.library_of("NumPy.mean") == "numpy"

    def test_single_segment(self) -> None:
        assert pac.library_of("os") == "os"


class TestMain:
    def test_writes_api_call_nodes_and_edges(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()
        code_dir = tmp_path / "code"
        (code_dir / "0000" / "000").mkdir(parents=True)

        pl.DataFrame({"Id": [1, 2]}).write_parquet(stage_dir / "nodes_kernel_version.parquet")
        pl.DataFrame({"Id": ["numpy", "pandas"]}).write_parquet(stage_dir / "nodes_library.parquet")

        (code_dir / "0000" / "000" / "1.py").write_text(
            "import numpy as np\nimport pandas as pd\ndf = pd.read_csv('x.csv')\nnp.mean(df)\n",
            encoding="utf-8",
        )
        notebook = {
            "cells": [
                {"cell_type": "code", "source": ["import numpy as np\n", "np.zeros(3)\n"]},
            ]
        }
        (code_dir / "0000" / "000" / "2.ipynb").write_text(json.dumps(notebook), encoding="utf-8")

        monkeypatch.setattr(
            "sys.argv",
            ["parse_api_calls.py", "--code-dir", str(code_dir), "--stage-dir", str(stage_dir)],
        )
        pac.main()

        nodes = pl.read_parquet(stage_dir / "nodes_api_call.parquet")
        assert set(nodes["Id"]) == {"numpy.mean", "numpy.zeros", "pandas.read_csv"}
        assert set(nodes["Library"]) == {"numpy", "pandas"}

        calls = pl.read_parquet(stage_dir / "edges_kernel_version_calls_api_call.parquet")
        pairs = set(zip(calls["from_kernel_version_id"], calls["to_api_call_id"], strict=True))
        assert pairs == {
            ("1", "numpy.mean"),
            ("1", "pandas.read_csv"),
            ("2", "numpy.zeros"),
        }

        in_library = pl.read_parquet(stage_dir / "edges_api_call_in_library.parquet")
        pairs = set(zip(in_library["from_api_call_id"], in_library["to_library_id"], strict=True))
        assert pairs == {
            ("numpy.mean", "numpy"),
            ("numpy.zeros", "numpy"),
            ("pandas.read_csv", "pandas"),
        }

    def test_library_edges_are_filtered_to_staged_libraries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()
        code_dir = tmp_path / "code"
        (code_dir / "0000" / "000").mkdir(parents=True)

        pl.DataFrame({"Id": [1]}).write_parquet(stage_dir / "nodes_kernel_version.parquet")
        pl.DataFrame({"Id": ["numpy"]}).write_parquet(stage_dir / "nodes_library.parquet")

        (code_dir / "0000" / "000" / "1.py").write_text(
            "import numpy as np\nimport pandas as pd\nnp.mean([1])\npd.read_csv('x.csv')\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            "sys.argv",
            ["parse_api_calls.py", "--code-dir", str(code_dir), "--stage-dir", str(stage_dir)],
        )
        pac.main()

        nodes = pl.read_parquet(stage_dir / "nodes_api_call.parquet")
        assert set(nodes["Id"]) == {"numpy.mean", "pandas.read_csv"}

        in_library = pl.read_parquet(stage_dir / "edges_api_call_in_library.parquet")
        pairs = set(zip(in_library["from_api_call_id"], in_library["to_library_id"], strict=True))
        assert pairs == {("numpy.mean", "numpy")}
