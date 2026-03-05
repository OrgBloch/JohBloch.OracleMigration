from __future__ import annotations

import argparse
import getpass
import os
import sys

from .mcp_setup import OracleMcpConfig, docker_mcp_setup_oracle
from .mcp_analysis import (
    McpAnalysisResult,
    infer_domains_from_tables,
    recommend_architecture_from_views,
    write_analysis_outputs,
)
from .oracle_mcp import OracleMcp, OracleMcpConnection


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
        views = mcp.list_views_with_definitions(schema=args.schema, max_rows=args.max_views)

        domains = infer_domains_from_tables(tables)
        arch_style, join_view_count = recommend_architecture_from_views(views)

        result = McpAnalysisResult(
            schema=args.schema,
            pattern=args.pattern,
            tables=tables,
            views=views,
            domains=domains,
            recommended_architecture=arch_style,
            join_view_count=join_view_count,
        )
        out_dir = write_analysis_outputs(result, args.out_dir)

        print(f"Recommended architecture: {arch_style}")
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
        "--out-dir",
        default="generated",
        help="Output directory (default: generated)",
    )
    p_analyze.set_defaults(func=cmd_mcp_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
