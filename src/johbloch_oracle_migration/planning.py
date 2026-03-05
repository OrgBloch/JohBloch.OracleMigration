from __future__ import annotations

from dataclasses import dataclass

from .oracle_sql import OracleSqlInventory


@dataclass(frozen=True)
class MigrationPlanOptions:
    source: str = "Oracle"
    target: str = "PostgreSQL"


def generate_migration_plan_markdown(
    inventory: OracleSqlInventory,
    *,
    options: MigrationPlanOptions | None = None,
) -> str:
    opts = options or MigrationPlanOptions()

    lines: list[str] = []
    lines.append(f"# Migration Plan: {opts.source} → {opts.target}")
    lines.append("")
    lines.append("## Inventory")
    lines.append("")
    lines.append(f"- Tables: {len(inventory.tables)}")
    lines.append(f"- Sequences: {len(inventory.sequences)}")
    lines.append(f"- Views: {len(inventory.views)}")
    lines.append(f"- Triggers: {len(inventory.triggers)}")
    lines.append(f"- Procedures: {len(inventory.procedures)}")
    lines.append(f"- Functions: {len(inventory.functions)}")
    lines.append(f"- Packages: {len(inventory.packages)}")
    lines.append("")

    lines.append("## Steps")
    lines.append("")
    lines.append("1. **Scope & success criteria**")
    lines.append("   - Define which schemas/modules are in scope")
    lines.append("   - Define ‘done’: build passes, key flows validated, performance baselines")
    lines.append("")
    lines.append("2. **Schema conversion (DDL)**")
    lines.append("   - Convert Oracle DDL to target DDL")
    lines.append("   - Review types, constraints, indexes, sequences")
    lines.append("   - Flag unsupported constructs (PL/SQL, packages, advanced triggers)")
    lines.append("")
    lines.append("3. **Data migration**")
    lines.append("   - Decide strategy: logical export/import vs. replication")
    lines.append("   - Validate row counts, NULL semantics, date/time semantics")
    lines.append("")
    lines.append("4. **Application changes**")
    lines.append("   - Replace Oracle-specific SQL, functions, hints")
    lines.append("   - Update drivers, connection pooling, and parameter binding")
    lines.append("")
    lines.append("5. **Testing & validation**")
    lines.append("   - Unit tests for data-access components")
    lines.append("   - Integration tests for critical queries")
    lines.append("   - Performance checks on top queries")
    lines.append("")
    lines.append("6. **Cutover plan**")
    lines.append("   - Backout strategy")
    lines.append("   - Freeze window and final sync")
    lines.append("   - Post-cutover monitoring")
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    if inventory.packages or inventory.procedures or inventory.functions:
        lines.append(
            "- Detected PL/SQL objects (procedures/functions/packages). "
            "Expect manual conversion (e.g. to PL/pgSQL) or redesign."
        )
    if inventory.triggers:
        lines.append(
            "- Triggers detected. Verify timing/semantics and re-implement in target DB."
        )

    return "\n".join(lines) + "\n"
