"""Stage 2 - extract deterministic facts from qualified SQL ASTs."""
from __future__ import annotations

from collections.abc import Iterable

from sqlglot import exp

from semantic_induction.models import (
    Agg,
    Catalog,
    ColumnLineage,
    Correlation,
    JoinEdge,
    Predicate,
    QueryBlock,
    QueryFacts,
    SetOperation,
    Window,
)


_PREDICATE_OPS = {
    exp.EQ: "EQ",
    exp.NEQ: "NEQ",
    exp.GT: "GT",
    exp.GTE: "GTE",
    exp.LT: "LT",
    exp.LTE: "LTE",
    exp.In: "IN",
    exp.Between: "BETWEEN",
    exp.Like: "LIKE",
}


def _column_name(column: exp.Column) -> str:
    return f"{column.table}.{column.name}" if column.table else column.name


def _columns(expression: exp.Expression | list[exp.Expression]) -> list[str]:
    if isinstance(expression, list):
        return [column for item in expression for column in _columns(item)]
    return [_column_name(column) for column in expression.find_all(exp.Column)]


def _is_column_pair(expression: exp.Expression) -> bool:
    return isinstance(expression.left, exp.Column) and isinstance(
        expression.right, exp.Column
    )


def _join_edges(ast: exp.Expression) -> list[JoinEdge]:
    edges: list[JoinEdge] = []
    seen: set[JoinEdge] = set()
    for comparison in ast.find_all(exp.EQ):
        if not _is_column_pair(comparison):
            continue
        left = _column_name(comparison.left)
        right = _column_name(comparison.right)
        if left.split(".")[0] == right.split(".")[0]:
            continue
        join = comparison.find_ancestor(exp.Join)
        join_type = "INNER"
        if join is not None:
            join_type = (join.args.get("side") or join.args.get("kind") or "INNER").upper()
        edge = JoinEdge(left, right, join_type)
        if edge not in seen:
            seen.add(edge)
            edges.append(edge)
    return edges


def _aggregate_alias(aggregate: exp.Expression) -> str | None:
    parent = aggregate.parent
    while parent is not None and not isinstance(parent, (exp.Select, exp.Alias)):
        parent = parent.parent
    return parent.alias if isinstance(parent, exp.Alias) else None


def _aggregations(ast: exp.Expression) -> list[Agg]:
    aggregations: list[Agg] = []
    for aggregate in ast.find_all(exp.AggFunc):
        column_expr = aggregate.this
        if isinstance(column_expr, exp.Star):
            column = "*"
        else:
            found_columns = _columns(column_expr) if column_expr is not None else []
            column = found_columns[0] if found_columns else "*"
        aggregations.append(
            Agg(
                func=aggregate.key.upper(),
                column=column,
                alias=_aggregate_alias(aggregate),
            )
        )
    return aggregations


def _predicate_value(expression: exp.Expression) -> str:
    return expression.sql(dialect="duckdb")


def _predicates(ast: exp.Expression) -> list[Predicate]:
    predicates: list[Predicate] = []
    for expression_type, operator in _PREDICATE_OPS.items():
        for expression in ast.find_all(expression_type):
            if isinstance(expression, exp.Between):
                column = expression.this
                value = f"{expression.args['low'].sql()} AND {expression.args['high'].sql()}"
            elif isinstance(expression, exp.In):
                column = expression.this
                values = expression.args.get("expressions")
                query = expression.args.get("query")
                if values:
                    value = ", ".join(_predicate_value(item) for item in values)
                elif query is not None:
                    value = _predicate_value(query)
                else:
                    value = ""
            else:
                if _is_column_pair(expression):
                    continue
                column = expression.left
                value = _predicate_value(expression.right)
            if isinstance(column, exp.Column):
                predicates.append(Predicate(_column_name(column), operator, value))
    return predicates


def _cte_names(ast: exp.Expression) -> set[str]:
    return {cte.alias for cte in ast.find_all(exp.CTE)}


def _table_aliases(ast: exp.Expression, catalog: Catalog | None) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for table in ast.find_all(exp.Table):
        if table.name in (catalog or {}) and table.alias:
            aliases[table.alias] = table.name
    return aliases


