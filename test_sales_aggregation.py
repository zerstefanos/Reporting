"""Tiny dummy tests for the sales aggregation example."""

from daily_sales_aggregation import aggregate_daily_sales


def test_aggregate_daily_sales_groups_by_day() -> None:
    rows = [
        {"sale_date": "2024-01-01T10:00:00", "amount": 100},
        {"sale_date": "2024-01-01T12:00:00", "amount": 50},
        {"sale_date": "2024-01-02T09:00:00", "amount": 75},
    ]

    assert aggregate_daily_sales(rows) == {
        "2024-01-01": 150.0,
        "2024-01-02": 75.0,
    }
