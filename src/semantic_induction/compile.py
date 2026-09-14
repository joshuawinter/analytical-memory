"""Compile supported induced metric signatures back into DuckDB SQL."""
from __future__ import annotations

from semantic_induction.models import (
    Catalog,
    CompilationAttempt,
    CompilationCoverage,
    Metric,
)


class CompileError(ValueError):
    """Raised when a metric cannot be rendered without guessing semantics."""


_OPERATORS = {
    "EQ": "=",
    "NEQ": "<>",
    "GT": ">",
    "GTE": ">=",
    "LT": "<",
    "LTE": "<=",
    "IN": "IN",
    "LIKE": "LIKE",
}


def _quote_identifier(value: str) -> str:
    if '"' in value:
        raise CompileError(f"invalid identifier: {value!r}")
    return f'"{value}"'


def _column_parts(value: str) -> tuple[str, str]:
    parts = value.split(".", 1)
    if len(parts) != 2:
        raise CompileError(f"metric column is not qualified: {value!r}")
    return parts[0], parts[1]


def _render_column(value: str, catalog: Catalog) -> str:
    table, column = _column_parts(value)
    if table not in catalog or column not in catalog[table]:
        raise CompileError(f"metric column is not in catalog: {value!r}")
    return f"{_quote_identifier(table)}.{_quote_identifier(column)}"


def compile_metric(metric: Metric, catalog: Catalog) -> str:
    """Render a metric using explicit inner-join predicates and grouping."""
    function, measure_column = metric.measure
    function = function.upper()
    supported = {"SUM", "AVG", "MIN", "MAX", "COUNT"}
    if function not in supported:
        raise CompileError(f"unsupported aggregate: {function}")
    measure_sql = "*" if measure_column == "*" else _render_column(measure_column, catalog)
    selected = [f"{function}({measure_sql}) AS metric_value"]
    selected.extend(
        f"{_render_column(column, catalog)} AS {_quote_identifier(column.rsplit('.', 1)[1])}"
        for column in sorted(metric.grain)
    )
    tables = {_column_parts(measure_column)[0]} if measure_column != "*" else set()
    tables.update(_column_parts(column)[0] for column in metric.grain)
    join_conditions: list[str] = []
    for edge in metric.join_path:
        left_table, _ = _column_parts(edge.left)
        right_table, _ = _column_parts(edge.right)
        tables.update((left_table, right_table))
        join_conditions.append(
            f"{_render_column(edge.left, catalog)} = {_render_column(edge.right, catalog)}"
        )
    if not tables:
        raise CompileError("metric has no physical source table")

    filters = [
        f"{_render_column(predicate.column, catalog)} "
        f"{_OPERATORS.get(predicate.op, predicate.op)} {predicate.value}"
        for predicate in metric.default_filters
    ]
    conditions = join_conditions + filters
    sql = f"SELECT {', '.join(selected)} FROM {', '.join(_quote_identifier(table) for table in sorted(tables))}"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if metric.grain:
        sql += " GROUP BY " + ", ".join(
            _render_column(column, catalog) for column in sorted(metric.grain)
        )
    return sql


def metric_id(metric: Metric) -> str:
    return f"{metric.measure[0]}:{metric.measure[1]}:{','.join(sorted(metric.grain))}"


def _features(metric: Metric) -> tuple[str, ...]:
    features = ["aggregate", "grouping" if metric.grain else "ungrouped"]
    if metric.join_path:
        features.append("inner_join_path")
    if metric.default_filters:
        features.append("filters")
    return tuple(features)


def compile_metric_report(metric: Metric, catalog: Catalog) -> CompilationAttempt:
    """Compile one metric while retaining structured unsupported evidence."""
    try:
        sql = compile_metric(metric, catalog)
    except CompileError as error:
        return CompilationAttempt(
            metric_id=metric_id(metric),
            status="UNSUPPORTED",
            features=_features(metric),
            rejection_reason=str(error),
        )
    except Exception as error:
        return CompilationAttempt(
            metric_id=metric_id(metric),
            status="FAILED",
            features=_features(metric),
            rejection_reason=str(error),
        )
    return CompilationAttempt(
        metric_id=metric_id(metric),
        status="COMPILED",
        features=_features(metric),
        generated_sql=sql,
    )


def compile_metrics(metrics: list[Metric], catalog: Catalog) -> CompilationCoverage:
    """Compile a batch and expose coverage instead of stopping at first error."""
    return CompilationCoverage(
        tuple(compile_metric_report(metric, catalog) for metric in metrics)
    )