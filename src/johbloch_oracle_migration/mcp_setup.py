from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class OracleMcpConfig:
    connection_string: str
    user: str


def _run(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        check=True,
        capture_output=True,
    )


def _docker_exe() -> str:
    return os.environ.get("DOCKER", "docker")


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def docker_mcp_set_oracle_password(password: str) -> None:
    # Use STDIN to avoid leaking the password in shell history / process list.
    _run([_docker_exe(), "mcp", "secret", "set", "oracle.password"], input_text=password + "\n")


def docker_mcp_write_config(config_yaml: str) -> None:
    docker = _docker_exe()

    # docker mcp config write takes a single argument: the YAML content itself.
    # (Passing a file path is interpreted as YAML text and fails.)
    _run([docker, "mcp", "config", "write", config_yaml])


def docker_mcp_read_config() -> str:
    cp = _run([_docker_exe(), "mcp", "config", "read"])
    return cp.stdout


def merge_oracle_config_into_yaml(existing_yaml: str, oracle: OracleMcpConfig) -> str:
    # Docker MCP config read/write uses a YAML-ish format. We do a conservative
    # merge that preserves existing content by appending/replacing a top-level
    # `oracle:` block.

    lines = existing_yaml.splitlines()

    def is_top_level_key(line: str) -> bool:
        return bool(line) and not line.startswith(" ") and line.rstrip().endswith(":")

    # Find existing `oracle:` block (top-level key)
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == "oracle:" and not line.startswith(" "):
            start = idx
            break

    if start is not None:
        end = len(lines)
        for idx in range(start + 1, len(lines)):
            if is_top_level_key(lines[idx]):
                end = idx
                break
        del lines[start:end]
        # Trim trailing empty lines after deletion
        while lines and lines[-1].strip() == "":
            lines.pop()

    if lines and lines[-1].strip() != "":
        lines.append("")

    lines.extend(
        [
            "oracle:",
            f"  oracle_connection_string: {_yaml_quote(oracle.connection_string)}",
            f"  oracle_user: {_yaml_quote(oracle.user)}",
            "",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def docker_mcp_setup_oracle(oracle: OracleMcpConfig, password: str) -> None:
    docker_mcp_set_oracle_password(password)
    existing = docker_mcp_read_config()
    merged = merge_oracle_config_into_yaml(existing, oracle)
    docker_mcp_write_config(merged)
