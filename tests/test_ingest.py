from pathlib import Path

from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from semantic_induction.ingest import ingest


def test_ingest_resolves_table_aliases_to_physical_names(tmp_path):
    ddl = tmp_path / "ddl.sql"
    ddl.write_text(
        "CREATE TABLE store_sales(ss_sold_date_sk BIGINT, ss_net_paid DECIMAL(7,2));\n"
        "CREATE TABLE date_dim(d_date_sk BIGINT, d_year BIGINT);\n",
        encoding="utf-8",
    )
    query_dir = tmp_path / "queries"
    query_dir.mkdir()
    (query_dir / "q1.sql").write_text(
        "WITH tmp1 AS (SELECT d.d_year AS y FROM date_dim d)\n"
        "SELECT dt.d_year, SUM(ss.ss_net_paid) AS total, tmp1.y\n"
        "FROM store_sales ss\n"
        "JOIN date_dim dt ON ss.ss_sold_date_sk = dt.d_date_sk\n"
        "JOIN tmp1 ON tmp1.y = dt.d_year\n"
        "GROUP BY dt.d_year, tmp1.y",
        encoding="utf-8",
    )

    _catalog, queries = ingest(ddl, query_dir)

    columns = {column.sql() for column in queries[0].ast.find_all(exp.Column)}

    # A query-local alias for a real catalog table resolves to the physical
    # table name -- this is the ambiguity Stage 1 exists to remove, and
    # downstream consumers (publishability checks, SQL compilation, profile
    # lookups) key on the physical name.
    assert 'date_dim."d_year"' in columns
    assert 'store_sales."ss_net_paid"' in columns
    assert not any(col.startswith('"dt"') or col.startswith('"ss"') for col in columns)

    # A CTE alias is not a physical table -- there is nothing to resolve it
    # to, so it must be left as-is rather than mangled or dropped.
    assert '"tmp1"."y"' in columns


def _assert_no_column_still_reachable_via_a_physical_alias(catalog, queries):
    """No column should still be addressable through a query-local alias
    for a real catalog table -- re-scoping the ingested AST must find
    nothing left to resolve. CTE and derived-table aliases are correctly
    exempt: they are not ``exp.Table`` sources, so they never appear here.
    """
    for query in queries:
        for scope in traverse_scope(query.ast):
            still_aliased = {
                alias
                for alias, source in scope.sources.items()
                if isinstance(source, exp.Table) and source.name in catalog and alias != source.name
            }
            for column in scope.columns:
                assert column.table not in still_aliased, (
                    f"{query.id}: {column.sql()} is still reachable via alias {column.table!r}"
                )


def test_ingest_is_a_fixed_point_of_alias_resolution_on_tpch():
    catalog, queries = ingest(Path("data/tpch/ddl.sql"), Path("data/tpch/queries"))
    _assert_no_column_still_reachable_via_a_physical_alias(catalog, queries)


def test_ingest_is_a_fixed_point_of_alias_resolution_on_tpcds():
    # TPC-DS is where this mattered most: 24 tables, heavy aliasing
    # (`dt` for date_dim, `i1`/`i2` for item), and prior to this fix ~46%
    # of induced metrics were silently unpublishable because of it.
    catalog, queries = ingest(Path("data/tpcds/ddl.sql"), Path("data/tpcds/queries"))
    _assert_no_column_still_reachable_via_a_physical_alias(catalog, queries)
