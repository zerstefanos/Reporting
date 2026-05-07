"""Dummy customer segmentation logic for Git Flow examples."""

from __future__ import annotations


def segment_customer(total_revenue: float) -> str:
    if total_revenue >= 10_000:
        return "enterprise"
    if total_revenue >= 2_500:
        return "growth"
    return "standard"