def _tables(
    ast: exp.Expression,
    catalog: Catalog | None = None,
    cte_names: set[str] | None = None,
) -> set[str]:
    cte_names = cte_names or set()
    tables: set[str] = set()
    for table in ast.find_all(exp.Table):
        if table.name in cte_names:
            continue
        if catalog is None or table.name in catalog:
            tables.add(table.name)
    return tables


def _lineage_for_select(
    select: exp.Select,
    cte_lineage: dict[str, dict[str, ColumnLineage]],
    aliases: dict[str, str],
) -> dict[str, ColumnLineage]:
    lineage: dict[str, ColumnLineage] = {}
    for expression in select.expressions:
        output_name = expression.alias_or_name
        sources: list[str] = []
        status = "SUPPORTED"
        for column in expression.find_all(exp.Column):
            table_name = aliases.get(column.table, column.table)
            block_lineage = cte_lineage.get(table_name)
            if block_lineage is not None:
                source = block_lineage.get(column.name)
                if source is None:
                    status = "UNRESOLVED"
                else:
                    sources.extend(source.sources)
                    if source.status != "SUPPORTED":
                        status = "PARTIAL"
            elif table_name:
                sources.append(f"{table_name}.{column.name}")
            else:
                status = "UNRESOLVED"
        lineage[output_name] = ColumnLineage(tuple(dict.fromkeys(sources)), status)
    return lineage


def _query_blocks(
    ast: exp.Expression,
    catalog: Catalog | None,
) -> tuple[list[QueryBlock], dict[str, ColumnLineage]]:
    cte_names = _cte_names(ast)
    aliases = _table_aliases(ast, catalog)
    blocks: list[QueryBlock] = []
    cte_lineage: dict[str, dict[str, ColumnLineage]] = {}
    flattened: dict[str, ColumnLineage] = {}

    for cte in ast.find_all(exp.CTE):
        select = cte.this if isinstance(cte.this, exp.Select) else cte.this.find(exp.Select)
        if select is None:
            continue
        output_lineage = _lineage_for_select(select, cte_lineage, aliases)
        cte_lineage[cte.alias] = output_lineage
        blocks.append(
            QueryBlock(
                block_id=cte.alias,
                kind="CTE",
                parent_id="main",
                tables=_tables(select, catalog, cte_names),
                output_lineage=output_lineage,
            )
        )
        flattened.update({f"{cte.alias}.{name}": value for name, value in output_lineage.items()})

    main = ast if isinstance(ast, exp.Select) else ast.find(exp.Select)
    if main is not None:
        output_lineage = _lineage_for_select(main, cte_lineage, aliases)
        blocks.append(
            QueryBlock(
                block_id="main",
                kind="MAIN",
                tables=_tables(main, catalog, cte_names),
                output_lineage=output_lineage,
            )
        )
        flattened.update({f"main.{name}": value for name, value in output_lineage.items()})
    return blocks, flattened


def _direct_tables(select: exp.Select) -> set[str]:
    """Return relation names owned by this SELECT, excluding nested scopes."""
    tables: set[str] = set()
    for table in select.find_all(exp.Table):
        if table.find_ancestor(exp.Select) is select:
            tables.add(table.alias or table.name)
    return tables


def _direct_relations(select: exp.Select) -> dict[str, str]:
    relations: dict[str, str] = {}
    for table in select.find_all(exp.Table):
        if table.find_ancestor(exp.Select) is select:
            relations[table.alias or table.name] = table.name
    return relations


def _subquery_blocks(
    ast: exp.Expression,
    catalog: Catalog | None,
    existing: list[QueryBlock],
) -> list[QueryBlock]:
    blocks = list(existing)
    known_selects = {block.block_id for block in blocks}
    index = 1
    for select in ast.find_all(exp.Select):
        if select is ast or any(
            block.block_id == select.alias for block in blocks if block.kind == "CTE"
        ):
            continue
        if select.find_ancestor(exp.CTE) is not None:
            continue
        block_id = f"subquery_{index}"
        while block_id in known_selects:
            index += 1
            block_id = f"subquery_{index}"
        known_selects.add(block_id)
        blocks.append(
            QueryBlock(
                block_id=block_id,
                kind="SUBQUERY",
                parent_id="main",
                tables={
                    physical_table
                    for relation, physical_table in _direct_relations(select).items()
                    if catalog is None or physical_table in catalog
                },
            )
        )
        index += 1
    return blocks


