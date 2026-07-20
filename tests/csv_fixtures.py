"""Helpers for writing tiny synthetic Meta Kaggle CSV fixtures in tests."""

from __future__ import annotations

import csv as csv_module
from pathlib import Path
from typing import Any


def write_csv(directory: Path, name: str, rows: list[dict[str, Any]]) -> Path:
    """Write `rows` (a list of dicts sharing the same keys) as a CSV file."""
    path = directory / name
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv_module.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
