from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass
from typing import Any

from .mcp_client import StdioMcpClient


@dataclass(frozen=True)
class OracleMcpConnection:
    connection_string: str
    user: str
    password: str


def _docker_exe() -> str:
    return os.environ.get("DOCKER", "docker")


def _oracle_mcp_command(conn: OracleMcpConnection) -> tuple[list[str], dict[str, str]]:
    env = {
        "ORACLE_CONNECTION_STRING": conn.connection_string,
        "ORACLE_USER": conn.user,
        "ORACLE_PASSWORD": conn.password,
    }
    cmd = [
        _docker_exe(),
        "run",
        "-i",
        "--rm",
        "-e",
        "ORACLE_CONNECTION_STRING",
        "-e",
        "ORACLE_USER",
        "-e",
        "ORACLE_PASSWORD",
        "mcp/oracle",
    ]
    return cmd, {**os.environ, **env}


class OracleMcp:
    def __init__(self, conn: OracleMcpConnection) -> None:
        cmd, env = _oracle_mcp_command(conn)
        self._client = StdioMcpClient(cmd, env=env)
        self._client.initialize()

    def close(self) -> None:
        self._client.close()

    def list_schemas(self) -> list[str]:
        result = self._client.tools_call("list_schemas")
        return _extract_text_list(result)

    def list_tables(self, *, schema: str | None = None, pattern: str | None = None) -> list[str]:
        args: dict[str, Any] = {}
        if schema:
            args["schema"] = schema
        if pattern:
            args["pattern"] = pattern
        result = self._client.tools_call("list_tables", args)
        return _extract_text_list(result)

    def describe_table(self, table_name: str, *, schema: str | None = None) -> Any:
        args: dict[str, Any] = {"table_name": table_name}
        if schema:
            args["schema"] = schema
        return self._client.tools_call("describe_table", args)

    def execute_query(self, query: str, *, max_rows: int | None = None) -> Any:
        args: dict[str, Any] = {"query": query}
        if max_rows is not None:
            args["maxRows"] = max_rows
        return self._client.tools_call("execute_query", args)

    def list_views_with_definitions(
        self,
        *,
        schema: str | None = None,
        max_rows: int = 500,
    ) -> list[dict[str, Any]]:
        """Return view names and (best-effort) view definitions.

        Notes:
        - Uses ALL_VIEWS, which depends on the connected user's privileges.
        - Oracle stores view definitions in LONG (TEXT). Some versions expose TEXT_VC.
        - This method tries TEXT_VC first and falls back to TEXT.
        """

        where = ""
        if schema:
            owner = _normalize_schema_name(schema)
            where = f" WHERE owner = '{owner}'"

        # TEXT_VC exists in some Oracle versions; prefer it when available.
        sql_candidates = [
            "SELECT owner, view_name, text_vc AS definition FROM all_views" + where,
            "SELECT owner, view_name, text AS definition FROM all_views" + where,
        ]

        last_err: Exception | None = None
        for sql in sql_candidates:
            try:
                raw = self.execute_query(sql, max_rows=max_rows)
                return _extract_rows(raw)
            except Exception as e:  # pragma: no cover
                last_err = e
                continue

        raise RuntimeError(f"failed to query view definitions: {last_err}")

    def count_objects(self, *, schema: str | None = None) -> dict[str, int]:
        """Return counts for common Oracle object types.

        Notes:
        - Uses ALL_OBJECTS. If the connected user lacks privileges, Oracle may return fewer objects.
        - This is read-only and intended for planning/inventory.
        """

        owner_filter = ""
        if schema:
            owner = _normalize_schema_name(schema)
            owner_filter = f" AND owner = '{owner}'"

        sql = (
            "SELECT object_type, COUNT(*) AS cnt "
            "FROM all_objects "
            "WHERE object_type IN (" 
            "'TABLE','VIEW','SEQUENCE','TRIGGER','PROCEDURE','FUNCTION','PACKAGE'" 
            ")" + owner_filter + " "
            "GROUP BY object_type"
        )

        raw = self.execute_query(sql, max_rows=1000)
        rows = _extract_rows(raw)
        counts: dict[str, int] = {"TABLE": 0, "VIEW": 0, "SEQUENCE": 0, "TRIGGER": 0, "PROCEDURE": 0, "FUNCTION": 0, "PACKAGE": 0}
        for row in rows:
            # Be defensive about column names/casing.
            obj_type = (row.get("OBJECT_TYPE") or row.get("object_type") or "").strip().upper()
            cnt_val = row.get("CNT") if "CNT" in row else row.get("cnt")
            try:
                cnt = int(cnt_val)
            except Exception:
                continue
            if obj_type:
                counts[obj_type] = cnt
        # Return friendly keys.
        return {k.title(): v for k, v in counts.items()}

    def list_objects(
        self,
        *,
        schema: str | None = None,
        object_types: list[str] | tuple[str, ...] | None = None,
        max_rows: int = 500,
    ) -> list[dict[str, Any]]:
        """List objects from ALL_OBJECTS.

        This is a lightweight helper intended for inventory/analysis.
        """

        where_parts: list[str] = []
        if schema:
            owner = _normalize_schema_name(schema)
            where_parts.append(f"owner = '{owner}'")

        types = [t.strip().upper() for t in (object_types or []) if str(t).strip()]
        if types:
            safe_types = [_normalize_object_type(t) for t in types]
            in_list = ",".join([f"'{t}'" for t in safe_types])
            where_parts.append(f"object_type IN ({in_list})")

        where = ""
        if where_parts:
            where = " WHERE " + " AND ".join(where_parts)

        sql = (
            "SELECT owner, object_type, object_name "
            "FROM all_objects" + where + " "
            "ORDER BY owner, object_type, object_name"
        )
        raw = self.execute_query(sql, max_rows=max_rows)
        return _extract_rows(raw)

    def get_plsql_source(
        self,
        *,
        schema: str,
        name: str,
        object_type: str,
        max_rows: int = 20000,
    ) -> str:
        """Fetch PL/SQL source from ALL_SOURCE and return as a single string.

        Notes:
        - Requires the connected user to have visibility of ALL_SOURCE for the requested owner.
        - We validate identifiers because execute_query does not support bind variables.
        """

        owner = _normalize_schema_name(schema)
        obj_name = _normalize_object_name(name)
        obj_type = _normalize_object_type(object_type)

        sql = (
            "SELECT line, text "
            "FROM all_source "
            f"WHERE owner = '{owner}' AND name = '{obj_name}' AND type = '{obj_type}' "
            "ORDER BY line"
        )
        raw = self.execute_query(sql, max_rows=max_rows)
        rows = _extract_rows(raw)
        lines: list[tuple[int, str]] = []
        for r in rows:
            line_raw = r.get("LINE") if "LINE" in r else r.get("line")
            text_raw = r.get("TEXT") if "TEXT" in r else r.get("text")
            try:
                line_no = int(line_raw)
            except Exception:
                continue
            lines.append((line_no, str(text_raw or "")))

        lines.sort(key=lambda x: x[0])
        return "".join([t for _, t in lines]).rstrip() + "\n"


