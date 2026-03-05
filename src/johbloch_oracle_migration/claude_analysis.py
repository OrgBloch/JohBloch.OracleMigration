from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .anthropic_client import AnthropicConfig, call_anthropic_messages, extract_json_object


@dataclass(frozen=True)
class ClaudeAnalysisInputs:
    schema: str | None
    pattern: str | None
    tables: list[str]
    views: list[dict[str, Any]]
    object_counts: dict[str, int]
    plsql_objects: list[dict[str, str]]


SYSTEM_PROMPT = """You are a senior software architect specialized in DDD and EDA.
You will analyze Oracle schema signals (tables, views, PL/SQL object names) and infer bounded contexts (domains).
You must be practical: produce a migration-oriented analysis that can drive code generation later.
Return JSON only.
""".strip()


def build_user_prompt(inp: ClaudeAnalysisInputs) -> str:
    # Keep the payload compact: tables can be large.
    tables = inp.tables[:2000]
    views = inp.views[:200]
    plsql_objects = inp.plsql_objects[:500]

    request = {
        "schema": inp.schema,
        "pattern": inp.pattern,
        "object_counts": inp.object_counts,
        "tables": tables,
        "views": views,
        "plsql_objects": plsql_objects,
    }

    return (
        "Analyze the following Oracle schema inventory and infer DDD bounded contexts (domains).\n\n"
        "Output MUST be a single JSON object (no markdown).\n\n"
        "JSON schema to return:\n"
        "{\n"
        "  \"domains\": [\n"
        "    {\n"
        "      \"name\": string,\n"
        "      \"description\": string,\n"
        "      \"tables\": [string],\n"
        "      \"plsql\": [string],\n"
        "      \"commands\": [string],\n"
        "      \"events\": [string]\n"
        "    }\n"
        "  ],\n"
        "  \"eda\": {\n"
        "    \"topics\": [string],\n"
        "    \"event_catalog\": [ {\"name\": string, \"producer\": string, \"consumers\": [string]} ]\n"
        "  },\n"
        "  \"microservices\": {\n"
        "    \"services\": [ {\"name\": string, \"apis\": [string], \"owned_tables\": [string]} ]\n"
        "  },\n"
        "  \"notes\": [string]\n"
        "}\n\n"
        "Heuristics:\n"
        "- Use table names to cluster domains.\n"
        "- Use view definitions (JOINs) to flag cross-domain read models.\n"
        "- Use PL/SQL names to infer domain services/commands.\n\n"
        "INPUT:\n"
        + json.dumps(request, indent=2, sort_keys=True)
    )


def run_claude_analysis(*, config: AnthropicConfig, inp: ClaudeAnalysisInputs) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (analysis_json, raw_api_response)."""

    user_prompt = build_user_prompt(inp)
    raw = call_anthropic_messages(config=config, system=SYSTEM_PROMPT, user=user_prompt)

    # Extract text blocks and parse first JSON object.
    text_parts: list[str] = []
    content = raw.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
    text = "\n".join(text_parts).strip()

    analysis = extract_json_object(text)
    if not isinstance(analysis, dict):
        raise ValueError("Claude analysis was not a JSON object")

    return analysis, raw
