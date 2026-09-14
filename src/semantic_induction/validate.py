"""Stage 6 - execute saved SQL and compare it with reference CSV answers."""
from __future__ import annotations

import csv
from time import perf_counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import duckdb


@dataclass(frozen=True)
class ValidationResult:
    query_id: str
    match: bool
    actual_rows: int
    expected_rows: int
    error: str | None = None
    execution_ms: float | None = None


def _cell(value: Any) -> object:
    if value is None:
        return None
    text = str(value)
    if text == "":
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return text


def _read_answer(path: Path) -> tuple[list[str], list[tuple[object, ...]]]:
    with path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.reader(source))
    if not rows:
        return [], []
    return rows[0], [tuple(_cell(cell) for cell in row) for row in rows[1:]]


def validate_query(
    connection: Any,
    query_path: Path,
    answer_path: Path,
    order_insensitive: bool = True,
) -> ValidationResult:
    query_id = query_path.stem
    started = perf_counter()
    match, actual_rows, expected_rows, error = compare_sql_to_answer(
        connection, query_path.read_text(encoding="utf-8"), answer_path, order_insensitive
    )
    elapsed = (perf_counter() - started) * 1000
    return ValidationResult(query_id, match, actual_rows, expected_rows, error, elapsed)


def compare_sql_to_answer(
    connection: Any,
    sql: str,
    answer_path: Path,
    order_insensitive: bool = True,
) -> tuple[bool, int, int, str | None]:
    """Execute ``sql`` and compare it to a reference CSV; never raises.

    Shared by the saved-query harness above and the Tier 3 arm runners,
    which compare LLM- or plan-derived SQL against the same reference
    answers instead of a file on disk.
    """
    try:
        result = connection.execute(sql)
        actual_columns = [description[0] for description in result.description]
        actual = [tuple(_cell(value) for value in row) for row in result.fetchall()]
        expected_columns, expected = _read_answer(answer_path)
        if order_insensitive:
            actual.sort(key=repr)
            expected.sort(key=repr)
        match = actual_columns == expected_columns and actual == expected
        return match, len(actual), len(expected), None
    except Exception as error:
        return False, 0, 0, str(error)



def validate_corpus(
    database_path: Path,
    query_dir: Path,
    answer_dir: Path,
    limit: int | None = None,
) -> list[ValidationResult]:
    """Validate matching qNN.sql/qNN.csv files against a DuckDB database."""
    query_paths = sorted(query_dir.glob("q*.sql"))
    if limit is not None:
        query_paths = query_paths[:limit]
    with duckdb.connect(str(database_path), read_only=True) as connection:
        return [
            validate_query(connection, query_path, answer_dir / f"{query_path.stem}.csv")
            for query_path in query_paths
        ]