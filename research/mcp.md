# Model Context Protocol Integration

Status: working analysis, 2026-09-13. Related architecture: [agent interface boundary](../docs/ARCHITECTURE.md#agent-interface-boundary).

Summary: MCP should be the corporate-agent interface to the analytical memory
and investigation service, exposing governed resources, tools, and workflow
prompts. It should not own metric definitions, provenance, approvals, policy,
or unrestricted SQL execution. The MVP can expose memory search, review
candidates, and approved investigations through MCP while the browser and CLI
use the same application service. This makes the platform consumable by
multiple agents without confusing the protocol with the corporate intelligence
system itself.

Source: https://modelcontextprotocol.io/

Accessed: 2026-09-13

Architecture relevance: [agent interface boundary](../docs/ARCHITECTURE.md#agent-interface-boundary), [analytical memory target model](../docs/ARCHITECTURE.md#analytical-memory-target-model)

## MVP boundary

```text
analytical memory -> InvestigationService -> browser / CLI / MCP -> agents
```

Initial MCP capabilities:

```text
search_business_memory(question)
get_review_candidates()
run_approved_investigation(question)
```

The approval gate is mandatory. No approved definition means `NEEDS_REVIEW`;
multiple approved definitions mean `AMBIGUOUS`. The MCP adapter must not bypass
these outcomes with arbitrary SQL.