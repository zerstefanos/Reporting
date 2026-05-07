"""Dummy revenue threshold helpers for release version-count testing."""

from __future__ import annotations


def classify_revenue(amount: float | None) -> str:
    safe_amount = amount or 0
    if safe_amount >= 50_000:
        return "strategic"
    if safe_amount >= 10_000:
        return "managed"
    return "standard"
