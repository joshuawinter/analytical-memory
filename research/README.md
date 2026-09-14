# Research Index

This directory contains external evidence and analysis supporting the enterprise semantic discovery and governance thesis.

## Working rules

- Preserve downloaded primary sources unchanged.
- Prefer a one-paragraph summary plus a stable source link; do not download a
	source unless local extraction or offline access is necessary.
- Give each source a stable ID such as `SRC-001`.
- Separate sourced claims from our interpretation.
- Cite sources inline as `[SRC-001, p. 3]` for PDFs or `[SRC-002]` for web sources.
- Record access dates for web sources.
- Use research notes to sharpen goals and positioning; do not silently turn hypotheses into product requirements.

## Sources

| ID | Source | Type | Local artifact / URL | Relevance |
|---|---|---|---|---|
| SRC-001 | TDWI & AtScale, *Building a Trusted Semantic Foundation for Generative BI*, sponsored viewpoint, 2026 | Web / Report | https://www.atscale.com/resource/trusted-semantic-foundation-generative-bi/ | Governed semantic foundations, deterministic query paths, ownership, evaluation, explainability, and security |
| SRC-002 | NVIDIA, *How Kumo Relational Works* | Web | https://docs.nvidia.com/sdgm/rfm/introduction | Relational foundation models and prediction over relational context |
| SRC-003 | dbt, *Semantic models* | Web | https://docs.getdbt.com/docs/build/semantic-models | Open semantic model structure: entities, dimensions, metrics, and relationships |
| SRC-004 | Cube, *Agentic analytics platform* | Web | https://cube.dev/product | Governed semantic context for AI agents and BI |
| SRC-005 | Google Cloud, *Looker* | Web | https://cloud.google.com/looker | LookML semantic modeling and conversational/agentic BI |
| SRC-006 | ThoughtSpot, *Modern Analytics Cloud* | Web | https://www.thoughtspot.com/product | Search, automated insights, governed models, and analytics agents |
| SRC-007 | Apache Ossie, incubating | Web | https://github.com/apache/ossie | Vendor-neutral semantic model exchange across BI and AI tools |
| SRC-008 | W3C, *PROV-O: The PROV Ontology* | Web | https://www.w3.org/TR/prov-o/ | Provenance, evidence, derivation, agents, activities, and resolutions |
| SRC-009 | W3C, *SKOS Simple Knowledge Organization System* | Web | https://www.w3.org/TR/skos-reference/ | Concepts, aliases, broader/narrower terms, and taxonomies |
| SRC-010 | Anthropic, *Model Context Protocol* | Web | https://modelcontextprotocol.io/ | Standard agent-facing resources, tools, and prompts interface |

All sources are cited by reference and URL without storing local binary artifacts.

## Note template

```markdown
### [SRC-NNN] Title

Summary: One paragraph stating the relevant claim, why it matters, and any
limits or uncertainty.

Source: https://example.com/source
Accessed: YYYY-MM-DD
Architecture relevance: [section](../docs/ARCHITECTURE.md#section-anchor)
```

## Notes

- [Marketplace landscape](marketplace.md)
- [Competitor matrix](competitors.md)
- [First principles](first-principles.md)
- [MCP integration](mcp.md)

## Architecture links

- [Project architecture](../docs/ARCHITECTURE.md)
- [Analytical memory target model](../docs/ARCHITECTURE.md#analytical-memory-target-model)
- [Scope lock and next build order](../docs/ARCHITECTURE.md#scope-lock-and-next-build-order)
