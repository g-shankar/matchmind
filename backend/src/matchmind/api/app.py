"""PitchPulse match API: one WebSocket and a few REST routes (docs/API-CONTRACT.md).

Playback is shared by everyone watching; viewer choices live per connection.
Session work runs in worker threads, so a slow crew call never freezes the
event loop. Two locks, always taken in this order:

- the crew lock orders crew work (moments, cards, recaps) and the jumps that
  reset it. Paid model calls only ever run under this lock.
- the playback lock guards the session's state (stats, clock, play/pause).
  It is only held for quick work, never for a model call, so pause, speed and
  the REST reads answer at once even while the model is slow.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import os
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from matchmind.crew.contracts import FocusMetric, Language, Persona, ViewerProfile
from matchmind.crew.producer import ViewerState

from . import view
from .session import MatchSession, SessionError, Tick, build_session

logger = logging.getLogger("pitchpulse.api")

MAX_MESSAGE_BYTES = 4096
MAX_CONNECTIONS = int(os.environ.get("MATCHMIND_MAX_CONNECTIONS", "200"))
MAX_CONN_PER_IP = int(os.environ.get("MATCHMIND_MAX_CONN_PER_IP", "20"))
SEND_QUEUE_BYTES = 4 * 1024 * 1024  # per connection; a viewer this far behind is dropped
JUMP_INTERVAL_S = 0.5  # at most one seek or reset per half second, for everyone
POST_BURST, POST_PER_SECOND = 10, 2.0  # per client IP on the POST routes
IP_LIMITERS_MAX = 10_000
CLOSE_TRY_AGAIN = 1013  # WebSocket "try again later"
DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:3000"
OOPS = "Something went wrong on our side. Please try again."
TOO_FAST = "Jumping around too fast. Wait a moment and try again."
TOO_MANY = "Too many requests. Wait a moment and try again."

T = TypeVar("T")


def allowed_origins_from_env() -> list[str]:
    raw = os.environ.get("MATCHMIND_ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip() and o.strip() != "*"]


# --- Client actions --------------------------------------------------------------------------


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str


class SetSpeed(_Action):
    speed_multiplier: Literal[1, 10, 60]


class Seek(_Action):
    clock_s: float = Field(ge=0, le=10_000)
    period: Literal[1, 2] | None = None

    @field_validator("clock_s")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("clock_s must be a number")
        return v


class SetView(_Action):
    persona: Persona | None = None
    language: Language | None = None
    favourite_team: str | None = Field(default=None, max_length=32)
    focus_player_id: str | None = Field(default=None, max_length=32)
    focus_metric: FocusMetric | None = None


class SetPersona(_Action):
    persona: Persona
    spotlight_player_id: str | None = Field(default=None, max_length=32)


ACTION_MODELS: dict[str, type[_Action]] = {
    "toggle_pause": _Action,
    "set_speed": SetSpeed,
    "reset": _Action,
    "seek": Seek,
    "set_view": SetView,
    "set_persona": SetPersona,
}

ACTION_HELP: dict[str, str] = {
    "toggle_pause": "toggle_pause takes no other fields.",
    "set_speed": "Speed must be 1, 10 or 60.",
    "reset": "reset takes no other fields.",
    "seek": "Seek needs clock_s, a time in seconds from kick-off (and optionally period 1 or 2).",
    "set_view": (
        "That view setting is not valid. Persona: casual, tactical, fantasy or player_spotlight; "
        "language: en, es, fr, ar or ja; focus metric: pressure, xg, pass_difficulty, top_speed or momentum."
    ),
    "set_persona": "Persona must be casual, tactical, fantasy or player_spotlight.",
}


class SeekBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clock_s: float = Field(ge=0, le=10_000)
    period: Literal[1, 2] | None = None


class SpeedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speed_multiplier: Literal[1, 10, 60]


# --- Connections -----------------------------------------------------------------------------


class RateLimiter:
    """Token bucket: `burst` actions at once, refilled at `per_second`."""

    def __init__(
        self, burst: int = 20, per_second: float = 10.0, clock: Callable[[], float] = time.monotonic
    ):
        self.burst, self.rate, self.clock = burst, per_second, clock
        self.tokens = float(burst)
        self.last = clock()

    def allow(self) -> bool:
        now = self.clock()
        self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class Connection:
    def __init__(
        self,
        ws: WebSocket,
        clock: Callable[[], float],
        on_drop: Callable[[Connection], None] | None = None,
    ) -> None:
        self.ws = ws
        self.profile = ViewerProfile()
        self.view_state = ViewerState()  # what the producer remembers for this viewer
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.queued_bytes = 0  # bounded by SEND_QUEUE_BYTES
        self.limiter = RateLimiter(clock=clock)
        self.closed = False
        self.writer_task: asyncio.Task[None] | None = None
        self._on_drop = on_drop
        self._closer: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        self.writer_task = asyncio.create_task(self.writer())
        return self.writer_task

    def send(self, payload: dict[str, Any]) -> None:
        if self.closed:
            return
        text = json.dumps(payload, separators=(",", ":"))  # ASCII: one byte per character
        if self.queued_bytes + len(text) > SEND_QUEUE_BYTES:
            self.overflow()
            return
        self.queued_bytes += len(text)
        self.queue.put_nowait(text)

    def error(self, text: str) -> None:
        self.send(view.message("ERROR", {"message": text}))

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.queue.put_nowait(None)

    def overflow(self) -> None:
        """The viewer cannot keep up: drop it for real rather than grow memory."""
        if self.closed:
            return
        self.closed = True
        self._drain()
        if self.writer_task is not None:
            self.writer_task.cancel()
        if self._on_drop is not None:
            self._on_drop(self)
        self._closer = asyncio.get_running_loop().create_task(self._close_socket(CLOSE_TRY_AGAIN))

    def _drain(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queued_bytes = 0

    async def _close_socket(self, code: int) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.ws.close(code=code), timeout=2)

    async def writer(self) -> None:
        while True:
            text = await self.queue.get()
            if text is None:
                break
            self.queued_bytes = max(0, self.queued_bytes - len(text))
            try:
                await self.ws.send_text(text)
            except Exception:  # noqa: BLE001 - the socket went away
                self.closed = True
                break


class Hub:
    """Owns the shared session and the open connections."""

    def __init__(self, session: MatchSession | None, clock: Callable[[], float] = time.monotonic) -> None:
        self._session = session
        self.clock = clock
        self.connections: set[Connection] = set()
        self._lock = asyncio.Lock()  # playback lock: quick session state work only
        self._crew_lock = asyncio.Lock()  # crew work, in order; taken before the playback lock
        self._last_jump: float | None = None
        self._slots = 0  # WebSocket slots reserved (before accept)
        self._slots_per_ip: dict[str, int] = {}

    # --- connection slots ----------------------------------------------------------------------

    def reserve(self, ip: str) -> bool:
        """Take a connection slot before the handshake, so the caps cannot be raced."""
        if self._slots >= MAX_CONNECTIONS or self._slots_per_ip.get(ip, 0) >= MAX_CONN_PER_IP:
            return False
        self._slots += 1
        self._slots_per_ip[ip] = self._slots_per_ip.get(ip, 0) + 1
        return True

    def release(self, ip: str) -> None:
        self._slots = max(0, self._slots - 1)
        left = self._slots_per_ip.get(ip, 0) - 1
        if left > 0:
            self._slots_per_ip[ip] = left
        else:
            self._slots_per_ip.pop(ip, None)

    def drop(self, conn: Connection) -> None:
        self.connections.discard(conn)

    @property
    def session(self) -> MatchSession:
        if self._session is None:
            raise HTTPException(status_code=503, detail="The match is still loading. Try again in a moment.")
        return self._session

    def attach(self, session: MatchSession) -> None:
        self._session = session

    async def run(self, fn: Callable[..., T], *args: Any) -> T:
        """Quick session work under the playback lock, off the event loop. Never a model call."""
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    async def run_crew(self, fn: Callable[..., T], *args: Any) -> T:
        """Crew work (may call the model) under the crew lock only. Everything that
        changes the session's stats also holds the crew lock, so the state it reads
        is steady; pause and speed may still change underneath, which is harmless."""
        async with self._crew_lock:
            return await asyncio.to_thread(fn, *args)

    # --- broadcasting ------------------------------------------------------------------------

    def _snapshot_messages(self, conns: list[Connection], profiles: list[ViewerProfile]) -> list[dict]:
        return [view.message("INITIAL_SNAPSHOT", view.snapshot_payload(self.session, p)) for p in profiles]

    async def send_snapshots(self, conns: list[Connection]) -> None:
        async with self._crew_lock:
            await self._send_snapshots(conns)

    async def _send_snapshots(self, conns: list[Connection]) -> None:
        """Caller holds the crew lock."""
        conns = [c for c in conns if not c.closed]
        profiles = [c.profile.model_copy() for c in conns]
        for conn in conns:
            conn.view_state = ViewerState()
        messages = await asyncio.to_thread(self._snapshot_messages, conns, profiles)
        for conn, msg in zip(conns, messages, strict=True):
            conn.send(msg)

    def broadcast(self, payload: dict[str, Any]) -> None:
        for conn in list(self.connections):
            conn.send(payload)

    def _render(
        self, ticks: list[Tick], conns: list[Connection], profiles: list[ViewerProfile]
    ) -> list[list[dict]]:
        """Crew work for ticks already played: moments, then cards and recaps per viewer."""
        session = self.session
        out: list[list[dict]] = [[] for _ in conns]
        for tick in ticks:
            tick = session.crew_tick(tick)
            shared = view.tick_shared(tick)
            for i, profile in enumerate(profiles):
                cards = session.cards_for(tick.bundles, profile, conns[i].view_state, tick)
                data = dict(shared, cards=[view.card_payload(c) for c in cards])
                out[i].append(view.message("MATCH_TICK", data))
            if tick.is_last:
                for i, profile in enumerate(profiles):
                    recap = session.recap(profile)
                    out[i].append(view.message("MATCH_END", {"recap": recap.model_dump(mode="json")}))
                    out[i].append(view.message("PLAYBACK_CONTROL", session.playback()))
        return out

    async def pump(self) -> None:
        """One step of the playback loop."""
        if self._session is None:
            return
        async with self._crew_lock:
            conns = [c for c in self.connections if not c.closed]
            if not conns:
                # Nobody is watching: hold the match where it is.
                await self.run(self._session.touch)
                return
            profiles = [c.profile.model_copy() for c in conns]
            # Stats under the playback lock (quick); crew and model work after it is released.
            ticks = await self.run(self._session.advance, False)
            if not ticks:
                return
            batches = await asyncio.to_thread(self._render, ticks, conns, profiles)
        for conn, batch in zip(conns, batches, strict=True):
            for msg in batch:
                conn.send(msg)

    async def loop(self, interval: float) -> None:
        while True:
            try:
                await self.pump()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("playback loop step failed")
            await asyncio.sleep(interval)

    # --- shared playback controls (used by WebSocket and REST) -------------------------------

    async def toggle_pause(self) -> dict[str, Any]:
        await self.run(self.session.toggle_pause)
        return self._announce_playback()

    async def set_speed(self, speed: int) -> dict[str, Any]:
        await self.run(self.session.set_speed, speed)
        return self._announce_playback()

    def _announce_playback(self) -> dict[str, Any]:
        playback = self.session.playback()
        self.broadcast(view.message("PLAYBACK_CONTROL", playback))
        return playback

    def _claim_jump(self) -> None:
        """One shared throttle for seek and reset (WebSocket and REST alike):
        at most one every JUMP_INTERVAL_S; requests in between are refused."""
        now = self.clock()
        if self._last_jump is not None and now - self._last_jump < JUMP_INTERVAL_S:
            raise HTTPException(status_code=429, detail=TOO_FAST)
        self._last_jump = now

    async def reset(self) -> dict[str, Any]:
        session = self.session
        self._claim_jump()
        async with self._crew_lock:
            await self.run(session.reset)
            self.broadcast(view.message("MATCH_RESET", {}))
            await self._send_snapshots(list(self.connections))
            return session.playback()

    async def seek(self, clock_s: float, period: int | None) -> dict[str, Any]:
        session = self.session
        self._claim_jump()
        async with self._crew_lock:
            await self.run(session.seek, clock_s, period)
            await self._send_snapshots(list(self.connections))
            return session.playback()


# --- App -------------------------------------------------------------------------------------


def create_app(
    session: MatchSession | None = None,
    session_factory: Callable[[], MatchSession] = build_session,
    tick_interval: float | None = 0.1,
    allowed_origins: list[str] | None = None,
    static_dir: str | Path | None = None,
    clock: Callable[[], float] = time.monotonic,
    public_origin: str | None = None,
) -> FastAPI:
    hub = Hub(session, clock=clock)
    origins = allowed_origins if allowed_origins is not None else allowed_origins_from_env()
    # Default: ./static relative to the working directory (the container copies the build there).
    static = Path(static_dir or os.environ.get("MATCHMIND_STATIC_DIR") or "static")
    serves_frontend = static.is_dir() and (static / "index.html").is_file()
    # WebSocket origins: the allow-list, plus this server's own public origin when it
    # serves the frontend itself. The Host header is never used: anyone can set it.
    ws_origins = set(origins)
    own = (public_origin or os.environ.get("MATCHMIND_PUBLIC_ORIGIN") or "").strip().rstrip("/")
    if serves_frontend and own and own != "*":
        ws_origins.add(own)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if hub._session is None:
            hub.attach(await asyncio.to_thread(session_factory))
        task = asyncio.create_task(hub.loop(tick_interval)) if tick_interval else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="PitchPulse match API", version="1.0.0", lifespan=lifespan)
    app.state.hub = hub
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[[Request], Awaitable[Any]]):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def _bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        detail = (
            f"Check {', '.join(fields)}: the value is missing or not allowed." if fields else "Bad request."
        )
        return JSONResponse({"detail": detail}, status_code=400)

    @app.exception_handler(SessionError)
    async def _session_error(request: Request, exc: SessionError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def _crash(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("request failed: %s", request.url.path)
        return JSONResponse({"detail": OOPS}, status_code=500)

    def _profile(persona: Persona, lang: Language, favourite_team: str | None) -> ViewerProfile:
        if favourite_team is not None and not hub.session.is_known_team(favourite_team):
            raise HTTPException(status_code=400, detail="That club is not in this match.")
        return ViewerProfile(persona=persona, language=lang, favourite_team=favourite_team)

    # --- REST --------------------------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/teams")
    async def teams() -> dict[str, Any]:
        return view.teams_payload(hub.session)

    ip_limiters: OrderedDict[str, RateLimiter] = OrderedDict()

    def post_limit(request: Request) -> None:
        """A simple per-client-IP limit on the POST routes."""
        ip = request.client.host if request.client else "unknown"
        limiter = ip_limiters.get(ip)
        if limiter is None:
            limiter = ip_limiters[ip] = RateLimiter(burst=POST_BURST, per_second=POST_PER_SECOND, clock=clock)
            while len(ip_limiters) > IP_LIMITERS_MAX:
                ip_limiters.popitem(last=False)
        ip_limiters.move_to_end(ip)
        if not limiter.allow():
            raise HTTPException(status_code=429, detail=TOO_MANY)

    limited = [Depends(post_limit)]

    @app.get("/api/match/snapshot")
    async def snapshot() -> dict[str, Any]:
        return await hub.run_crew(view.snapshot_payload, hub.session, ViewerProfile())

    @app.get("/api/match/players")
    async def players() -> list[dict[str, Any]]:
        return await hub.run(lambda: [view.player_payload(p) for p in hub.session.players()])

    @app.get("/api/match/bookmarks")
    async def bookmarks() -> list[dict[str, Any]]:
        return [view.bookmark_payload(b) for b in hub.session.bookmarks]

    @app.get("/api/match/moment/{moment_id}")
    async def moment(
        moment_id: str,
        persona: Persona = "casual",
        lang: Language = "en",
        favourite_team: str | None = Query(default=None, max_length=32),
    ) -> dict[str, Any]:
        if len(moment_id) > 80:
            raise HTTPException(status_code=404, detail="We could not find that moment.")
        profile = _profile(persona, lang, favourite_team)
        # Moments are fixed at load and the crew is thread-safe: no lock, so a slow
        # model answer here holds up nobody else.
        card = await asyncio.to_thread(hub.session.card_for_moment, moment_id, profile)
        if card is None:
            raise HTTPException(status_code=404, detail="We could not find that moment.")
        return view.card_payload(card)

    @app.get("/api/match/recap")
    async def recap(persona: Persona = "casual", lang: Language = "en") -> dict[str, Any]:
        result = await hub.run_crew(hub.session.recap, ViewerProfile(persona=persona, language=lang))
        return result.model_dump(mode="json")

    @app.post("/api/match/seek", dependencies=limited)
    async def seek(body: SeekBody) -> dict[str, Any]:
        if not math.isfinite(body.clock_s):
            raise HTTPException(status_code=400, detail="Pick a time between kick-off and full time.")
        return await hub.seek(body.clock_s, body.period)

    @app.post("/api/match/speed", dependencies=limited)
    async def speed(body: SpeedBody) -> dict[str, Any]:
        return await hub.set_speed(body.speed_multiplier)

    @app.post("/api/match/reset", dependencies=limited)
    async def reset() -> dict[str, Any]:
        return await hub.reset()

    @app.get("/api/crew/status")
    async def crew_status() -> dict[str, Any]:
        return (await hub.run(hub.session.crew_status)).model_dump()

    @app.get("/api/crew/trace")
    async def crew_trace(limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, Any]]:
        traces = await hub.run(hub.session.crew_traces, limit)
        return [t.model_dump() for t in traces]

    @app.get("/api/auto-eventing")
    async def auto_eventing() -> dict[str, Any]:
        if hub.session.auto_eventing is None:
            raise HTTPException(status_code=404, detail="Auto-eventing is coming soon.")
        return hub.session.auto_eventing

    # --- WebSocket ---------------------------------------------------------------------------

    def _origin_ok(ws: WebSocket) -> bool:
        origin = ws.headers.get("origin")
        if origin is None:
            return True  # not a browser; browsers always send Origin
        return origin.rstrip("/") in ws_origins  # the Host header is never trusted for this

    @app.websocket("/ws/match")
    async def ws_match(ws: WebSocket) -> None:
        if not _origin_ok(ws) or hub._session is None:
            await ws.close(code=1008)
            return
        ip = ws.client.host if ws.client else "unknown"
        if not hub.reserve(ip):
            await ws.close(code=1008)
            return
        conn: Connection | None = None
        writer: asyncio.Task[None] | None = None
        try:
            await ws.accept()
            conn = Connection(ws, hub.clock, on_drop=hub.drop)
            hub.connections.add(conn)
            writer = conn.start()
            await _serve(ws, conn)
        except Exception:  # noqa: BLE001 - never leak details to the client
            logger.exception("websocket connection failed")
        finally:
            hub.release(ip)
            if conn is not None:
                hub.drop(conn)
                conn.close()
            if writer is not None and not writer.done():  # a dropped viewer's writer is already cancelled
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(writer, timeout=2)

    async def _serve(ws: WebSocket, conn: Connection) -> None:
        await hub.send_snapshots([conn])
        while not conn.closed:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            text = msg.get("text")
            if text is None:
                conn.error("Send actions as JSON text.")
                continue
            await _handle(conn, text)

    async def _handle(conn: Connection, text: str) -> None:
        if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
            conn.error("That message is too big. Actions must be under 4 KB.")
            return
        if not conn.limiter.allow():
            conn.error("Too many actions at once. Wait a moment and try again.")
            return
        try:
            raw = json.loads(text)
        except ValueError:
            conn.error('We could not read that message. Send JSON like {"action": "toggle_pause"}.')
            return
        name = raw.get("action") if isinstance(raw, dict) else None
        model = ACTION_MODELS.get(name) if isinstance(name, str) else None
        if model is None:
            conn.error("Unknown action. Use toggle_pause, set_speed, reset, seek, set_view or set_persona.")
            return
        try:
            action = model.model_validate(raw)
        except ValidationError:
            conn.error(ACTION_HELP[name])
            return
        try:
            await _dispatch(conn, name, action)
        except SessionError as exc:
            conn.error(str(exc))
        except HTTPException as exc:
            conn.error(str(exc.detail))
        except Exception:
            logger.exception("action %s failed", name)
            conn.error(OOPS)

    async def _dispatch(conn: Connection, name: str, action: _Action) -> None:
        if name == "toggle_pause":
            await hub.toggle_pause()
        elif name == "set_speed":
            assert isinstance(action, SetSpeed)
            await hub.set_speed(action.speed_multiplier)
        elif name == "reset":
            await hub.reset()
        elif name == "seek":
            assert isinstance(action, Seek)
            await hub.seek(action.clock_s, action.period)
        elif name in ("set_view", "set_persona"):
            if isinstance(action, SetPersona):
                changes: dict[str, Any] = {"persona": action.persona}
                if action.spotlight_player_id is not None:
                    changes["focus_player_id"] = action.spotlight_player_id
            else:
                changes = {k: getattr(action, k) for k in action.model_fields_set if k != "action"}
            _set_view(conn, changes)

    def _set_view(conn: Connection, changes: dict[str, Any]) -> None:
        session = hub.session
        team = changes.get("favourite_team")
        if team is not None and not session.is_known_team(team):
            conn.error("That club is not in this match.")
            return
        player = changes.get("focus_player_id")
        if player is not None and not session.is_known_player(player):
            conn.error("That player is not in this match.")
            return
        for key in ("persona", "language"):
            if key in changes and changes[key] is None:
                changes.pop(key)  # these always have a value
        conn.profile = conn.profile.model_copy(update=changes)
        conn.view_state = ViewerState()
        conn.send(view.message("PROFILE_CHANGED", conn.profile.model_dump()))
        conn.send(view.message("PERSONA_CHANGED", {"persona": conn.profile.persona}))

    # --- Built frontend ----------------------------------------------------------------------

    if serves_frontend:
        app.mount("/", StaticFiles(directory=static, html=True), name="static")

    return app


app = create_app()
