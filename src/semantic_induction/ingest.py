"""Stage 1 — ingest & normalize (ARCHITECTURE.md, "Stage 1").

Parses schema DDL into a catalog, parses each query in the corpus, and
qualifies every column reference against that catalog so every downstream
statistic operates on unambiguous "table.column" names. This is the
load-bearing call in the whole pipeline: get it wrong and every later stage
is silently wrong too.
"""
from __future__ import annotations

from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify as sqlglot_qualify

from semantic_induction.models import Catalog, Query


def build_catalog(ddl_path: Path, dialect: str = "duckdb") -> Catalog:
    """Parse CREATE TABLE statements into {table: {column: type}}."""
    ddl_text = ddl_path.read_text(encoding="utf-8")
    statements = sqlglot.parse(ddl_text, dialect=dialect)

    catalog: Catalog = {}
    for stmt in statements:
        if stmt is None or not isinstance(stmt, exp.Create):
            continue
        schema_expr = stmt.this
        if not isinstance(schema_expr, exp.Schema):
            continue
        table_name = schema_expr.this.name
        columns: dict[str, str] = {}
        for col in schema_expr.expressions:
            if isinstance(col, exp.ColumnDef):
                kind = col.args.get("kind")
                columns[col.this.name] = str(kind) if kind else "UNKNOWN"
        catalog[table_name] = columns
    return catalog


def ingest(ddl_path: Path, query_dir: Path, dialect: str = "duckdb") -> tuple[Catalog, list[Query]]:
    """Stage 1 entry point: DDL + query directory -> (catalog, qualified corpus)."""
    catalog = build_catalog(ddl_path, dialect=dialect)

    corpus: list[Query] = []
    for f in sorted(query_dir.glob("*.sql")):
        raw_sql = f.read_text(encoding="utf-8")
        ast = sqlglot.parse_one(raw_sql, dialect=dialect)
        qualified = sqlglot_qualify(ast, schema=catalog, dialect=dialect)
        corpus.append(Query(id=f.stem, ast=qualified, sql=raw_sql))
    return catalog, corpus
