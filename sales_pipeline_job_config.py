"""Dummy exported job configuration for release-note and Git Flow tests."""

SALES_PIPELINE_JOB = {
    "name": "sales_pipeline",
    "schedule": "0 6 * * *",
    "source": "PostgreSQL.Database",
    "target": "PowerBI.Reporting",
    "enabled": True,
}