def _correlations(ast: exp.Expression, blocks: list[QueryBlock]) -> list[Correlation]:
    result: list[Correlation] = []
    selects: list[exp.Select] = []
    for subquery in ast.find_all(exp.Subquery):
        if isinstance(subquery.this, exp.Select):
            selects.append(subquery.this)
    for exists in ast.find_all(exp.Exists):
        if isinstance(exists.this, exp.Select):
            selects.append(exists.this)
    seen: set[int] = set()
    for index, select in enumerate(selects, start=1):
        if id(select) in seen:
            continue
        seen.add(id(select))
        local_tables = _direct_tables(select)
        scope_id = f"subquery_{index}"
        for comparison_type, operator in _PREDICATE_OPS.items():
            for comparison in select.find_all(comparison_type):
                if comparison.find_ancestor(exp.Select) is not select:
                    continue
                columns = list(comparison.find_all(exp.Column))
                if len(columns) < 2:
                    continue
                local = [column for column in columns if column.table in local_tables]
                outer = [column for column in columns if column.table not in local_tables]
                if local and outer:
                    result.append(
                        Correlation(
                            scope_id,
                            _column_name(local[0]),
                            _column_name(outer[0]),
                            operator,
                        )
                    )
    return result


def _set_operations(ast: exp.Expression) -> list[SetOperation]:
    result: list[SetOperation] = []
    for index, operation in enumerate(ast.find_all((exp.Union, exp.Intersect, exp.Except)), start=1):
        operator = operation.key.upper()
        if isinstance(operation, exp.Union) and not operation.args.get("distinct", True):
            operator = "UNION_ALL"
        result.append(SetOperation(operator, f"set_{index}_left", f"set_{index}_right"))
    return result


def _group_by(ast: exp.Expression) -> list[str]:
    result: list[str] = []
    for group in ast.find_all(exp.Group):
        for expression in group.expressions:
            result.extend(_columns(expression))
    return result


def _order_by(ast: exp.Expression) -> list[str]:
    result: list[str] = []
    for order in ast.find_all(exp.Order):
        for expression in order.expressions:
            result.extend(_columns(expression.this))
    return result


def _projections(ast: exp.Expression) -> list[str]:
    result: list[str] = []
    for select in ast.find_all(exp.Select):
        for expression in select.expressions:
            result.extend(_columns(expression))
    return result


def _windows(ast: exp.Expression) -> list[Window]:
    result: list[Window] = []
    for window in ast.find_all(exp.Window):
        function = window.this
        result.append(
            Window(
                func=function.key.upper(),
                partition_by=tuple(_columns(window.args.get("partition_by") or exp.Null())),
                order_by=tuple(_columns(window.args.get("order") or exp.Null())),
            )
        )
    return result


def extract_facts(
    query_id: str,
    ast: exp.Expression,
    catalog: Catalog | None = None,
) -> QueryFacts:
    """Extract Stage 2 facts from one qualified SQL expression."""
    blocks, lineage = _query_blocks(ast, catalog)
    blocks = _subquery_blocks(ast, catalog, blocks)
    return QueryFacts(
        query_id=query_id,
        tables=_tables(ast, catalog, _cte_names(ast)),
        join_edges=_join_edges(ast),
        aggregations=_aggregations(ast),
        group_by=_group_by(ast),
        predicates=_predicates(ast),
        projections=_projections(ast),
        order_by=_order_by(ast),
        window_fns=_windows(ast),
        query_blocks=blocks,
        column_lineage=lineage,
        correlations=_correlations(ast, blocks),
        set_operations=_set_operations(ast),
    )


def extract_corpus(
    queries: Iterable[object],
    catalog: Catalog | None = None,
) -> list[QueryFacts]:
    """Extract facts for objects exposing ``id`` and ``ast`` attributes."""
    return [extract_facts(query.id, query.ast, catalog) for query in queries]