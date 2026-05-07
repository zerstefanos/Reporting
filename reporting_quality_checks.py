"""Dummy reporting quality checks for release version-count testing."""

from __future__ import annotations


def quality_status(error_count: int, warning_count: int) -> str:
    if error_count:
        return "failed"
    if warning_count:
        return "warning"
    return "passed"
