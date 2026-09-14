from semantic_induction.integration import IntegrationWorkflow
from semantic_induction.models import (
    BusinessKeyMapping,
    DataQualityOutcome,
    LoadBatch,
    MappingRule,
    TargetRowVersion,
    TemporalPolicy,
)


def test_integration_workflow_preserves_tpc_di_evidence():
    workflow = IntegrationWorkflow(
        workflow_id="customer_incremental",
        mappings=[
            MappingRule(
                rule_id="customer_name",
                source_attributes=("crm.customer.name",),
                target_attribute="dim_customer.customer_name",
                expression="TRIM(name)",
            )
        ],
        key_mappings=[
            BusinessKeyMapping(
                source_key=("crm.customer.customer_id",),
                target_entity="dim_customer",
                target_surrogate_key="customer_sk",
                lookup_policy="EXISTING",
            )
        ],
        temporal_policies=[
            TemporalPolicy(
                target_entity="dim_customer",
                business_key=("customer_id",),
                effective_start="valid_from",
                effective_end="valid_to",
            )
        ],
        batches=[LoadBatch("batch-001", "crm", "COMPLETED")],
        quality_outcomes=[
            DataQualityOutcome("required_name", "source-7", "REJECTED", "missing")
        ],
        target_versions=[
            TargetRowVersion(
                "dim_customer", "42", ("customer-7",), "2026-01-01", None, True, "batch-001"
            )
        ],
    )

    assert workflow.mappings[0].operation == "MAP"
    assert workflow.key_mappings[0].lookup_policy == "EXISTING"
    assert workflow.temporal_policies[0].history_type == "SCD2"
    assert workflow.quality_outcomes[0].disposition == "REJECTED"
    assert workflow.target_versions[0].current is True