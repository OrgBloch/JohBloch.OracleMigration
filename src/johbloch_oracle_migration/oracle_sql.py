from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class OracleSqlInventory:
    tables: list[str]
    sequences: list[str]
    views: list[str]
    triggers: list[str]
    procedures: list[str]
    functions: list[str]
    packages: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


_NAME = r"(?:(?:\"[^\"]+\")|(?:[A-Za-z_][A-Za-z0-9_\$#]*))(?:\.(?:(?:\"[^\"]+\")|(?:[A-Za-z_][A-Za-z0-9_\$#]*)))*"

_PATTERNS: dict[str, re.Pattern[str]] = {
    "tables": re.compile(rf"\bCREATE\s+TABLE\s+({_NAME})\b", re.IGNORECASE),
    "sequences": re.compile(rf"\bCREATE\s+SEQUENCE\s+({_NAME})\b", re.IGNORECASE),
    "views": re.compile(rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+({_NAME})\b", re.IGNORECASE),
    "triggers": re.compile(rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+({_NAME})\b", re.IGNORECASE),
    "procedures": re.compile(rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+({_NAME})\b", re.IGNORECASE),
    "functions": re.compile(rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+({_NAME})\b", re.IGNORECASE),
    "packages": re.compile(rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+({_NAME})\b", re.IGNORECASE),
}


def _unique_sorted(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.strip()
        if not key:
            continue
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return sorted(out, key=str.casefold)


def analyze_oracle_sql(sql_text: str) -> OracleSqlInventory:
    matches: dict[str, list[str]] = {k: [] for k in _PATTERNS}
    for key, pattern in _PATTERNS.items():
        matches[key].extend(m.group(1) for m in pattern.finditer(sql_text))

    return OracleSqlInventory(
        tables=_unique_sorted(matches["tables"]),
        sequences=_unique_sorted(matches["sequences"]),
        views=_unique_sorted(matches["views"]),
        triggers=_unique_sorted(matches["triggers"]),
        procedures=_unique_sorted(matches["procedures"]),
        functions=_unique_sorted(matches["functions"]),
        packages=_unique_sorted(matches["packages"]),
    )


_TYPE_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bVARCHAR2\b", re.IGNORECASE), "VARCHAR"),
    (re.compile(r"\bNVARCHAR2\b", re.IGNORECASE), "VARCHAR"),
    (re.compile(r"\bNCHAR\b", re.IGNORECASE), "CHAR"),
    (re.compile(r"\bNUMBER\b", re.IGNORECASE), "NUMERIC"),
    (re.compile(r"\bCLOB\b", re.IGNORECASE), "TEXT"),
    (re.compile(r"\bBLOB\b", re.IGNORECASE), "BYTEA"),
]


_MISC_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bSYSDATE\b", re.IGNORECASE), "CURRENT_TIMESTAMP"),
    (re.compile(r"\bSYSTIMESTAMP\b", re.IGNORECASE), "CURRENT_TIMESTAMP"),
    (re.compile(r"\bFROM\s+DUAL\b", re.IGNORECASE), ""),
]


def convert_oracle_to_postgres(sql_text: str) -> str:
    """Best-effort Oracle SQL -> PostgreSQL SQL text conversion.

    This is intentionally conservative and only does low-risk, mechanical
    replacements. It will NOT fully convert PL/SQL, packages, triggers, etc.
    """

    converted = sql_text

    for pattern, replacement in _TYPE_REPLACEMENTS:
        converted = pattern.sub(replacement, converted)

    for pattern, replacement in _MISC_REPLACEMENTS:
        converted = pattern.sub(replacement, converted)

    converted = re.sub(r"\s+ENABLE\b", "", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bUSING\s+INDEX\b", "", converted, flags=re.IGNORECASE)

    return converted
