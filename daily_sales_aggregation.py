"""Dummy daily sales aggregation job for Git Flow release testing."""

from __future__ import annotations

from collections import defaultdict


def aggregate_daily_sales(rows: list[dict[str, object]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        day = str(row.get("sale_date", ""))[:10]
        totals[day] += float(row.get("amount", 0))
    return dict(totals)
