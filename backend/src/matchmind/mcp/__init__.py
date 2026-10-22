"""PitchPulse over the Model Context Protocol: typed, read-only tools on the live
synthetic match (docs/MCP.md). `build_server` makes the server; the match API
mounts it at `/mcp` (Streamable HTTP) and `matchmind-mcp` serves it over stdio."""

from .server import MCPHttpEndpoint, build_server
from .tools import PLANNED_TOOLS, REGISTRY, ToolContext, ToolSpec, register

__all__ = [
    "PLANNED_TOOLS",
    "REGISTRY",
    "MCPHttpEndpoint",
    "ToolContext",
    "ToolSpec",
    "build_server",
    "register",
]
