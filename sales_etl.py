"""Dummy sales ETL transformations used to exercise the Git Flow manual."""

from __future__ import annotations


def transform_sales(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Normalize simple sales rows for reporting examples."""
    transformed: list[dict[str, object]] = []
    for row in rows:
        transformed.append(
            {
                "sale_id": row.get("sale_id"),
                "region": str(row.get("region", "")).upper(),
                "amount": float(row.get("amount", 0)),
                "sale_date": row.get("sale_date"),
            }
        )
    return transformed
