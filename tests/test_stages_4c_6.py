from datetime import datetime, timezone
from pathlib import Path

import duckdb

from semantic_induction.conflicts import detect_conflicts
from semantic_induction.models import Agg, Entity, Predicate, QueryFacts, Ruling, SemanticLayer
from semantic_induction.naming import AnthropicNamingProvider, MockNamingProvider, name_layer
from semantic_induction.resolution import ResolutionStore, conflict_id
from semantic_induction.validate import validate_query


def test_resolution_store_is_versioned(tmp_path):
    conflict = detect_conflicts(
        SemanticLayer(),
        [
            QueryFacts("a", aggregations=[Agg("SUM", "orders.amount")]),
            QueryFacts(
                "b",
                aggregations=[Agg("SUM", "orders.amount")],
                predicates=[Predicate("orders.status", "EQ", "'COMPLETE'")],
            ),
        ],
    )[0]
    path = tmp_path / "rulings.json"
    store = ResolutionStore(path)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.add(Ruling(conflict_id(conflict), "chosen-a", "Use the complete order definition.", True, "analyst", now, now))

    assert ResolutionStore(path).resolve(conflict, now).chosen == "chosen-a"


def test_mock_naming_does_not_change_structure():
    layer = SemanticLayer(entities={"orders": Entity("orders", "FACT")})

    name_layer(layer, MockNamingProvider())

    assert layer.entities["orders"].kind == "FACT"
    assert layer.names["orders"].source == "mock"


def test_anthropic_naming_provider_uses_structured_response():
    class Messages:
        def create(self, **request):
            assert request["model"] == "test-model"
            assert request["max_tokens"] == 256
            return type("Response", (), {"content": [type("Block", (), {"text": '{"name":"Orders","description":"Customer orders."}'})()]})()

    class Client:
        messages = Messages()

    config = type("Config", (), {"model": "test-model", "api_key": "placeholder", "api_key_env": "TEST_KEY"})()
    provider = AnthropicNamingProvider(config=config, client=Client())

    definition = provider.name("orders", Entity("orders", "FACT"))

    assert definition.name == "Orders"
    assert definition.source == "anthropic:test-model"


def test_anthropic_naming_provider_accepts_json_code_fence():
    class Messages:
        def create(self, **request):
            response_text = '```json\n{"name":"Orders","description":"Customer orders."}\n```'
            return type("Response", (), {"content": [type("Block", (), {"text": response_text})()]})()

    class Client:
        messages = Messages()

    config = type("Config", (), {"model": "test-model", "api_key": "placeholder", "api_key_env": "TEST_KEY"})()
    definition = AnthropicNamingProvider(config=config, client=Client()).name(
        "orders", Entity("orders", "FACT")
    )

    assert definition.description == "Customer orders."


def test_validation_compares_duckdb_result_to_csv(tmp_path):
    database = tmp_path / "test.duckdb"
    query = tmp_path / "q01.sql"
    answer = tmp_path / "q01.csv"
    connection = duckdb.connect(str(database))
    connection.execute("CREATE TABLE values_table(value INTEGER)")
    connection.execute("INSERT INTO values_table VALUES (2), (1)")
    connection.close()
    query.write_text("SELECT value FROM values_table ORDER BY value", encoding="utf-8")
    answer.write_text("value\n1\n2\n", encoding="utf-8")

    result = validate_query(duckdb.connect(str(database), read_only=True), query, answer)

    assert result.match is True


def test_validation_handles_nulls_and_commas(tmp_path):
    database = tmp_path / "special.duckdb"
    query = tmp_path / "q02.sql"
    answer = tmp_path / "q02.csv"
    connection = duckdb.connect(str(database))
    connection.execute("CREATE TABLE values_table(label VARCHAR, value INTEGER)")
    connection.execute("INSERT INTO values_table VALUES ('a,b', NULL)")
    connection.close()
    query.write_text("SELECT label, value FROM values_table", encoding="utf-8")
    answer.write_text('label,value\n"a,b",\n', encoding="utf-8")

    result = validate_query(duckdb.connect(str(database), read_only=True), query, answer)

    assert result.match is True
    assert result.execution_ms is not None