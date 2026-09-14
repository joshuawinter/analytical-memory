from pathlib import Path

from semantic_induction.aggregate import aggregate
from semantic_induction.extract import extract_corpus
from semantic_induction.induce import induce
from semantic_induction.ingest import ingest
from semantic_induction.models import (
    Catalog,
    Dimension,
    Entity,
    JoinEdge,
    Measure,
    Metric,
    SemanticLayer,
)
from semantic_induction.ossie_export import export_ossie_yaml, to_ossie_dict

ROOT = Path(__file__).parents[1]


def test_ossie_export_synthetic_model():
    catalog: Catalog = {
        "orders": {"order_id": "INTEGER", "amount": "DECIMAL(10,2)", "order_date": "DATE"},
        "customer": {"customer_id": "INTEGER", "name": "VARCHAR"},
    }
    layer = SemanticLayer(
        entities={"orders": Entity("orders", "FACT", ("order_id",)), "customer": Entity("customer", "DIM", ("customer_id",))},
        measures={("SUM", "orders.amount"): Measure("orders.amount", "SUM", 5)},
        dimensions={"orders.order_date": Dimension("orders.order_date", 5)},
        metrics=[
            Metric(
                measure=("SUM", "orders.amount"),
                grain=frozenset({"customer.customer_id"}),
                join_path=(JoinEdge("orders.customer_id", "customer.customer_id", "INNER"),),
                default_filters=(),
                support=5,
                seen_in=("q1",),
            )
        ],
    )

    doc = to_ossie_dict(layer, catalog, model_name="test_model")
    assert doc["version"] == "0.2.0"
    model = doc["semantic_model"][0]
    assert model["name"] == "test_model"
    assert len(model["datasets"]) == 2
    assert len(model["relationships"]) == 1
    assert model["relationships"][0]["from"] == "orders"
    assert model["relationships"][0]["to"] == "customer"
    assert len(model["metrics"]) == 1
    assert model["metrics"][0]["name"] == "sum_amount"
    assert model["metrics"][0]["expression"]["dialects"][0]["expression"] == "SUM(orders.amount)"

    yaml_text = export_ossie_yaml(layer, catalog, model_name="test_model")
    assert "version: 0.2.0" in yaml_text
    assert "name: test_model" in yaml_text
    assert "name: orders" in yaml_text
    assert "expression: SUM(orders.amount)" in yaml_text


def test_ossie_export_tpch_corpus():
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    facts = extract_corpus(queries, catalog)
    stats = aggregate(facts)
    layer = induce(stats, catalog, facts, min_support=1)

    yaml_text = export_ossie_yaml(layer, catalog, model_name="tpch_model")
    assert "version: 0.2.0" in yaml_text
    assert "name: lineitem" in yaml_text
    assert "name: orders" in yaml_text
    assert "name: sum_l_extendedprice" in yaml_text
    assert "name: lineitem_to_orders_l_orderkey" in yaml_text


def test_tpcds_ossie_induction_conformance():
    """Induce semantic layer from 99 TPC-DS query templates and compare to Apache Ossie spec."""
    catalog, queries = ingest(ROOT / "data/tpcds/ddl.sql", ROOT / "data/tpcds/queries")
    facts = extract_corpus(queries, catalog)
    stats = aggregate(facts)
    layer = induce(stats, catalog, facts, min_support=1)

    ossie_doc = to_ossie_dict(layer, catalog, model_name="tpcds_retail_model")
    model = ossie_doc["semantic_model"][0]

    dataset_names = {d["name"] for d in model["datasets"]}
    # Key core TPC-DS tables present in Apache Ossie's tpcds_semantic_model.yaml
    expected_core_datasets = {"store_sales", "date_dim", "customer", "item", "store"}
    assert expected_core_datasets.issubset(dataset_names)

    # Key metric expressions in Apache Ossie's tpcds_semantic_model.yaml:
    # 1. total_sales -> SUM(store_sales.ss_ext_sales_price)
    # 2. total_profit -> SUM(store_sales.ss_net_profit)
    metric_expressions = {
        m["expression"]["dialects"][0]["expression"] for m in model["metrics"]
    }
    assert "SUM(store_sales.ss_ext_sales_price)" in metric_expressions
    assert "SUM(store_sales.ss_net_profit)" in metric_expressions

    # Key relationships in Apache Ossie's tpcds_semantic_model.yaml:
    # store_sales -> date_dim (ss_sold_date_sk = d_date_sk)
    # store_sales -> item (ss_item_sk = i_item_sk)
    # store_sales -> customer (ss_customer_sk = c_customer_sk)
    # store_sales -> store (ss_store_sk = s_store_sk)
    rel_tuples = {
        (r["from"], r["to"], tuple(r["from_columns"]), tuple(r["to_columns"]))
        for r in model["relationships"]
    }
    assert ("store_sales", "date_dim", ("ss_sold_date_sk",), ("d_date_sk",)) in rel_tuples or \
           ("date_dim", "store_sales", ("d_date_sk",), ("ss_sold_date_sk",)) in rel_tuples

    yaml_text = export_ossie_yaml(layer, catalog, model_name="tpcds_retail_model")
    assert "name: tpcds_retail_model" in yaml_text
    assert "name: store_sales" in yaml_text
    assert "SUM(store_sales.ss_ext_sales_price)" in yaml_text