_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")
_OBJECT_NAME_RE = _SCHEMA_RE


def _normalize_object_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        raise ValueError("object name is empty")
    if n.startswith('"') and n.endswith('"') and len(n) >= 2:
        raise ValueError("quoted object names are not supported")
    if not _OBJECT_NAME_RE.match(n):
        raise ValueError("invalid object name")
    return n.upper()


_OBJECT_TYPE_RE = re.compile(r"^[A-Z][A-Z ]*$")
_ALLOWED_OBJECT_TYPES = {
    "TABLE",
    "VIEW",
    "SEQUENCE",
    "TRIGGER",
    "PROCEDURE",
    "FUNCTION",
    "PACKAGE",
    "PACKAGE BODY",
    "TYPE",
    "TYPE BODY",
}


def _normalize_object_type(object_type: str) -> str:
    t = (object_type or "").strip().upper()
    if not t:
        raise ValueError("object type is empty")
    if not _OBJECT_TYPE_RE.match(t):
        raise ValueError("invalid object type")
    if t not in _ALLOWED_OBJECT_TYPES:
        raise ValueError(f"unsupported object type: {t}")
    return t


def _normalize_schema_name(schema: str) -> str:
    s = (schema or "").strip()
    if not s:
        raise ValueError("schema is empty")
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        # Keep quoted identifiers as-is (without surrounding quotes) is risky; for now reject.
        raise ValueError("quoted schema names are not supported")
    if not _SCHEMA_RE.match(s):
        raise ValueError("invalid schema name")
    return s.upper()


def _extract_rows(result: dict) -> list[dict[str, Any]]:
    """Normalize the MCP tool result into a list of row dicts.

    The Oracle MCP server tool is expected to return a JSON object containing rows.
    We keep this helper permissive to handle different server shapes.
    """

    if not isinstance(result, dict):
        return []

    # Some servers wrap the tool result as text content (often JSON).
    content = result.get("content")
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        if text_parts:
            text = "\n".join(text_parts).strip()
            if text:
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None
                if isinstance(parsed, dict):
                    return _extract_rows(parsed)

    # Common shapes: {"rows": [...]}, or nested under "result".
    if isinstance(result.get("rows"), list):
        return [r for r in result["rows"] if isinstance(r, dict)]

    nested = result.get("result")
    if isinstance(nested, dict) and isinstance(nested.get("rows"), list):
        return [r for r in nested["rows"] if isinstance(r, dict)]

    return []


def _extract_text_list(tool_call_result: Any) -> list[str]:
    # Many MCP servers return: { content: [{type:'text', text:'...'}] }
    if isinstance(tool_call_result, dict):
        content = tool_call_result.get("content")
        if isinstance(content, list):
            out: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text", "")).strip()
                    if not text:
                        continue
                    # Some servers return newline-separated values.
                    out.extend([ln.strip() for ln in text.splitlines() if ln.strip()])
            return out
    if isinstance(tool_call_result, list):
        return [str(x) for x in tool_call_result]
    if isinstance(tool_call_result, str):
        return [ln.strip() for ln in tool_call_result.splitlines() if ln.strip()]
    return [str(tool_call_result)]
