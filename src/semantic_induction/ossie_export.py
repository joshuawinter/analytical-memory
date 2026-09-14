"""Export an induced SemanticLayer or AnalyticalMemory to Apache Ossie YAML format."""
from __future__ import annotations

import re
from typing import Any

from semantic_induction.memory import AnalyticalMemory
from semantic_induction.models import Catalog, JoinEdge, Metric, SemanticLayer


def _map_datatype(type_str: str) -> str:
    t = type_str.upper()
    if any(k in t for k in ("INT", "BIGINT", "SMALLINT", "TINYINT", "INTEGER")):
        return "Integer"
    if any(k in t for k in ("DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL")):
        return "Decimal"
    if any(k in t for k in ("DATE", "TIME", "TIMESTAMP")):
        return "Date" if "DATE" in t else "Timestamp"
    if any(k in t for k in ("BOOL", "BOOLEAN")):
        return "Boolean"
    return "String"


def _clean_identifier(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower()).strip("_")
    return cleaned or "metric"


def _dump_yaml(data: Any, indent_level: int = 0) -> str:
    """Deterministic, dependency-free YAML serializer supporting nested dicts/lists."""
    indent = "  " * indent_level
    if data is None:
        return "null"
    if isinstance(data, bool):
        return "true" if data else "false"
    if isinstance(data, (int, float)):
        return str(data)
    if isinstance(data, str):
        if not data:
            return '""'
        if "\n" in data:
            lines = data.strip().splitlines()
            return "|\n" + "\n".join("  " * (indent_level + 1) + line for line in lines)
        if any(c in data for c in (":", "#", "[", "]", "{", "}", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`", '"', "'")):
            escaped = data.replace('"', '\\"')
            return f'"{escaped}"'
        return data

    if isinstance(data, list):
        if not data:
            return "[]"
        # If simple flat primitives list (like column lists [a, b]), format inline if short
        if all(isinstance(x, (str, int, float, bool)) for x in data) and len(data) <= 3 and sum(len(str(x)) for x in data) < 40:
            items = ", ".join(_dump_yaml(x, 0) for x in data)
            return f"[{items}]"
        lines = []
        for item in data:
            if isinstance(item, dict):
                item_yaml = _dump_yaml(item, indent_level + 1).lstrip()
                lines.append(f"{indent}- {item_yaml}")
            else:
                lines.append(f"{indent}- {_dump_yaml(item, indent_level + 1)}")
        return "\n".join(lines)

    if isinstance(data, dict):
        if not data:
            return "{}"
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)) and value:
                # Check if it's an inline list
                rendered = _dump_yaml(value, indent_level + 1)
                if rendered.startswith("["):
                    lines.append(f"{indent}{key}: {rendered}")
                else:
                    lines.append(f"{indent}{key}:\n{rendered}")
            else:
                lines.append(f"{indent}{key}: {_dump_yaml(value, indent_level + 1)}")
        return "\n".join(lines)

    return str(data)


def to_ossie_dict(
    layer: SemanticLayer,
    catalog: Catalog,
    model_name: str = "induced_semantic_model",
    memory: AnalyticalMemory | None = None,
) -> dict[str, Any]:
    """Convert a SemanticLayer (and optional AnalyticalMemory) to an Apache Ossie model dictionary."""
    datasets: list[dict[str, Any]] = []

    # 1. Build datasets from catalog and induced entities
    for table_name, columns in sorted(catalog.items()):
        entity = layer.entities.get(table_name)
        pk = list(entity.grain) if entity and entity.grain else []
        if not pk:
            for col in columns:
                if col.endswith("_key") or col.endswith("_id") or col.endswith("_sk"):
                    pk = [col]
                    break

        fields: list[dict[str, Any]] = []
        for col_name, col_type in sorted(columns.items()):
            full_col = f"{table_name}.{col_name}"
            dtype = _map_datatype(col_type)
            is_dim = full_col in layer.dimensions or dtype in ("Date", "Timestamp")
            field_dict: dict[str, Any] = {
                "name": col_name,
                "expression": {
                    "dialects": [
                        {"dialect": "ANSI_SQL", "expression": col_name}
                    ]
                },
                "datatype": dtype,
            }
            if is_dim:
                field_dict["dimension"] = {
                    "is_time": dtype in ("Date", "Timestamp")
                }

            # Add synonyms if known in memory
            if memory and full_col in memory.concepts:
                concept = memory.concepts[full_col]
                if concept.aliases:
                    field_dict["ai_context"] = {"synonyms": list(concept.aliases)}

            fields.append(field_dict)

        dataset_dict: dict[str, Any] = {
            "name": table_name,
            "source": table_name,
            "fields": fields,
        }
        if pk:
            dataset_dict["primary_key"] = pk
            dataset_dict["unique_keys"] = [pk]
        datasets.append(dataset_dict)

    # 2. Build relationships from unique join edges
    relationships: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()
    for metric in layer.metrics:
        for edge in metric.join_path:
            left_table, left_col = edge.left.split(".", 1)
            right_table, right_col = edge.right.split(".", 1)
            edge_key = (f"{left_table}.{left_col}", f"{right_table}.{right_col}")
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            rel_name = f"{left_table}_to_{right_table}_{left_col}"
            relationships.append({
                "name": rel_name,
                "from": left_table,
                "to": right_table,
                "from_columns": [left_col],
                "to_columns": [right_col],
                "ai_context": {
                    "synonyms": [f"{left_table} {right_table} join"]
                },
            })

    # 3. Build metrics from induced layer measures and metrics
    metrics: list[dict[str, Any]] = []
    seen_measures: set[tuple[str, str]] = set()
    for (agg, col), measure in sorted(layer.measures.items(), key=lambda item: item[0]):
        if (agg, col) in seen_measures:
            continue
        seen_measures.add((agg, col))

        table, col_name = col.split(".", 1) if "." in col else ("", col)
        metric_name = _clean_identifier(f"{agg}_{col_name}" if col_name != "*" else f"{agg}_all_{table}")
        expr_sql = f"{agg}({col})" if col != "*" else f"{agg}(*)"
        
        m_dict: dict[str, Any] = {
            "name": metric_name,
            "expression": {
                "dialects": [
                    {"dialect": "ANSI_SQL", "expression": expr_sql}
                ]
            },
            "description": f"Induced {agg} metric over {col} with support {measure.support}",
            "datatype": "Decimal" if agg in ("SUM", "AVG") else "Integer",
        }
        if memory and col in memory.concepts:
            concept = memory.concepts[col]
            synonyms = list(concept.aliases)
            if concept.preferred_label:
                synonyms.insert(0, concept.preferred_label.lower())
            if synonyms:
                m_dict["ai_context"] = {"synonyms": synonyms}
        metrics.append(m_dict)

    ossie_doc: dict[str, Any] = {
        "version": "0.2.0",
        "semantic_model": [
            {
                "name": model_name,
                "description": f"Auto-induced semantic model '{model_name}' generated from query exhaust",
                "ai_context": {
                    "instructions": f"Auto-induced semantic model containing {len(datasets)} datasets and {len(metrics)} metrics."
                },
                "datasets": datasets,
                "relationships": relationships,
                "metrics": metrics,
            }
        ],
    }
    return ossie_doc


def export_ossie_yaml(
    layer: SemanticLayer,
    catalog: Catalog,
    model_name: str = "induced_semantic_model",
    memory: AnalyticalMemory | None = None,
) -> str:
    """Export an induced SemanticLayer to Apache Ossie YAML text."""
    doc = to_ossie_dict(layer, catalog, model_name=model_name, memory=memory)
    return _dump_yaml(doc) + "\n"
