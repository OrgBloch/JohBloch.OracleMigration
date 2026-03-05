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
    object_counts: dict[str, int]
    plsql_objects: list[dict[str, str]]
    warnings: list[dict[str, Any]]
    domains: dict[str, list[str]]
    recommended_architecture: str
    join_view_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pattern": self.pattern,
            "tables": self.tables,
            "views": self.views,
            "object_counts": self.object_counts,
            "plsql_objects": self.plsql_objects,
            "warnings": self.warnings,
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
    if result.object_counts:
        md_lines.append("")
        md_lines.append("## Object counts")
        md_lines.append("")
        for k in sorted(result.object_counts.keys(), key=str.casefold):
            md_lines.append(f"- {k}: {result.object_counts[k]}")
    if result.plsql_objects:
        md_lines.append("")
        md_lines.append("## PL/SQL objects (sample)")
        md_lines.append("")
        for obj in result.plsql_objects:
            otype = obj.get("object_type") or obj.get("OBJECT_TYPE") or ""
            oname = obj.get("object_name") or obj.get("OBJECT_NAME") or ""
            owner = obj.get("owner") or obj.get("OWNER") or ""
            label = f"{owner}.{oname}" if owner else oname
            md_lines.append(f"- {otype}: {label}")

    if result.warnings:
        md_lines.append("")
        md_lines.append("## Warnings")
        md_lines.append("")
        md_lines.append(f"Count: {len(result.warnings)}")
        md_lines.append("")
        for w in result.warnings[:50]:
            code = w.get("code", "warning")
            message = w.get("message", "")
            md_lines.append(f"- {code}: {message}")
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


def generate_architecture(domains: dict[str, list[str]], style: str) -> dict[str, Any]:
    style_l = (style or "").strip().lower()
    if style_l == "eda":
        return {
            "style": "EDA",
            "services": sorted(domains.keys(), key=str.casefold),
            "events": ["CustomerCreated", "OrderPlaced", "StockAdjusted"],
        }
    if style_l == "microservices":
        return {
            "style": "Microservices",
            "services": sorted(domains.keys(), key=str.casefold),
        }
    return {"style": style or "Unknown", "services": sorted(domains.keys(), key=str.casefold)}


def create_best_practice_structure(
    out_dir: str | Path,
    *,
    domains: dict[str, list[str]],
    architecture: str,
    language: str,
) -> Path:
    """Create a best-practice output folder structure under out_dir.

    This only creates folders; file generation is handled elsewhere.
    """

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    lang = (language or "").strip().lower()
    arch = (architecture or "").strip().lower()

    if lang == "python":
        if arch == "eda":
            per_domain = ["domain", "events", "projections", "repositories"]
        else:
            per_domain = ["domain", "api", "infrastructure"]
    else:
        # Keep it minimal for now (stubs can be expanded later).
        per_domain = ["domain", "api", "infrastructure"]

    for domain in sorted(domains.keys(), key=str.casefold):
        domain_path = out_path / domain
        domain_path.mkdir(exist_ok=True)
        for folder in per_domain:
            (domain_path / folder).mkdir(exist_ok=True)

    return out_path
