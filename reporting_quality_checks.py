"""Dummy reporting quality checks for release version-count testing."""

from __future__ import annotations


def quality_status(error_count: int | None, warning_count: int | None) -> str:
    error_count = error_count or 0
    warning_count = warning_count or 0
    if error_count:
        return "failed"
    if warning_count:
        return "warning"
    return "passed"
