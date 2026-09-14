"""Stage 1b - profile DuckDB data and capture bounded samples."""
from __future__ import annotations

from typing import Any

from semantic_induction.models import Catalog, ColumnProfile, TableProfile


def _identifier(value: str) -> str:
    """Quote a DuckDB identifier after rejecting embedded quotes."""
    if '"' in value:
        raise ValueError(f"invalid identifier: {value!r}")
    return f'"{value}"'


def profile_database(
    connection: Any,
    catalog: Catalog,
    sample_size: int = 100,
    top_values: int = 5,
) -> dict[str, TableProfile]:
    """Profile catalog tables and capture deterministic bounded samples.

    Statistics are computed from the full table. Samples are limited to the
    requested number of rows and are evidence for inspection, not semantic
    truth. Table and column names come only from the parsed catalog.
    """
    if sample_size < 0 or top_values < 0:
        raise ValueError("sample_size and top_values must be non-negative")

    profiles: dict[str, TableProfile] = {}
    for table, columns in catalog.items():
        quoted_table = _identifier(table)
        row_count = connection.execute(
            f"SELECT COUNT(*) FROM {quoted_table}"
        ).fetchone()[0]
        column_profiles: dict[str, ColumnProfile] = {}
        for column in columns:
            quoted_column = _identifier(column)
            stats = connection.execute(
                f"SELECT COUNT(*), COUNT({quoted_column}), "
                f"COUNT(DISTINCT {quoted_column}), MIN({quoted_column}), "
                f"MAX({quoted_column}) FROM {quoted_table}"
            ).fetchone()
            values = connection.execute(
                f"SELECT CAST({quoted_column} AS VARCHAR), COUNT(*) "
                f"FROM {quoted_table} WHERE {quoted_column} IS NOT NULL "
                f"GROUP BY {quoted_column} ORDER BY COUNT(*) DESC, 1 "
                f"LIMIT {top_values}"
            ).fetchall()
            column_profiles[column] = ColumnProfile(
                table=table,
                column=column,
                row_count=stats[0],
                null_count=stats[0] - stats[1],
                distinct_count=stats[2],
                min_value=None if stats[3] is None else str(stats[3]),
                max_value=None if stats[4] is None else str(stats[4]),
                top_values=tuple((str(value), count) for value, count in values),
            )

        sample_columns = tuple(columns)
        if sample_size:
            sample_rows = connection.execute(
                f"SELECT * FROM {quoted_table} USING SAMPLE {sample_size} "
                "(reservoir, 42)"
            ).fetchmany(sample_size)
        else:
            sample_rows = []
        profiles[table] = TableProfile(
            table=table,
            row_count=row_count,
            columns=column_profiles,
            sample_columns=sample_columns,
            sample_rows=tuple(tuple(row) for row in sample_rows),
        )
    return profiles