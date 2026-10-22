"""The PitchPulse MCP server: the registry's tools on an `MCPServer`, plus the
Streamable HTTP endpoint the match API mounts at `/mcp`.

Everything served is public synthetic data and every tool is read-only, so the
endpoint has no sign-in (docs/MCP.md says so). It is still guarded like the
REST routes: a per-IP token bucket, a small request body cap, one JSON-RPC
request per POST (no batches), Origin and Host checks against the app's
allow-list (the SDK's DNS-rebinding protection), and `Cache-Control: no-store`.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import Message, Receive, Scope, Send

from matchmind import __version__ as _pkg_version
from matchmind.api.session import SessionError

from .tools import REGISTRY, ToolContext, ToolSpec

logger = logging.getLogger("pitchpulse.mcp")

SERVER_NAME = "pitchpulse"
MAX_BODY_BYTES = 16 * 1024  # a tool call is a few hundred bytes
OOPS = "Something went wrong on our side. Please try again."
TOO_MANY = "Too many requests. Wait a moment and try again."
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")
INSTRUCTIONS = (
    "PitchPulse match intelligence on a fictional, synthetic football match. All tools are "
    "read-only. Numbers come from the deterministic stats engine; quote a moment's numbers only "
    "from its facts (get_moment). Start with get_match_snapshot or list_moments."
)
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


def canonical_json(payload: Any) -> str:
    """The one JSON text form used for tool results (and by the parity tests)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def _bad_input(exc: ValidationError) -> str:
    fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
    if fields:
        return f"Check {', '.join(fields)}: the value is missing or not allowed."
    return "Those arguments are not valid for this tool."


def _error(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def _result(payload: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=canonical_json(payload))], structured_content=payload
    )


class PitchPulseMCP(MCPServer):
    """MCPServer that answers bad arguments with one plain sentence (field names only)."""

    specs: dict[str, ToolSpec]

    async def call_tool(self, name: str, arguments: dict[str, Any], context: Any = None) -> Any:
        spec = self.specs.get(name)
        if spec is not None and isinstance(arguments, dict):
            unknown = sorted(k[:40] for k in arguments if k not in spec.input_model.model_fields)
            if unknown:
                return _error(f"Check {', '.join(unknown[:3])}: this tool does not take that argument.")
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            if isinstance(exc.__cause__, ValidationError):
                return _error(_bad_input(exc.__cause__))
            raise


def _signature(model: type[BaseModel], output: type[BaseModel]) -> inspect.Signature:
    """A keyword-only signature built from the input model, so the tool's input schema is the
    model's own flat fields, constraints and descriptions."""
    params = []
    for name, field in model.model_fields.items():
        annotation = Annotated[(field.annotation, *field.metadata, Field(description=field.description))]
        default = inspect.Parameter.empty if field.is_required() else field.default
        params.append(
            inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation)
        )
    return inspect.Signature(params, return_annotation=Annotated[CallToolResult, output])


def _tool_function(spec: ToolSpec, ctx: ToolContext) -> Callable[..., Any]:
    async def call(**kwargs: Any) -> CallToolResult:
        try:
            args = spec.input_model.model_validate(kwargs)
        except ValidationError as exc:
            return _error(_bad_input(exc))
        try:
            payload = await spec.handler(ctx, args)
        except HTTPException as exc:
            return _error(str(exc.detail))
        except SessionError as exc:
            return _error(str(exc))
        except Exception:
            logger.exception("MCP tool %s failed", spec.name)
            return _error(OOPS)
        return _result(payload)

    call.__name__ = spec.name
    call.__doc__ = spec.description
    call.__signature__ = _signature(spec.input_model, spec.output_model)  # type: ignore[attr-defined]
    return call


