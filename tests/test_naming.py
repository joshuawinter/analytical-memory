from dataclasses import dataclass

from semantic_induction.memory import MetricDefinition
from semantic_induction.models import JoinEdge, Predicate
from semantic_induction.naming import NamedDefinition, name_metric_definition


@dataclass
class _RecordingProvider:
    """Records the payload it was called with instead of calling a real model."""

    source: str = "stub"
    seen_object_id: str | None = None
    seen_structure: object = None

    def name(self, object_id: str, structure: object) -> NamedDefinition:
        self.seen_object_id = object_id
        self.seen_structure = structure
        return NamedDefinition(object_id, "Stub Name", "Stub description.", self.source)


def _definition(**overrides) -> MetricDefinition:
    base = dict(
        definition_id="metric:0:sum",
        concept_id="lineitem.l_extendedprice",
        measure=("SUM", "lineitem.l_extendedprice"),
        grain=("lineitem.l_returnflag",),
        join_path=(JoinEdge("lineitem.l_orderkey", "orders.o_orderkey", "INNER"),),
        default_filters=(Predicate("lineitem.l_shipdate", "LTE", "CAST('1998-09-02' AS DATE)"),),
        evidence_ids=("query:q1", "query:q2"),
        confidence=0.67,
        profile_notes=("return flag: 3 distinct values (observed: 'N', 'R', 'A')",),
    )
    base.update(overrides)
    return MetricDefinition(**base)


def test_name_metric_definition_sends_join_path_filters_and_profile_evidence():
    provider = _RecordingProvider()

    named = name_metric_definition(_definition(), provider)

    assert provider.seen_object_id == "metric:0:sum"
    payload = provider.seen_structure
    assert payload["measure"] == "lineitem.l_extendedprice"
    assert payload["aggregation"] == "SUM"
    assert payload["grain"] == ["lineitem.l_returnflag"]
    assert payload["join_path"] == ["lineitem.l_orderkey = orders.o_orderkey"]
    assert payload["invariant_filters"] == ["lineitem.l_shipdate LTE CAST('1998-09-02' AS DATE)"]
    assert payload["evidence_count"] == 2
    assert payload["confidence"] == 0.67
    assert payload["profile_notes"] == ["return flag: 3 distinct values (observed: 'N', 'R', 'A')"]
    assert named.name == "Stub Name"
    assert named.description == "Stub description."


def test_name_metric_definition_defaults_to_mock_provider_when_none_given():
    named = name_metric_definition(_definition())

    assert named.source == "mock"
    assert named.object_id == "metric:0:sum"
