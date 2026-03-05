from __future__ import annotations

import re
from textwrap import indent


class PLSQLToPythonConverter:
    """Pragmatic PL/SQL → Python converter.

    This is intentionally heuristic (regex based) and best-effort.
    It extracts PROCEDURE/FUNCTION blocks and maps a few common SQL patterns
    into repository method calls.
    """

    def __init__(self, repository_name: str = "repository") -> None:
        self.repository_name = repository_name

    def convert(self, plsql_code: str) -> str:
        units = self._extract_program_units(plsql_code)
        python_units = [self._convert_unit(u) for u in units]
        if not python_units:
            return "# No procedures/functions detected by heuristic converter\n"
        return "\n\n".join(python_units).rstrip() + "\n"

    def _extract_program_units(self, code: str) -> list[dict]:
        pattern = re.compile(
            r"(PROCEDURE|FUNCTION)\s+(\w+)\s*\((.*?)\)\s*(RETURN\s+\w+)?(.*?)END\s+\2;",
            re.IGNORECASE | re.DOTALL,
        )
        units: list[dict] = []
        for match in pattern.finditer(code or ""):
            kind = match.group(1).upper()
            name = match.group(2)
            params = match.group(3)
            return_type = match.group(4)
            body = match.group(5)
            units.append(
                {
                    "kind": kind,
                    "name": name,
                    "params": self._parse_params(params),
                    "return_type": return_type.strip() if return_type else None,
                    "body": (body or "").strip(),
                }
            )
        return units

    def _parse_params(self, param_str: str) -> list[dict[str, str]]:
        if not (param_str or "").strip():
            return []
        params: list[dict[str, str]] = []
        for p in param_str.split(","):
            parts = p.strip().split()
            if len(parts) >= 2:
                params.append({"name": parts[0], "type": parts[1]})
        return params

    def _convert_unit(self, unit: dict) -> str:
        if unit.get("kind") == "PROCEDURE":
            return self._convert_procedure(unit)
        return self._convert_function(unit)

    def _convert_procedure(self, unit: dict) -> str:
        method_name = self._snake_case(str(unit.get("name", "procedure")))
        params = self._python_params(unit.get("params") or [])
        body = self._convert_body(str(unit.get("body", "")))
        return (
            f"def {method_name}(self{', ' if params else ''}{params}):\n"
            f"{indent(body, '    ')}"
        ).rstrip()

    def _convert_function(self, unit: dict) -> str:
        method_name = self._snake_case(str(unit.get("name", "function")))
        params = self._python_params(unit.get("params") or [])
        body = self._convert_body(str(unit.get("body", "")), is_function=True)
        return (
            f"def {method_name}(self{', ' if params else ''}{params}):\n"
            f"{indent(body, '    ')}"
        ).rstrip()

    def _convert_body(self, body: str, *, is_function: bool = False) -> str:
        python_lines: list[str] = []

        select_into = re.findall(
            r"SELECT\s+(.*?)\s+INTO\s+(\w+)\s+FROM\s+(.*?);",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for expr, var, table in select_into:
            python_lines.append(
                f"{var} = self.{self.repository_name}.fetch_one(\"{expr.strip()}\", table=\"{table.strip()}\")"
            )

        inserts = re.findall(
            r"INSERT\s+INTO\s+(\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\);",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for table, cols, vals in inserts:
            python_lines.append(
                f"self.{self.repository_name}.insert(\"{table}\", [{cols}], [{vals}])"
            )

        updates = re.findall(
            r"UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+(.*?);",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for table, set_clause, where_clause in updates:
            python_lines.append(
                f"self.{self.repository_name}.update(\"{table}\", set_clause=\"{set_clause.strip()}\", where=\"{where_clause.strip()}\")"
            )

        deletes = re.findall(
            r"DELETE\s+FROM\s+(\w+)\s+WHERE\s+(.*?);",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for table, where_clause in deletes:
            python_lines.append(
                f"self.{self.repository_name}.delete(\"{table}\", where=\"{where_clause.strip()}\")"
            )

        if is_function:
            ret = re.findall(r"RETURN\s+(.*?);", body, flags=re.IGNORECASE)
            if ret:
                python_lines.append(f"return {ret[0].strip()}")

        if not python_lines:
            python_lines.append("pass")

        return "\n".join(python_lines) + "\n"

    def _python_params(self, params: list[dict[str, str]]) -> str:
        return ", ".join(p.get("name", "p") for p in params if p.get("name"))

    def _snake_case(self, name: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def convert_plsql_to_language(plsql: str, *, target_language: str = "python") -> str:
    target = (target_language or "").strip().lower()
    if target == "python":
        return PLSQLToPythonConverter().convert(plsql)
    return f"# target language '{target_language}' not implemented yet\n"