def build_server(hub: Any, tools: Iterable[ToolSpec] | None = None) -> PitchPulseMCP:
    """An MCP server whose tools read the given hub's live session."""
    server = PitchPulseMCP(
        SERVER_NAME,
        title="PitchPulse",
        instructions=INSTRUCTIONS,
        version=_pkg_version,
        log_level="WARNING",
    )
    ctx = ToolContext(hub=hub)
    server.specs = {}
    for spec in tools if tools is not None else REGISTRY.values():
        server.specs[spec.name] = spec
        server.add_tool(
            _tool_function(spec, ctx),
            name=spec.name,
            title=spec.title,
            description=spec.description,
            annotations=READ_ONLY,
            structured_output=True,
        )
    return server


# --- Streamable HTTP ----------------------------------------------------------------------------


def allowed_hosts(origins: Iterable[str], extra: Iterable[str] = ()) -> list[str]:
    """Host header values the MCP endpoint answers: local development, the hosts of the
    allowed origins (including this server's own public origin) and any listed in
    MATCHMIND_MCP_ALLOWED_HOSTS. Used only against DNS rebinding, never for trust."""
    hosts: list[str] = []
    for h in LOCAL_HOSTS:
        hosts += [h, f"{h}:*"]
    for origin in origins:
        netloc = urlsplit(origin).netloc
        if netloc and netloc not in hosts:
            hosts.append(netloc)
    env = os.environ.get("MATCHMIND_MCP_ALLOWED_HOSTS", "")
    for h in [*extra, *env.split(",")]:
        h = h.strip()
        if h and h != "*" and h not in hosts:
            hosts.append(h)
    return hosts


class MCPHttpEndpoint:
    """ASGI app for `/mcp`: stateless Streamable HTTP with JSON responses (one POST per
    request, no long-lived streams), wrapped in the app's own limits."""

    def __init__(
        self,
        server: MCPServer,
        allowed_origins: Iterable[str],
        hosts: Iterable[str],
        rate_check: Callable[[Request], None] | None = None,
        max_body: int = MAX_BODY_BYTES,
    ) -> None:
        self.server = server
        self.security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(hosts),
            allowed_origins=[o.rstrip("/") for o in allowed_origins],
        )
        self.rate_check = rate_check
        self.max_body = max_body
        self._manager: Any = None

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        """Start the SDK's session manager for one app lifespan (a fresh one each time)."""
        self.server.streamable_http_app(
            stateless_http=True,
            json_response=True,
            transport_security=self.security,
            max_request_body_size=self.max_body,
        )
        manager = self.server.session_manager
        async with manager.run():
            self._manager = manager
            try:
                yield
            finally:
                self._manager = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover - only HTTP is routed here
            return
        request = Request(scope, receive)
        if self._manager is None:
            await _plain(503, "The match is still loading. Try again in a moment.")(scope, receive, send)
            return
        if request.method != "POST":
            await Response(status_code=405, headers={"Allow": "POST"})(scope, receive, send)
            return
        if self.rate_check is not None:
            try:
                self.rate_check(request)
            except HTTPException:
                await _plain(429, TOO_MANY, {"Retry-After": "1"})(scope, receive, send)
                return
        body = await _read_body(request, self.max_body)
        if body is None:
            await _plain(413, "That request is too big. Tool calls must be under 16 KB.")(
                scope, receive, send
            )
            return
        if body.lstrip()[:1] == b"[":
            await _plain(400, "Send one request at a time; batches are not accepted.")(scope, receive, send)
            return
        await self._manager.handle_request(scope, _replay(body, receive), _no_store(send))


def _plain(status: int, detail: str, headers: dict[str, str] | None = None) -> Response:
    resp = JSONResponse({"detail": detail}, status_code=status, headers=headers)
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def _read_body(request: Request, limit: int) -> bytes | None:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            return None
    return bytes(body)


def _replay(body: bytes, receive: Receive) -> Receive:
    """The body already read, then the real channel (so a disconnect is still seen)."""
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


def _no_store(send: Send) -> Send:
    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
            headers += [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]
            message = {**message, "headers": headers}
        await send(message)

    return wrapped
