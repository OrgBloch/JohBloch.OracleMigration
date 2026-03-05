from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class McpAnalysisResult:
    schema: str | None
    pattern: str | None
    tables: list[str]
    views: list[dict[str, Any]]
    domains: dict[str, list[str]]
    recommended_architecture: str
    join_view_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pattern": self.pattern,
            "tables": self.tables,
            "views": self.views,
            "domains": self.domains,
            "recommended_architecture": self.recommended_architecture,
            "join_view_count": self.join_view_count,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def infer_domains_from_tables(tables: list[str]) -> dict[str, list[str]]:
    """Infer a simple domain grouping from table names.

    This is intentionally heuristic and meant to provide an initial cut for planning.
    """

    keywords: list[tuple[str, tuple[str, ...]]] = [
        ("customer", ("customer", "cust", "client", "address", "contact")),
        ("order", ("order", "ord", "line", "item", "shipment", "delivery")),
        ("billing", ("invoice", "payment", "bill", "credit", "debit", "charge")),
        ("inventory", ("stock", "product", "sku", "warehouse", "inventory")),
        ("identity", ("user", "account", "role", "permission", "auth")),
    ]

    domains: dict[str, list[str]] = {name: [] for name, _ in keywords}
    domains["misc"] = []

    for t in tables:
        short = t.split(".")[-1].strip()
        key = short.lower()
        assigned = False
        for domain, words in keywords:
            if any(w in key for w in words):
                domains[domain].append(t)
                assigned = True
                break
        if not assigned:
            domains["misc"].append(t)

    # Drop empty domains for readability.
    return {k: v for k, v in domains.items() if v}


def recommend_architecture_from_views(views: list[dict[str, Any]]) -> tuple[str, int]:
    """Recommend architecture based on a simple heuristic.

    Heuristic (from conversation.md example):
    - If any view definition contains JOIN -> recommend EDA
    - Else -> recommend Microservices
    """

    join_views = 0
    for v in views:
        definition = v.get("DEFINITION") or v.get("definition") or ""
        if isinstance(definition, str) and "JOIN" in definition.upper():
            join_views += 1
    if join_views:
        return "EDA", join_views
    return "Microservices", 0


def write_analysis_outputs(result: McpAnalysisResult, out_dir: str | Path) -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    (out_path / "analysis.json").write_text(result.to_json() + "\n", encoding="utf-8")

    md_lines: list[str] = []
    md_lines.append("# MCP Analysis")
    md_lines.append("")
    if result.schema:
        md_lines.append(f"- Schema: {result.schema}")
    if result.pattern:
        md_lines.append(f"- Table pattern: {result.pattern}")
    md_lines.append(f"- Tables: {len(result.tables)}")
    md_lines.append(f"- Views (sampled): {len(result.views)}")
    md_lines.append(f"- Views containing JOIN: {result.join_view_count}")
    md_lines.append(f"- Recommended architecture: {result.recommended_architecture}")
    md_lines.append("")
    md_lines.append("## Domains (heuristic)")
    md_lines.append("")
    for domain in sorted(result.domains.keys(), key=str.casefold):
        tables = result.domains[domain]
        md_lines.append(f"### {domain} ({len(tables)})")
        for t in tables:
            md_lines.append(f"- {t}")
        md_lines.append("")

    (out_path / "analysis.md").write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
    return out_path
