from pathlib import Path
from decimal import Decimal

import duckdb

from semantic_induction.compile import compile_metric, compile_metric_report, compile_metrics
from semantic_induction.models import Metric, Predicate


ROOT = Path(__file__).parents[1]


def test_compiles_and_executes_grouped_metric():
    catalog = {"lineitem": {"l_quantity": "DECIMAL", "l_returnflag": "VARCHAR"}}
    metric = Metric(
        measure=("SUM", "lineitem.l_quantity"),
        grain=frozenset({"lineitem.l_returnflag"}),
        join_path=(),
        default_filters=(Predicate("lineitem.l_returnflag", "IN", "('A', 'N')"),),
        support=1,
        seen_in=("q01",),
    )
    connection = duckdb.connect()
    connection.execute("CREATE TABLE lineitem(l_quantity DECIMAL(15, 2), l_returnflag VARCHAR)")
    connection.execute("INSERT INTO lineitem VALUES (10, 'A'), (20, 'N'), (30, 'R')")

    result = connection.execute(compile_metric(metric, catalog)).fetchall()

    assert result == [(Decimal("10.00"), "A"), (Decimal("20.00"), "N")]


def test_compilation_reports_unsupported_metrics_without_stopping():
    catalog = {"lineitem": {"l_quantity": "DECIMAL"}}
    supported = Metric(("SUM", "lineitem.l_quantity"), frozenset(), (), (), 1, ("q01",))
    unsupported = Metric(("STDDEV", "lineitem.l_quantity"), frozenset(), (), (), 1, ("q02",))

    report = compile_metrics([supported, unsupported], catalog)

    assert report.total == 2
    assert report.compiled == 1
    assert report.unsupported == 1
    assert compile_metric_report(unsupported, catalog).rejection_reason == "unsupported aggregate: STDDEV"