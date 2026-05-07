"""Dummy revenue threshold helpers for release version-count testing."""

from __future__ import annotations


def classify_revenue(amount: float) -> str:
    if amount >= 50_000:
        return "strategic"
    if amount >= 10_000:
        return "managed"
    return "standard"
