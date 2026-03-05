from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpResult:
    id: int
    result: Any


class StdioMcpClient:
    """Minimal MCP (JSON-RPC) client over stdio.

    This is intentionally tiny: initialize + tools/list + tools/call.
    """

    def __init__(self, command: list[str], *, env: dict[str, str] | None = None) -> None:
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,
        )
        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("failed to open stdio for MCP process")

        self._lock = threading.Lock()
        self._next_id = 1

    def close(self) -> None:
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        finally:
            self._proc.terminate()

    def _send(self, payload: dict[str, Any]) -> int:
        with self._lock:
            req_id = int(payload["id"])
            line = json.dumps(payload)
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            return req_id

    def _read_until_id(self, req_id: int) -> Any:
        assert self._proc.stdout is not None
        while True:
            line = self._proc.stdout.readline()
            if not line:
                stderr = ""
                if self._proc.stderr is not None:
                    try:
                        stderr = self._proc.stderr.read() or ""
                    except Exception:
                        stderr = ""
                raise RuntimeError(f"MCP process ended unexpectedly. stderr=\n{stderr}")

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                # Ignore non-JSON noise.
                continue

            # Ignore notifications.
            if "id" not in msg:
                continue

            if msg.get("id") != req_id:
                continue

            if "error" in msg and msg["error"] is not None:
                raise RuntimeError(str(msg["error"]))

            return msg.get("result")

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req_id = self._next_id
        self._next_id += 1

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        self._send(payload)
        return self._read_until_id(req_id)

    def initialize(self) -> None:
        # Standard MCP init (best-effort). Some servers may ignore fields.
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "johbloch-oracle-migration", "version": "0.1.0"},
                "capabilities": {},
            },
        )

    def tools_list(self) -> Any:
        return self.request("tools/list")

    def tools_call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})
