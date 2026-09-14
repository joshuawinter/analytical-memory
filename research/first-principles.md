# First-Principles Notes

Status: working reasoning, not externally sourced. Related architecture: [analytical memory target model](../docs/ARCHITECTURE.md#analytical-memory-target-model), [human review boundary](../docs/ARCHITECTURE.md#human-review-boundary).

## 1. Business meaning is operational

Enterprise semantics are not only definitions written in catalogs. They are also encoded in repeated choices: joins, grains, filters, date bases, exclusions, and report usage.

## 2. Usage is evidence, not truth

A query demonstrates that someone used an interpretation. It does not prove that the interpretation is correct or normative. Therefore the system must preserve:

```text
observed fact != inferred interpretation != approved definition
```

## 3. Data validates plausibility

Profiles, samples, uniqueness, cardinality, and execution results can reject mechanically unsafe interpretations. They cannot determine business intent by themselves.

## 4. Humans resolve normative meaning

The system should automate mechanical checks and route ambiguity, conflicts, scope, ownership, and policy to human reviewers. A decision needs rationale, provenance, owner, and validity period.

## 5. Trust requires repeatability and explanation

A useful analytical answer must be reproducible and inspectable:

```text
question -> selected definition -> evidence -> plan -> SQL -> result -> finding
```

## 6. The durable product is a feedback loop

The system improves when approved and rejected interpretations become memory. Each investigation should leave behind evidence, assumptions, results, and feedback that can influence later retrieval and review.

## 7. Product boundary

The project should discover, reconcile, audit, and publish enterprise semantics. Existing BI and semantic platforms can remain the serving and experience layers.

## 8. Interaction requirement versus metaphor

The product requirement is efficient expert feedback that improves the agent.
Specific interaction language, such as swipe left/right, is a design metaphor
or hypothesis until validated with users. Preserve the feedback contract while
leaving the interaction pattern open.

## 9. Resource discipline

The first meaningful experiment should be local-first and deterministic. API
calls are reserved for targeted language generation or evaluation, not data
generation, SQL validation, or routine evidence processing. A local GPU may
support embeddings, reranking, batch paraphrases, or small-model inference;
adding GPU complexity is justified only when it reduces external spend or
improves the experiment materially.

## 10. Focused enterprise-like experiment

Start with order-to-cash and fulfillment: customer, product, warehouse, sales
order, order line, order event, and inventory snapshot. Inject one known
operational change, such as warehouse stockouts causing an on-time-in-full
decline, and evaluate whether the system can recover the definition, obtain
expert approval, investigate the change, and cite evidence without confusing
observed behavior with normative truth.
