"""MCP client: connect to MCP servers and forward tool calls."""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from draguniteus.config import Config


class MCPClient:
    """Manages MCP server connections and tool forwarding."""

    def __init__(self):
        self.servers: dict[str, dict[str, Any]] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._tools_cache: dict[str, list[dict]] = {}
        self._lock = threading.Lock()
        self._load_config()

    def _load_config(self) -> None:
        """Load MCP server definitions from config."""
        from draguniteus.config import Config
        cfg = Config()
        # Accept both 'mcpServers' (Claude Code style) and 'mcp_servers' keys
        servers = cfg.mcp_servers
        for name, conf in servers.items():
            self.servers[name] = conf

    def add_server(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        server_type: str = "stdio",
        url: str | None = None,
    ) -> None:
        """Add and start an MCP server."""
        config = {
            "command": command,
            "args": args or [],
            "env": env or {},
            "type": server_type,
            "url": url,
        }
        self.servers[name] = config
        self.start_server(name)

    def start_server(self, name: str) -> None:
        """Start an MCP server process."""
        if name not in self.servers:
            return
        with self._lock:
            if name in self._processes:
                return  # Already running

        conf = self.servers[name]
        server_type = conf.get("type", "stdio")

        if server_type == "stdio":
            self._start_stdio_server(name, conf)
        # SSE/HTTP/WebSocket servers would be started differently
        # For now we focus on stdio which is the most common

    def _start_stdio_server(self, name: str, conf: dict[str, Any]) -> None:
        """Start a stdio MCP server process."""
        import logging
        logger = logging.getLogger("draguniteus.mcp")

        cmd = conf["command"]
        args = list(conf.get("args", []))
        env = dict(os.environ)
        env.update(conf.get("env", {}))

        try:
            proc = subprocess.Popen(
                [cmd] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=False,  # binary mode for JSON-RPC
            )
            with self._lock:
                self._processes[name] = proc
            logger.info(f"MCP server '{name}' started (pid={proc.pid})")

            # Send initialize handshake (required by MCP spec before any other method)
            ok = self._send_initialize(name)
            if ok:
                logger.info(f"MCP server '{name}' initialized successfully")
            else:
                logger.warning(f"MCP server '{name}' initialization may have failed — some tools may be unavailable")
        except FileNotFoundError:
            logger.error(f"MCP server '{name}' failed to start: command not found: '{cmd}'")
        except PermissionError:
            logger.error(f"MCP server '{name}' failed to start: permission denied: '{cmd}'")
        except Exception as e:
            logger.error(f"MCP server '{name}' failed to start: {e}")

    def _send_initialize(self, server_name: str) -> bool:
        """Send the required initialize request to an MCP server. Returns True on success."""
        init_req = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "draguniteus",
                    "version": "1.0",
                },
            },
            "id": 1,
        }
        try:
            proc = self._processes[server_name]
            req_bytes = (json.dumps(init_req) + "\n").encode("utf-8")
            proc.stdin.write(req_bytes)
            proc.stdin.flush()
            # Read the initialize response synchronously (required before other methods)
            line = self._readline_with_timeout(proc, 10.0)
            if line is None:
                return False
            # Store that we've initialized so subsequent requests know to expect responses
            self._initialized = getattr(self, '_initialized', set())
            self._initialized.add(server_name)
            return True
        except Exception:
            return False

    def stop_server(self, name: str) -> None:
        """Stop an MCP server process."""
        with self._lock:
            if name in self._processes:
                try:
                    self._processes[name].terminate()
                    self._processes[name].wait(timeout=5)
                except Exception:
                    try:
                        self._processes[name].kill()
                    except Exception:
                        pass
                del self._processes[name]

        # Clean up initialized state so server can be restarted
        self._initialized = getattr(self, '_initialized', set())
        self._initialized.discard(name)

    def get_status(self, server_name: str) -> str:
        """Get the connection status of an MCP server.

        Returns one of: 'stopped', 'running', 'initialized', 'failed'
        """
        with self._lock:
            if server_name not in self._processes:
                return "stopped"
        # Server process exists — check if it's still alive
        proc = self._processes[server_name]
        if proc.poll() is not None:
            return "failed"
        initialized = getattr(self, '_initialized', set())
        if server_name in initialized:
            return "initialized"
        return "running"

    def get_all_statuses(self) -> dict[str, str]:
        """Get status of all configured servers."""
        return {name: self.get_status(name) for name in self.servers}

    def stop_all(self) -> None:
        """Stop all MCP server processes."""
        with self._lock:
            for name in list(self._processes.keys()):
                self.stop_server(name)

    def _send_request(self, server_name: str, method: str, params: dict[str, Any] | None = None,
                    timeout: float = 30.0) -> dict[str, Any] | None:
        """Send a JSON-RPC request and return the parsed response."""
        if server_name not in self.servers:
            return None

        conf = self.servers[server_name]
        server_type = conf.get("type", "stdio")

        if server_type == "stdio":
            return self._send_stdio_request(server_name, method, params, timeout)
        return None

    def ping(self, server_name: str) -> bool:
        """Check if an MCP server is responsive by sending a ping."""
        resp = self._send_request(server_name, "ping", timeout=5.0)
        return resp is not None

    def list_tools(self, server_name: str) -> list[dict]:
        """List all tools available from an MCP server."""
        if server_name in self._tools_cache:
            return self._tools_cache[server_name]

        resp = self._send_request(server_name, "tools/list", timeout=10.0)
        if resp and "result" in resp:
            tools = resp["result"].get("tools", [])
            with self._lock:
                self._tools_cache[server_name] = tools
            return tools
        return []

    def _readline_with_timeout(self, proc: subprocess.Popen, timeout: float = 30.0,
                              max_line_length: int = 10 * 1024 * 1024) -> str | None:
        """Read one line from proc.stdout with timeout. Cross-platform."""
        result = []
        exc = []

        def reader():
            try:
                # Read up to max_line_length bytes to prevent memory exhaustion
                import os
                fd = proc.stdout.fileno()
                chunk = os.read(fd, max_line_length)
                if chunk:
                    # Find newline in the chunk
                    nl_index = chunk.find(b'\n')
                    if nl_index >= 0:
                        result.append(chunk[:nl_index + 1])
                    else:
                        result.append(chunk)
            except Exception as e:
                exc.append(e)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if exc:
            return None
        if result:
            raw = result[0]
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace")
            return raw
        return None

    def _send_stdio_request(self, server_name: str, method: str,
                             params: dict[str, Any] | None = None,
                             timeout: float = 30.0) -> dict[str, Any] | None:
        """Send a JSON-RPC request via stdio with per-request timeout."""
        import os

        with self._lock:
            if server_name not in self._processes:
                return None
            proc = self._processes[server_name]

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
        }

        try:
            proc.stdin.write(json.dumps(request).encode("utf-8") + b"\n")
            proc.stdin.flush()

            result: list = []

            def reader():
                try:
                    # Read with size limit to prevent memory exhaustion
                    chunk = os.read(proc.stdout.fileno(), 10 * 1024 * 1024)
                    if chunk:
                        result.append(chunk)
                except Exception:
                    pass

            t = threading.Thread(target=reader, daemon=True)
            t.start()
            t.join(timeout=timeout)

            if not result:
                return None
            raw = result[0]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if raw:
                # Extract just the first JSON object (ignore any extra output)
                raw = raw.strip()
                resp = json.loads(raw)
                return resp
            return None
        except json.JSONDecodeError:
            return None
        except Exception:
            return None

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on an MCP server via stdio protocol.

        MCP servers use the 'tools/call' method rather than calling tool names directly.
        """
        resp = self._send_request(server_name, "tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        if resp is None:
            return f"MCP error: server {server_name} not available or tool call failed"
        if "error" in resp:
            return f"MCP error: {resp['error']}"
        result = resp.get("result", {})
        if isinstance(result, dict):
            content = result.get("content", [])
            if isinstance(content, list) and content:
                return content[0].get("text", str(result))
            return str(result)
        return str(result)

    def get_tools_map(self) -> dict[str, tuple[str, str]]:
        """Get a map of tool_name -> (server_name, tool_name) for all MCP tools."""
        tools_map = {}
        for server_name in self.servers:
            tools = self.list_tools(server_name)
            for tool in tools:
                tool_name = tool.get("name", "")
                if tool_name:
                    mcp_name = f"mcp__{server_name}__{tool_name}"
                    tools_map[mcp_name] = (server_name, tool_name)
        return tools_map

    def get_server_configs(self) -> dict[str, dict[str, Any]]:
        return self.servers

    @staticmethod
    def expand_env_vars(value: str | None, base_dir: Path | None = None) -> str | None:
        """Expand environment variables in strings like ${CLAUDE_PLUGIN_ROOT}."""
        if value is None:
            return None
        if base_dir:
            value = value.replace("${CLAUDE_PLUGIN_ROOT}", str(base_dir))
            value = value.replace("${PLUGIN_ROOT}", str(base_dir))
        return value