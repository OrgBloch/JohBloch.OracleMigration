from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from .mcp_setup import OracleMcpConfig, docker_mcp_setup_oracle
from .mcp_analysis import (
    McpAnalysisResult,
    create_best_practice_structure,
    generate_architecture,
    infer_domains_from_tables,
    recommend_architecture_from_views,
    write_analysis_outputs,
)
from .plsql_convert import convert_plsql_to_language
from .oracle_mcp import OracleMcp, OracleMcpConnection


def _write_claude_outputs(
    *,
    out_dir: Path,
    analysis: dict,
    raw_response: dict,
) -> None:
    import json

    (out_dir / "claude_analysis.json").write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "claude_response.json").write_text(
        json.dumps(raw_response, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    md: list[str] = []
    md.append("# Claude Analysis")
    md.append("")
    domains = analysis.get("domains")
    if isinstance(domains, list):
        md.append(f"Domains: {len(domains)}")
        md.append("")
        for d in domains:
            if not isinstance(d, dict):
                continue
            name = d.get("name")
            desc = d.get("description")
            md.append(f"## {name}")
            if desc:
                md.append(str(desc))
            tables = d.get("tables")
            if isinstance(tables, list) and tables:
                md.append("")
                md.append("Tables:")
                for t in tables[:50]:
                    md.append(f"- {t}")
            events = d.get("events")
            if isinstance(events, list) and events:
                md.append("")
                md.append("Events:")
                for e in events[:50]:
                    md.append(f"- {e}")
            md.append("")
    notes = analysis.get("notes")
    if isinstance(notes, list) and notes:
        md.append("## Notes")
        md.append("")
        for n in notes[:50]:
            md.append(f"- {n}")
        md.append("")

    (out_dir / "claude_analysis.md").write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")


def _write_background_job_prompts(*, out_dir: Path) -> None:
    jobs_dir = out_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    # These prompts are intended to be run as background jobs (separately), using Claude.
    micro_prompt = """You are Claude, trained in DDD and microservices.

Given the file claude_analysis.json, generate a best-practice Python microservices code skeleton.

Constraints:
- Use the inferred bounded contexts (domains) as service boundaries.
- Write files under: generated/microservices/<domain>/{domain,api,infrastructure}
- Keep it minimal: domain models + service class + repository interface + API stub.
- Do not connect to real databases. Create placeholders.

Inputs:
- generated/claude_analysis.json
- generated/analysis.json (heuristic inventory)

Output:
- Create/overwrite files under generated/microservices/...
""".strip() + "\n"

    eda_prompt = """You are Claude, trained in DDD and Event-Driven Architecture.

Given the file claude_analysis.json, generate a best-practice Python EDA code skeleton.

Constraints:
- Use the inferred bounded contexts (domains) as service boundaries.
- Write files under: generated/eda/<domain>/{domain,events,projections,repositories}
- Keep it minimal: event definitions + producer/handler stubs + projection stubs.
- Do not connect to real message brokers. Create placeholders.

Inputs:
- generated/claude_analysis.json
- generated/analysis.json (heuristic inventory)

Output:
- Create/overwrite files under generated/eda/...
""".strip() + "\n"

    (jobs_dir / "microservices.prompt.md").write_text(micro_prompt, encoding="utf-8")
    (jobs_dir / "eda.prompt.md").write_text(eda_prompt, encoding="utf-8")

    import json

    (jobs_dir / "jobs.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {"name": "generate_microservices_skeleton", "prompt_file": "microservices.prompt.md"},
                    {"name": "generate_eda_skeleton", "prompt_file": "eda.prompt.md"},
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def cmd_mcp_setup(args: argparse.Namespace) -> int:
    connection_string = args.connection_string or input("Oracle connection string (host:port/service): ").strip()
    user = args.user or input("Oracle user: ").strip()

    if not connection_string or not user:
        raise SystemExit("connection string and user are required")

    if args.password_stdin:
        password = sys.stdin.read().strip()
    elif args.password_env:
        password = os.environ.get(args.password_env, "").strip()
    else:
        password = getpass.getpass("Oracle password (stored in Docker MCP secrets): ")
    if not password:
        raise SystemExit("password is required")

    docker_mcp_setup_oracle(OracleMcpConfig(connection_string=connection_string, user=user), password)
    print("Oracle MCP configured via Docker MCP Toolkit.")
    print("Tip: run `docker mcp server ls` to verify config shows ✓ done.")
    return 0


def _get_mcp_connection(args: argparse.Namespace) -> OracleMcpConnection:
    connection_string = args.connection_string or input("Oracle connection string (host:port/service): ").strip()
    user = args.user or input("Oracle user: ").strip()

    if args.password_stdin:
        password = sys.stdin.read().strip()
    elif args.password_env:
        password = os.environ.get(args.password_env, "").strip()
    else:
        password = getpass.getpass("Oracle password: ")

    if not connection_string or not user or not password:
        raise SystemExit("connection string, user, and password are required")

    return OracleMcpConnection(connection_string=connection_string, user=user, password=password)


def cmd_mcp_list_schemas(args: argparse.Namespace) -> int:
    conn = _get_mcp_connection(args)
    mcp = OracleMcp(conn)
    try:
        for s in mcp.list_schemas():
            print(s)
        return 0
    finally:
        mcp.close()


def cmd_mcp_list_tables(args: argparse.Namespace) -> int:
    conn = _get_mcp_connection(args)
    mcp = OracleMcp(conn)
    try:
        for t in mcp.list_tables(schema=args.schema, pattern=args.pattern):
            print(t)
        return 0
    finally:
        mcp.close()


def cmd_mcp_inventory(args: argparse.Namespace) -> int:
    conn = _get_mcp_connection(args)
    mcp = OracleMcp(conn)
    try:
        schemas = mcp.list_schemas()
        tables = mcp.list_tables(schema=args.schema, pattern=args.pattern)
        counts = mcp.count_objects(schema=args.schema)

        if args.json:
            import json

            print(
                json.dumps(
                    {
                        "schemas": schemas,
                        "tables": tables,
                        "counts": counts,
                        "schema_filter": args.schema,
                        "pattern": args.pattern,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("Oracle MCP inventory")
            print(f"Schemas: {len(schemas)}")
            if args.schema:
                print(f"Objects (schema={args.schema}):")
            else:
                print("Objects:")
            for key in sorted(counts.keys()):
                print(f"- {key}: {counts[key]}")
            if args.schema:
                print(f"Tables (schema={args.schema}): {len(tables)}")
            else:
                print(f"Tables: {len(tables)}")
        return 0
    finally:
        mcp.close()


def cmd_mcp_plan(args: argparse.Namespace) -> int:
    conn = _get_mcp_connection(args)
    mcp = OracleMcp(conn)
    try:
        schemas = mcp.list_schemas()
        tables = mcp.list_tables(schema=args.schema, pattern=args.pattern)
        counts = mcp.count_objects(schema=args.schema)

        # Reuse the existing markdown plan generator shape with a simple, DB-based inventory summary.
        md_lines: list[str] = []
        md_lines.append("# Migration Plan (MCP): Oracle → PostgreSQL")
        md_lines.append("")
        md_lines.append("## Inventory")
        md_lines.append("")
        md_lines.append(f"- Schemas: {len(schemas)}")
        md_lines.append(f"- Tables (listed): {len(tables)}")
        for key in sorted(counts.keys()):
            if key.lower() == "table":
                continue
            md_lines.append(f"- {key}: {counts[key]}")
        if args.schema:
            md_lines.append(f"- Schema filter: {args.schema}")
        if args.pattern:
            md_lines.append(f"- Table pattern: {args.pattern}")
        md_lines.append("")
        md_lines.append("## Next steps")
        md_lines.append("")
        md_lines.append("1. Extract DDL for in-scope schemas/tables")
        md_lines.append("2. Convert DDL + review types/constraints/indexes")
        md_lines.append("3. Plan data migration + validation")
        md_lines.append("4. Replace Oracle-specific SQL in app code")
        md_lines.append("5. Run integration/performance checks")
        md_lines.append("")
        print("\n".join(md_lines) + "\n")
        return 0
    finally:
        mcp.close()


def cmd_mcp_query(args: argparse.Namespace) -> int:
    conn = _get_mcp_connection(args)
    mcp = OracleMcp(conn)
    try:
        result = mcp.execute_query(args.query, max_rows=args.max_rows)
        import json

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        mcp.close()


def cmd_mcp_analyze(args: argparse.Namespace) -> int:
    conn = _get_mcp_connection(args)
    mcp = OracleMcp(conn)
    try:
        tables = mcp.list_tables(schema=args.schema, pattern=args.pattern)
        warnings: list[dict[str, object]] = []
        try:
            views = mcp.list_views_with_definitions(schema=args.schema, max_rows=args.max_views)
        except Exception as e:
            views = []
            warnings.append(
                {
                    "code": "views_unavailable",
                    "message": f"Could not read view definitions from ALL_VIEWS: {e}",
                }
            )
        counts = mcp.count_objects(schema=args.schema)
        plsql_objects = mcp.list_objects(
            schema=args.schema,
            object_types=["PACKAGE", "PROCEDURE", "FUNCTION"],
            max_rows=args.max_plsql_objects,
        )

        domains = infer_domains_from_tables(tables)
        arch_style, join_view_count = recommend_architecture_from_views(views)

        result = McpAnalysisResult(
            schema=args.schema,
            pattern=args.pattern,
            tables=tables,
            views=views,
            object_counts=counts,
            plsql_objects=[
                {
                    "owner": str(r.get("OWNER") or r.get("owner") or ""),
                    "object_type": str(r.get("OBJECT_TYPE") or r.get("object_type") or ""),
                    "object_name": str(r.get("OBJECT_NAME") or r.get("object_name") or ""),
                }
                for r in plsql_objects
                if isinstance(r, dict)
            ],
            warnings=[
                {
                    "code": str(w.get("code", "warning")),
                    "message": str(w.get("message", "")),
                }
                for w in warnings
            ],
            domains=domains,
            recommended_architecture=arch_style,
            join_view_count=join_view_count,
        )
        out_dir = write_analysis_outputs(result, args.out_dir)

        if args.use_claude:
            from .anthropic_client import AnthropicConfig, get_api_key_from_env
            from .claude_analysis import ClaudeAnalysisInputs, run_claude_analysis

            api_key = get_api_key_from_env(args.anthropic_api_key_env)
            cfg = AnthropicConfig(
                api_key=api_key,
                model=args.claude_model,
                max_tokens=args.claude_max_tokens,
                timeout_seconds=args.claude_timeout_seconds,
            )
            claude_in = ClaudeAnalysisInputs(
                schema=args.schema,
                pattern=args.pattern,
                tables=tables,
                views=views,
                object_counts=counts,
                plsql_objects=result.plsql_objects,
            )
            try:
                claude_analysis, raw = run_claude_analysis(config=cfg, inp=claude_in)
                _write_claude_outputs(out_dir=Path(out_dir), analysis=claude_analysis, raw_response=raw)
                print(f"Claude analysis written to: {Path(out_dir) / 'claude_analysis.json'}")
            except Exception as e:
                print(f"Claude analysis failed: {e}")

        print(f"Recommended architecture: {arch_style}")
        if domains:
            domain_names = ", ".join(sorted(domains.keys(), key=str.casefold))
            print(f"Domains: {domain_names}")
        else:
            print("Domains: (none inferred)")
        if warnings:
            print(f"Warnings: {len(warnings)} (see {out_dir / 'analysis.json'})")
        print(f"Output written to: {out_dir}")
        return 0
    finally:
        mcp.close()


def cmd_mcp_run(args: argparse.Namespace) -> int:
    """End-to-end MCP pipeline: analyze + structure + PL/SQL fetch + conversion."""

    conn = _get_mcp_connection(args)
    mcp = OracleMcp(conn)
    try:
        tables = mcp.list_tables(schema=args.schema, pattern=args.pattern)
        warnings: list[dict[str, object]] = []
        try:
            views = mcp.list_views_with_definitions(schema=args.schema, max_rows=args.max_views)
        except Exception as e:
            views = []
            warnings.append(
                {
                    "code": "views_unavailable",
                    "message": f"Could not read view definitions from ALL_VIEWS: {e}",
                }
            )
        counts = mcp.count_objects(schema=args.schema)

        domains = infer_domains_from_tables(tables)
        arch_style, join_view_count = recommend_architecture_from_views(views)

        plsql_objects = mcp.list_objects(
            schema=args.schema,
            object_types=["PACKAGE", "PACKAGE BODY", "PROCEDURE", "FUNCTION"],
            max_rows=args.max_units,
        )

        # Best-effort: concatenate PL/SQL sources into one buffer.
        plsql_chunks: list[str] = []
        attempted = 0
        fetched = 0
        for r in plsql_objects:
            if not isinstance(r, dict):
                continue
            owner = str(r.get("OWNER") or r.get("owner") or "").strip()
            obj_type = str(r.get("OBJECT_TYPE") or r.get("object_type") or "").strip()
            obj_name = str(r.get("OBJECT_NAME") or r.get("object_name") or "").strip()
            if not (owner and obj_type and obj_name):
                continue
            attempted += 1
            try:
                src = mcp.get_plsql_source(schema=owner, name=obj_name, object_type=obj_type)
            except Exception as e:
                warnings.append(
                    {
                        "code": "plsql_source_unavailable",
                        "owner": owner,
                        "object_type": obj_type,
                        "object_name": obj_name,
                        "message": f"Could not fetch source from ALL_SOURCE for {owner}.{obj_name} ({obj_type}): {e}",
                    }
                )
                continue
            plsql_chunks.append(f"-- {owner}.{obj_name} ({obj_type})\n{src}\n")
            fetched += 1

        plsql_all = "\n".join(plsql_chunks).rstrip() + "\n" if plsql_chunks else ""
        if not plsql_all:
            warnings.append(
                {
                    "code": "plsql_export_empty",
                    "message": (
                        "No PL/SQL source was exported. This is commonly due to missing privileges on ALL_SOURCE or "
                        "because the schema has no packages/procedures/functions visible to this user."
                    ),
                    "attempted": attempted,
                    "fetched": fetched,
                }
            )
        converted = convert_plsql_to_language(plsql_all, target_language=args.target_language)

        # Write analysis outputs.
        analysis = McpAnalysisResult(
            schema=args.schema,
            pattern=args.pattern,
            tables=tables,
            views=views,
            object_counts=counts,
            plsql_objects=[
                {
                    "owner": str(r.get("OWNER") or r.get("owner") or ""),
                    "object_type": str(r.get("OBJECT_TYPE") or r.get("object_type") or ""),
                    "object_name": str(r.get("OBJECT_NAME") or r.get("object_name") or ""),
                }
                for r in plsql_objects
                if isinstance(r, dict)
            ],
            warnings=[
                {
                    "code": str(w.get("code", "warning")),
                    "message": str(w.get("message", "")),
                    "owner": str(w.get("owner", "")),
                    "object_type": str(w.get("object_type", "")),
                    "object_name": str(w.get("object_name", "")),
                    "attempted": w.get("attempted"),
                    "fetched": w.get("fetched"),
                }
                for w in warnings
            ],
            domains=domains,
            recommended_architecture=arch_style,
            join_view_count=join_view_count,
        )
        out_dir = write_analysis_outputs(analysis, args.out_dir)

        effective_domains = domains
        domain_source = "heuristic"
        claude_analysis: dict | None = None

        # Optional: Claude-driven DDD/EDA analysis.
        if args.use_claude:
            from .anthropic_client import AnthropicConfig, get_api_key_from_env
            from .claude_analysis import ClaudeAnalysisInputs, run_claude_analysis

            api_key = get_api_key_from_env(args.anthropic_api_key_env)
            cfg = AnthropicConfig(
                api_key=api_key,
                model=args.claude_model,
                max_tokens=args.claude_max_tokens,
                timeout_seconds=args.claude_timeout_seconds,
            )
            claude_in = ClaudeAnalysisInputs(
                schema=args.schema,
                pattern=args.pattern,
                tables=tables,
                views=views,
                object_counts=counts,
                plsql_objects=analysis.plsql_objects,
            )
            try:
                claude_analysis, raw = run_claude_analysis(config=cfg, inp=claude_in)
                _write_claude_outputs(out_dir=Path(out_dir), analysis=claude_analysis, raw_response=raw)
                _write_background_job_prompts(out_dir=Path(out_dir))

                # Prefer Claude domains for downstream structure generation, if present.
                cd = claude_analysis.get("domains") if isinstance(claude_analysis, dict) else None
                if isinstance(cd, list) and cd:
                    mapped: dict[str, list[str]] = {}
                    for item in cd:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or "").strip()
                        if not name:
                            continue
                        tables_list = item.get("tables")
                        if isinstance(tables_list, list):
                            mapped[name] = [str(t) for t in tables_list if str(t).strip()]
                        else:
                            mapped[name] = []
                    if mapped:
                        effective_domains = mapped
                        domain_source = "claude"
            except Exception as e:
                warnings.append(
                    {
                        "code": "claude_analysis_failed",
                        "message": f"Claude analysis failed: {e}",
                    }
                )

        # Always generate both structures (microservices + EDA), based on domains.
        create_best_practice_structure(
            out_dir / "microservices",
            domains=effective_domains,
            architecture="Microservices",
            language=args.target_language,
        )
        create_best_practice_structure(
            out_dir / "eda",
            domains=effective_domains,
            architecture="EDA",
            language=args.target_language,
        )

        # Write an explicit domain list file to the output folder.
        domain_lines: list[str] = []
        domain_lines.append(f"# Inferred domains (source: {domain_source})\n")
        if not effective_domains:
            domain_lines.append("(none)\n")
        else:
            for domain in sorted(effective_domains.keys(), key=str.casefold):
                domain_lines.append(f"- {domain} ({len(effective_domains[domain])} tables)\n")
        (out_dir / "domains.txt").write_text("".join(domain_lines), encoding="utf-8")

        # Write architecture summary.
        architecture = generate_architecture(effective_domains, arch_style)
        import json

        (out_dir / "architecture.json").write_text(
            json.dumps(architecture, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        (out_dir / "warnings.json").write_text(
            json.dumps({"warnings": warnings}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Write PL/SQL + converted output.
        (out_dir / "plsql.sql").write_text(
            plsql_all or "-- No PL/SQL exported (see warnings.json / analysis.json)\n",
            encoding="utf-8",
        )
        (out_dir / "converted.py").write_text(converted, encoding="utf-8")

        print(f"Recommended architecture: {arch_style}")
        print(f"Target language: {args.target_language}")
        if effective_domains:
            domain_names = ", ".join(sorted(effective_domains.keys(), key=str.casefold))
            print(f"Domains ({domain_source}): {domain_names}")
        else:
            print("Domains: (none inferred)")
        if warnings:
            print(f"Warnings: {len(warnings)} (see {out_dir / 'warnings.json'})")
        print(f"Output written to: {out_dir}")
        return 0
    finally:
        mcp.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oracle-migration",
        description="Oracle migration helper (MCP-only): inventory, plan, and read-only queries via Oracle MCP.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_mcp = sub.add_parser("mcp-setup", help="Configure Docker Desktop MCP Toolkit (Oracle server)")
    p_mcp.add_argument("--connection-string", help="Oracle connection string (host:port/service)")
    p_mcp.add_argument("--user", help="Oracle username")
    p_mcp.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read password from STDIN (avoids putting it in shell history)",
    )
    p_mcp.add_argument(
        "--password-env",
        help="Read password from the given environment variable name",
    )
    p_mcp.set_defaults(func=cmd_mcp_setup)

    def add_mcp_auth_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--connection-string", help="Oracle connection string (host:port/service)")
        p.add_argument("--user", help="Oracle username")
        p.add_argument("--password-stdin", action="store_true", help="Read password from STDIN")
        p.add_argument("--password-env", help="Read password from env var name")

    def add_claude_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--use-claude",
            action="store_true",
            help="Use Anthropic Claude for analysis (requires ANTHROPIC_API_KEY env var)",
        )
        p.add_argument(
            "--anthropic-api-key-env",
            default="ANTHROPIC_API_KEY",
            help="Environment variable name containing the Anthropic API key (default: ANTHROPIC_API_KEY)",
        )
        p.add_argument(
            "--claude-model",
            default="claude-3-5-sonnet-latest",
            help="Claude model name (default: claude-3-5-sonnet-latest)",
        )
        p.add_argument(
            "--claude-max-tokens",
            type=int,
            default=2000,
            help="Max tokens for Claude response (default: 2000)",
        )
        p.add_argument(
            "--claude-timeout-seconds",
            type=int,
            default=120,
            help="HTTP timeout for Claude request (default: 120)",
        )

    p_ls_schemas = sub.add_parser("mcp-list-schemas", help="List schemas via Oracle MCP")
    add_mcp_auth_args(p_ls_schemas)
    p_ls_schemas.set_defaults(func=cmd_mcp_list_schemas)

    p_ls_tables = sub.add_parser("mcp-list-tables", help="List tables via Oracle MCP")
    add_mcp_auth_args(p_ls_tables)
    p_ls_tables.add_argument("--schema", help="Schema name")
    p_ls_tables.add_argument("--pattern", help="Table pattern (supports %% as wildcard)")
    p_ls_tables.set_defaults(func=cmd_mcp_list_tables)

    p_inv = sub.add_parser("mcp-inventory", help="Inventory schemas/tables via Oracle MCP")
    add_mcp_auth_args(p_inv)
    p_inv.add_argument("--schema", help="Schema name")
    p_inv.add_argument("--pattern", help="Table pattern (supports %% as wildcard)")
    p_inv.add_argument("--json", action="store_true", help="Output JSON")
    p_inv.set_defaults(func=cmd_mcp_inventory)

    p_plan = sub.add_parser("mcp-plan", help="Generate a migration plan from live DB via Oracle MCP")
    add_mcp_auth_args(p_plan)
    p_plan.add_argument("--schema", help="Schema name")
    p_plan.add_argument("--pattern", help="Table pattern (supports %% as wildcard)")
    p_plan.set_defaults(func=cmd_mcp_plan)

    p_query = sub.add_parser("mcp-query", help="Execute a read-only query via Oracle MCP")
    add_mcp_auth_args(p_query)
    p_query.add_argument("query", help="SQL query to execute")
    p_query.add_argument("--max-rows", type=int, default=1000, help="Max rows (default: 1000)")
    p_query.set_defaults(func=cmd_mcp_query)

    p_analyze = sub.add_parser(
        "mcp-analyze",
        help="Analyze schema (domains + EDA-vs-microservices) via Oracle MCP and write outputs",
    )
    add_mcp_auth_args(p_analyze)
    p_analyze.add_argument("--schema", help="Schema name (recommended to avoid huge metadata reads)")
    p_analyze.add_argument("--pattern", help="Table pattern (supports %% as wildcard)")
    p_analyze.add_argument(
        "--max-views",
        type=int,
        default=200,
        help="Max view rows to fetch (default: 200)",
    )
    p_analyze.add_argument(
        "--max-plsql-objects",
        type=int,
        default=200,
        help="Max PL/SQL objects to list in analysis output (default: 200)",
    )
    p_analyze.add_argument(
        "--out-dir",
        default="generated",
        help="Output directory (default: generated)",
    )
    add_claude_args(p_analyze)
    p_analyze.set_defaults(func=cmd_mcp_analyze)

    p_run = sub.add_parser(
        "mcp-run",
        help="End-to-end pipeline: analyze + structure + PL/SQL export + conversion",
    )
    add_mcp_auth_args(p_run)
    p_run.add_argument("--schema", help="Schema name (recommended)")
    p_run.add_argument("--pattern", help="Table pattern (supports %% as wildcard)")
    p_run.add_argument(
        "--max-views",
        type=int,
        default=200,
        help="Max view rows to fetch (default: 200)",
    )
    p_run.add_argument(
        "--max-units",
        type=int,
        default=50,
        help="Max PL/SQL objects to fetch source for (default: 50)",
    )
    p_run.add_argument(
        "--target-language",
        default="python",
        help="Target language (default: python)",
    )
    p_run.add_argument(
        "--out-dir",
        default="generated",
        help="Output directory (default: generated)",
    )
    add_claude_args(p_run)
    p_run.set_defaults(func=cmd_mcp_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
