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
import threading
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.datastructures import MutableHeaders
from starlette.middleware.gzip import GZipMiddleware

from matchmind.ask.intents import ChipId
from matchmind.crew.contracts import (
    LANGUAGES,
    FocusMetric,
    Language,
    Persona,
    ViewerProfile,
)
from matchmind.crew.producer import ViewerState
from matchmind.dataset import catalog as dataset_catalog
from matchmind.dataset.dictionary import cached_dictionary
from matchmind.dataset.export import FORMATS as DATASET_FORMATS
from matchmind.dataset.export import TRACKING_HZ, TRACKING_MAX_WINDOW_S, TrackingWindow, export_parts
from matchmind.schema import PITCH_LENGTH_M, PITCH_WIDTH_M, SCHEMA_VERSION, Event

from . import reads, view
from . import session as session_mod
from .session import CUE_PAGE_MAX, MatchSession, SessionError, Tick, build_session
from .validation import validation_body

logger = logging.getLogger("pitchpulse.api")

MAX_MESSAGE_BYTES = 4096
MAX_CONNECTIONS = int(os.environ.get("MATCHMIND_MAX_CONNECTIONS", "200"))
MAX_CONN_PER_IP = int(os.environ.get("MATCHMIND_MAX_CONN_PER_IP", "20"))
SEND_QUEUE_BYTES = 4 * 1024 * 1024  # per connection; a viewer this far behind is dropped
# All send queues together, so viewers that stop reading cannot pin MAX_CONNECTIONS x 4 MB
# (the container has 1 GiB). Once it is spent, a viewer more than SEND_QUEUE_SHARE_BYTES
# behind is dropped; viewers that keep up (a few KB queued) are never dropped for it.
SEND_QUEUE_TOTAL_BYTES = int(os.environ.get("MATCHMIND_SEND_QUEUE_TOTAL_BYTES", str(192 * 1024 * 1024)))
SEND_QUEUE_SHARE_BYTES = 256 * 1024
JUMP_INTERVAL_S = 0.5  # at most one seek or reset per half second, for everyone
# When nobody has watched for this long, the next visitor starts a fresh match at kick-off
# and the default speed instead of landing at full time (docs/adr/0006-one-shared-match-clock.md).
# 0 turns it off. Never applies to a live stream.
IDLE_REWIND_S = float(os.environ.get("MATCHMIND_IDLE_REWIND_S", "300"))
# Pause and speed, shared by everyone: without it 20 connections from one address toggled
# pause about 190 times a second, froze the match and flooded every viewer. Also turns a
# double tap on pause into one change.
CONTROL_INTERVAL_S = 0.3
VIEW_BURST, VIEW_PER_SECOND = 3, 1.0  # set_view per connection
# Events of new cue-sheet compiling per playback step (shared by every viewer). An audience
# never seen before costs one pass over the match so far (about 2,000 events at full time);
# the rest wait a step or two (docs/CUE-SHEET.md).
COMPILE_BUDGET = 2500
POST_BURST, POST_PER_SECOND = 10, 2.0  # per client IP on the POST routes
# Per client IP on the GET routes that may call a paid service (moment cards and recaps).
# Room for the app's own bursts: re-voicing 12 cards after a language switch, 4 per split view.
GET_BURST, GET_PER_SECOND = 30, 3.0
# Per client IP on the other read routes (snapshot, players, stats, crew status...). Each
# builds a JSON payload; one address looping on them slowed every viewer on a single core
# (launch checks LC-1). The app polls these every few seconds, so this leaves wide room.
# /api/health stays open for the platform's probes.
READ_BURST, READ_PER_SECOND = 60, 10.0
IP_LIMITERS_MAX = 10_000
# Behind the Container Apps ingress the caller's address is the LAST X-Forwarded-For
# entry (the ingress appends what it saw); anything to its left is client-supplied.
TRUST_FORWARDED_FOR = os.environ.get("MATCHMIND_TRUST_FORWARDED_FOR", "false").strip().lower() in (
    "true",
    "1",
    "yes",
)
CLOSE_TRY_AGAIN = 1013  # WebSocket "try again later"
DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:3000"
OOPS = "Something went wrong on our side. Please try again."
TOO_FAST = "Jumping around too fast. Wait a moment and try again."
TOO_MANY = "Too many requests. Wait a moment and try again."
CONTROL_TOO_FAST = "Playback was just changed. Wait a moment and try again."
VIEW_TOO_FAST = "Changing the view too fast. Wait a moment and try again."
TOO_MANY_ACTIONS = "Too many actions at once. Wait a moment and try again."
LOADING = "The match is still loading. Try again in a moment."
NO_CLUB_HERE = "That club is not in this match."
NO_PLAYER_HERE = "That player is not in this match."

# Stable codes for the viewer-facing WebSocket errors, sent next to the English text so the
# app can show each one in the viewer's language (frontend src/i18n/toasts.ts). Anything
# not listed goes out as "other".
ERROR_CODES: dict[str, str] = {
    OOPS: "oops",
    TOO_FAST: "jump_too_fast",
    VIEW_TOO_FAST: "view_too_fast",
    CONTROL_TOO_FAST: "control_too_fast",
    TOO_MANY_ACTIONS: "too_many_actions",
    LOADING: "loading",
    NO_CLUB_HERE: "unknown_club",
    NO_PLAYER_HERE: "unknown_player",
    session_mod.MATCH_FINISHED: "match_finished",
    session_mod.BAD_SPEED: "bad_speed",
    session_mod.BAD_TIME: "bad_time",
    session_mod.NO_SUCH_HALF: "no_such_half",
    session_mod.NOT_PLAYED_YET: "not_played_yet",
    session_mod.AFTER_FULL_TIME: "after_full_time",
}

# Dataset downloads (synthetic, public): a few per client IP, at most two built at once.
EXPORT_BURST, EXPORT_PER_SECOND = 6, 0.2
EXPORT_CONCURRENCY = 2
EXPORT_CHUNK = 64 * 1024
DATASET_CACHE = "public, max-age=3600"
EXPORTS_BUSY = "Downloads are busy right now. Try again in a few seconds."

# Ask the studio (docs/ASK.md): bodies are tiny; questions over 200 characters get a
# plain refusal, anything past these caps a 400 or 413.
ASK_BODY_MAX = 2048
ASK_QUESTION_MAX = 1000
ASK_TOO_BIG = "That question is too long. Keep it under 200 characters."

T = TypeVar("T")


# --- Dataset export (docs/DATASET.md) ------------------------------------------------ begin


@lru_cache(maxsize=1)
def dataset_index() -> dict[str, Any]:
    """GET /api/dataset: every downloadable match, with its scenario and seed."""
    return {
        "synthetic": True,
        "note": "Synthetic matches from the PitchPulse engine. Invented clubs and players only.",
        "schema_version": SCHEMA_VERSION,
        "pitch": {"length_m": PITCH_LENGTH_M, "width_m": PITCH_WIDTH_M, "home_attacks": "+x"},
        "formats": list(DATASET_FORMATS),
        "tracking": {"hz": TRACKING_HZ, "max_window_s": TRACKING_MAX_WINDOW_S, "formats": ["zip"]},
        "scenarios": dict(dataset_catalog.SCENARIOS),
        "seeded": {
            "seed_start": dataset_catalog.SEED_START,
            "seed_end": dataset_catalog.SEED_START + dataset_catalog.API_SEED_COUNT - 1,
            "match_id": "MM-GEN-<seed, 5 digits>",
        },
        "matches": [e.as_dict() for e in dataset_catalog.api_entries()],
    }


@lru_cache(maxsize=6)
def dataset_export_bytes(
    match_id: str, fmt: str, window: tuple[int, float, float] | None
) -> tuple[str, str, bytes]:
    """One export, built whole (at most a few MB) so the slot is held only while building."""
    entry = dataset_catalog.find(match_id)
    if entry is None:
        raise KeyError(match_id)
    tracking = TrackingWindow(*window) if window else None
    name, media, chunks = export_parts(
        entry,
        dataset_catalog.load_match(entry),
        fmt,
        cached_dictionary(),
        Event.model_json_schema(),
        tracking,
    )
    return name, media, b"".join(chunks)


# --- Dataset export -------------------------------------------------------------------- end


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
    spoilers: bool | None = None


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
        f"language: {', '.join(LANGUAGES[:-1])} or {LANGUAGES[-1]}; "
        "focus metric: pressure, xg, pass_difficulty, top_speed or momentum."
    ),
    "set_persona": "Persona must be casual, tactical, fantasy or player_spotlight.",
}


class AskBody(BaseModel):
    """POST /api/ask: a typed question or a suggested chip id, never both."""

    model_config = ConfigDict(extra="forbid")
    question: str | None = Field(default=None, max_length=ASK_QUESTION_MAX)
    chip: ChipId | None = None
    lang: Language = "en"
    spoilers: bool = True


class SeekBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clock_s: float = Field(ge=0, le=10_000)
    period: Literal[1, 2] | None = None


class SpeedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speed_multiplier: Literal[1, 10, 60]


# --- Connections -----------------------------------------------------------------------------


def content_security_policy(origins: list[str], own: str | None = None) -> str:
    """CSP for the app pages: everything from this server, plus the configured origins.

    connect-src lists, each with its ws:/wss: twin, this server's public origin
    (MATCHMIND_PUBLIC_ORIGIN; spelled out because older browsers do not match 'self'
    for WebSockets) and the allow-list (a frontend built with VITE_API_URL talks to one
    of them). Never a bare ws:/wss: scheme, which would allow any WebSocket host. Fonts are
    bundled; React sets inline styles, so styles allow 'unsafe-inline' (scripts do not)."""
    extra: list[str] = []
    for o in [*([own] if own else []), *origins]:
        o = o.strip().rstrip("/")
        if o.startswith(("http://", "https://")) and all(c not in o for c in " ;'\"*"):
            extra += [o, "ws" + o[4:]]
    connect = " ".join(["'self'", *dict.fromkeys(extra)])
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        f"connect-src {connect}; "
        "img-src 'self' data:; "
        "media-src 'self'; "
        "font-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'none'"
    )


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


class SendBudget:
    """Bytes queued for sending across every connection (one per hub)."""

    def __init__(self, total: int | None = None) -> None:
        self.total = SEND_QUEUE_TOTAL_BYTES if total is None else total
        self.used = 0


class Connection:
    def __init__(
        self,
        ws: WebSocket,
        clock: Callable[[], float],
        on_drop: Callable[[Connection], None] | None = None,
        budget: SendBudget | None = None,
    ) -> None:
        self.ws = ws
        self.budget = budget
        self.profile = ViewerProfile()
        self.view_state = ViewerState()  # what the producer remembers for this viewer
        # set_view starts a new cue sheet: about one a second per viewer (bursts of 3, so
        # the join-time set_view plus a quick language or persona pick still go through).
        self.view_limiter = RateLimiter(burst=VIEW_BURST, per_second=VIEW_PER_SECOND, clock=clock)
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
        size = len(text)
        if self.queued_bytes + size > SEND_QUEUE_BYTES:
            self.overflow()
            return
        budget = self.budget
        if (
            budget is not None
            and budget.used + size > budget.total
            and self.queued_bytes + size > SEND_QUEUE_SHARE_BYTES
        ):
            self.overflow()  # memory is short and this viewer is far behind
            return
        self._charge(size)
        self.queue.put_nowait(text)

    def _charge(self, size: int) -> None:
        self.queued_bytes += size
        if self.budget is not None:
            self.budget.used += size

    def _release(self, size: int) -> None:
        size = min(size, self.queued_bytes)
        self.queued_bytes -= size
        if self.budget is not None:
            self.budget.used = max(0, self.budget.used - size)

    def error(self, text: str) -> None:
        self.send(view.message("ERROR", {"message": text, "code": ERROR_CODES.get(text, "other")}))

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.queue.put_nowait(None)

    def overflow(self) -> None:
        """The viewer cannot keep up: drop it for real rather than grow memory."""
        if self.closed:
            return
        self.closed = True
        self.drain_queue()
        if self.writer_task is not None:
            self.writer_task.cancel()
        if self._on_drop is not None:
            self._on_drop(self)
        self._closer = asyncio.get_running_loop().create_task(self._close_socket(CLOSE_TRY_AGAIN))

    def drain_queue(self) -> None:
        """Empty the queue and give its bytes back to the shared budget."""
        while not self.queue.empty():
            self.queue.get_nowait()
        self._release(self.queued_bytes)

    async def _close_socket(self, code: int) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.ws.close(code=code), timeout=2)

    async def writer(self) -> None:
        while True:
            text = await self.queue.get()
            if text is None:
                break
            self._release(len(text))
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
        self._last_control: float | None = None
        self._slots = 0  # WebSocket slots reserved (before accept)
        self._idle_since: float | None = None  # when the last viewer left (None: someone is here)
        self._slots_per_ip: dict[str, int] = {}
        self.send_budget = SendBudget()

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
        if conn in self.connections:
            self.connections.discard(conn)
            if not self.connections:
                self._idle_since = self.clock()

    def join(self, conn: Connection) -> bool:
        """Add a viewer. Returns True when they are the first viewer after the match sat
        unwatched for IDLE_REWIND_S: the caller then rewinds to kick-off for them."""
        first = not self.connections
        idle = self._idle_since
        self.connections.add(conn)
        self._idle_since = None
        if not first or idle is None or IDLE_REWIND_S <= 0:
            return False
        return self.clock() - idle >= IDLE_REWIND_S

    async def rewind_for_new_visitor(self) -> None:
        """Kick-off at the default speed, before the new viewer's first snapshot. Only runs
        when nobody else is watching, so no one's match moves under them."""
        session = self.session
        if not session.rewindable:
            return
        async with self._crew_lock:
            if len(self.connections) > 1:
                return
            await self.run(session.reset)

    @property
    def session(self) -> MatchSession:
        if self._session is None:
            raise HTTPException(status_code=503, detail=LOADING)
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

    def _new_sheets(self, profiles: list[ViewerProfile], upto: int | None) -> list[bool]:
        """Which of these audiences get their cue sheet compiled now. Compiling is
        incremental and shared per profile, but an audience never seen before costs a pass
        over the match so far: at most COMPILE_BUDGET events of that work per step (always
        at least one audience), the rest wait for the next step, so many viewers changing
        view at once cannot hold the crew lock and stall playback."""
        budget = COMPILE_BUDGET
        out: list[bool] = []
        for profile in profiles:
            cost = self.session.compile_cost(profile, upto)
            ok = cost == 0 or budget == COMPILE_BUDGET or cost <= budget
            if ok:
                budget -= cost
            out.append(ok)
        return out

    def _snapshot_messages(self, profiles: list[ViewerProfile]) -> tuple[list[ViewerState], list[dict]]:
        """Fresh producer memory and cue sheet per viewer (compiled up to now, shared
        between viewers with the same profile), and their INITIAL_SNAPSHOT. A viewer over
        this step's compile budget gets `cue_sheet: null` and their sheet on a later tick."""
        states: list[ViewerState] = []
        for profile, now in zip(profiles, self._new_sheets(profiles, None), strict=True):
            states.append(self.session.viewer_state(profile) if now else ViewerState())
        messages = []
        for profile, state in zip(profiles, states, strict=True):
            data = view.snapshot_payload(self.session, profile, state)
            data["recent_events"] = view.recent_events_payload(self.session, profile)
            messages.append(view.message("INITIAL_SNAPSHOT", data))
            state.cue_active = None  # the snapshot carried it
        return states, messages

    async def send_snapshots(self, conns: list[Connection]) -> None:
        async with self._crew_lock:
            await self._send_snapshots(conns)

    async def _send_snapshots(self, conns: list[Connection]) -> None:
        """Caller holds the crew lock."""
        conns = [c for c in conns if not c.closed]
        profiles = [c.profile.model_copy() for c in conns]
        for conn in conns:
            conn.view_state = ViewerState()
        states, messages = await asyncio.to_thread(self._snapshot_messages, profiles)
        for conn, state, msg in zip(conns, states, messages, strict=True):
            conn.view_state = state
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
        states = [c.view_state for c in conns]
        fresh = [i for i, s in enumerate(states) if s.cues is None]
        allowed = self._new_sheets([profiles[i] for i in fresh], ticks[0].index)
        for i, now in zip(fresh, allowed, strict=True):
            if not now:
                continue  # over this step's budget: cards as usual, the sheet starts next step
            # New profile: start its sheet where these ticks begin. A set_view that landed
            # while this step was playing has replaced the connection's state and profile;
            # then this sheet (for the old profile) is used for this batch only.
            states[i] = session.viewer_state(profiles[i], ticks[0].index)
            if conns[i].profile == profiles[i] and conns[i].view_state.cues is None:
                conns[i].view_state = states[i]
        held: list[list[dict]] = [[] for _ in conns]  # catch-up cards from a withheld tick
        for tick in ticks:
            tick = session.crew_tick(tick)
            shared = view.tick_shared(tick)
            for i, profile in enumerate(profiles):
                state = states[i]
                cards = session.cards_for(tick.bundles, profile, state, tick)
                data = dict(shared, cards=[view.card_payload(c) for c in cards])
                cues = view.cues_message(state, session.tick_cues(tick, cards, state))
                if not profile.spoilers:  # catch-up mode: no result, no cue sheet (docs/PERSONALISATION.md)
                    if held[i]:
                        data["cards"] = held[i] + data["cards"]
                        held[i] = []
                    free = view.spoiler_free_tick(session, data)
                    if free is None:  # a withheld event (VAR review, kick-off): its cards ride the next tick
                        held[i] = data["cards"]  # filtered and scrubbed once, with that tick
                        continue
                    out[i].append(view.message("MATCH_TICK", free))
                    continue
                out[i].append(view.message("MATCH_TICK", data))
                if cues is not None:
                    out[i].append(cues)
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
            if await self.run(self._session.poll_live):
                # A live match has just started on the stream: everyone starts afresh.
                self.broadcast(view.message("MATCH_RESET", {}))
                await self._send_snapshots(conns)
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
        session = self.session
        self._claim_control()
        await self.run(session.toggle_pause)
        return self._announce_playback()

    async def set_speed(self, speed: int) -> dict[str, Any]:
        session = self.session
        if session.speed == speed:
            return session.playback()  # nothing changes: a retry is answered, not broadcast
        self._claim_control()
        await self.run(session.set_speed, speed)
        return self._announce_playback()

    def _claim_control(self) -> None:
        """One shared throttle for pause and speed (WebSocket and REST alike)."""
        now = self.clock()
        if self._last_control is not None and now - self._last_control < CONTROL_INTERVAL_S:
            raise HTTPException(status_code=429, detail=CONTROL_TOO_FAST)
        self._last_control = now

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


class _StaticCache:
    """Cache headers for the built app: Vite's hashed files under /assets/ never change, so
    they are cached for a year; everything else (index.html) is re-checked each visit."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        immutable = str(scope.get("path", "")).startswith("/assets/")

        async def send_with_cache(message: Any) -> None:
            if message["type"] == "http.response.start" and message.get("status") == 200:
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "public, max-age=31536000, immutable" if immutable else "no-cache"
            await send(message)

        await self.app(scope, receive, send_with_cache)


def _api_docs_from_env(default: bool) -> bool:
    raw = os.environ.get("MATCHMIND_API_DOCS", "").strip().lower()
    if not raw:
        return default
    return raw in ("true", "1", "yes", "on")


def _mcp_enabled_from_env() -> bool:
    raw = os.environ.get("MATCHMIND_MCP_ENABLED", "true").strip().lower()
    return raw not in ("false", "0", "no", "off")


def client_ip(conn: Request | WebSocket) -> str:
    """The address limits and connection caps are keyed by. Never the leftmost
    X-Forwarded-For entry: a caller can put anything there."""
    if TRUST_FORWARDED_FOR:
        last = conn.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        if last:
            return last[:64]
    return conn.client.host if conn.client else "unknown"


JSON_ONLY = "Send this request as JSON (Content-Type: application/json)."


def _is_json(request: Request) -> bool:
    return request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json"


async def json_only(request: Request) -> None:
    """415 for a state-changing POST that is not JSON (see `limited` in create_app)."""
    if not _is_json(request):
        raise HTTPException(status_code=415, detail=JSON_ONLY)


def create_app(
    session: MatchSession | None = None,
    session_factory: Callable[[], MatchSession] = build_session,
    tick_interval: float | None = 0.1,
    allowed_origins: list[str] | None = None,
    static_dir: str | Path | None = None,
    clock: Callable[[], float] = time.monotonic,
    public_origin: str | None = None,
    mcp_enabled: bool | None = None,
    api_docs: bool | None = None,
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
            # The MCP endpoint's session manager lives exactly as long as the app.
            async with mcp_http.run() if mcp_http is not None else contextlib.nullcontext():
                yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    # /docs and /openapi.json: on for local development, off where this server also serves
    # the app (the deployed container). MATCHMIND_API_DOCS=true|false overrides either way.
    docs_on = api_docs if api_docs is not None else _api_docs_from_env(default=not serves_frontend)
    app = FastAPI(
        title="PitchPulse match API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )
    app.state.hub = hub
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    csp = content_security_policy(origins, own or None)
    hsts = own.startswith("https://")

    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[[Request], Awaitable[Any]]):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        path = request.url.path
        if not path.startswith("/api/"):
            response.headers.setdefault("Content-Security-Policy", csp)
        if hsts:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # Downloads of the synthetic dataset may be cached publicly; nothing else under /api.
        public = path.startswith("/api/dataset") and response.status_code == 200
        if path.startswith("/api/") and not public:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def _bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(validation_body(exc.errors()), status_code=400)

    @app.exception_handler(SessionError)
    async def _session_error(request: Request, exc: SessionError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def _crash(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("request failed: %s", request.url.path)
        return JSONResponse({"detail": OOPS}, status_code=500)

    # --- REST --------------------------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    def ip_limit(burst: int, per_second: float) -> Callable[[Request], None]:
        """A simple per-client-IP token bucket (its own table per route group)."""
        ip_limiters: OrderedDict[str, RateLimiter] = OrderedDict()

        def check(request: Request) -> None:
            ip = client_ip(request)
            limiter = ip_limiters.get(ip)
            if limiter is None:
                limiter = ip_limiters[ip] = RateLimiter(burst=burst, per_second=per_second, clock=clock)
                while len(ip_limiters) > IP_LIMITERS_MAX:
                    ip_limiters.popitem(last=False)
            ip_limiters.move_to_end(ip)
            if not limiter.allow():
                raise HTTPException(status_code=429, detail=TOO_MANY)

        return check

    # State-changing POSTs take JSON only: a plain cross-site form (urlencoded, multipart,
    # text/plain) needs no CORS preflight, so without this any page could reset the match.
    limited = [Depends(json_only), Depends(ip_limit(POST_BURST, POST_PER_SECOND))]
    # One bucket per client IP for every GET that may reach a paid path (moment cards,
    # recaps) and for MCP, so the REST routes and the MCP tools cannot double the burst.
    get_limit = ip_limit(GET_BURST, GET_PER_SECOND)
    limited_get = [Depends(get_limit)]
    limited_read = [Depends(ip_limit(READ_BURST, READ_PER_SECOND))]

    @app.get("/api/teams", dependencies=limited_read)
    async def teams() -> dict[str, Any]:
        return await reads.teams(hub)

    @app.get("/api/match/snapshot", dependencies=limited_read)
    async def snapshot(spoilers: bool = True) -> dict[str, Any]:
        return await reads.snapshot(hub, spoilers)

    @app.get("/api/match/players", dependencies=limited_read)
    async def players() -> list[dict[str, Any]]:
        return await reads.players(hub)

    @app.get("/api/match/bookmarks", dependencies=limited_read)
    async def bookmarks() -> list[dict[str, Any]]:
        return reads.bookmarks(hub)

    @app.get("/api/match/moment/{moment_id}", dependencies=limited_get)
    async def moment(
        moment_id: str,
        persona: Persona = "casual",
        lang: Language = "en",
        favourite_team: str | None = Query(default=None, max_length=32),
    ) -> dict[str, Any]:
        return await reads.moment_card(hub, moment_id, persona, lang, favourite_team)

    # --- Claim audit (trust layer, docs/TRUST.md) -----------------------------------------------
    @app.get("/api/match/moment/{moment_id}/audit", dependencies=limited_get)
    async def moment_audit(moment_id: str) -> dict[str, Any]:
        """Facts, source events, evidence, every rendering's claims and fact-check,
        parity and trace for one moment. Same rate limit as the moment route; never
        calls a paid model (template sweep plus the live crew's cached cards)."""
        if len(moment_id) > 80:
            raise HTTPException(status_code=404, detail="We could not find that moment.")
        audit = await asyncio.to_thread(hub.session.moment_audit, moment_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="We could not find that moment.")
        return audit.model_dump(mode="json")

    # --- end claim audit -----------------------------------------------------------------------

    @app.get("/api/match/recap", dependencies=limited_get)
    async def recap(
        persona: Persona = "casual", lang: Language = "en", spoilers: bool = True
    ) -> dict[str, Any]:
        return await reads.recap(hub, persona, lang, spoilers)

    @app.get("/api/match/cue-sheet", dependencies=limited_get)
    async def cue_sheet(
        persona: Persona = "casual",
        lang: Language = "en",
        favourite_team: str | None = Query(default=None, max_length=32),
        since_seq: int = Query(default=0, ge=0, le=1_000_000),
        limit: int = Query(default=CUE_PAGE_MAX, ge=1, le=CUE_PAGE_MAX),
    ) -> dict[str, Any]:
        return await reads.cue_sheet(hub, persona, lang, favourite_team, since_seq, limit)

    # --- Ask the studio (docs/ASK.md) ---------------------------------------------------------
    @app.post("/api/ask", dependencies=limited_get)
    async def ask(request: Request) -> dict[str, Any]:
        """One question about the match, answered from the stats engine as of the playback
        clock. Shares the per-IP bucket of the paid-path GET routes and MCP."""
        # JSON only: a form or text/plain POST is a "simple" cross-site request a browser
        # sends from any page without a CORS preflight.
        if not _is_json(request):
            raise HTTPException(status_code=415, detail="Send the question as JSON.")
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > ASK_BODY_MAX:
            raise HTTPException(status_code=413, detail=ASK_TOO_BIG)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > ASK_BODY_MAX:
                raise HTTPException(status_code=413, detail=ASK_TOO_BIG)
        try:
            body = AskBody.model_validate_json(bytes(raw))
        except ValidationError as exc:
            return JSONResponse(validation_body(exc.errors()), status_code=400)  # type: ignore[return-value]
        if (body.question is None) == (body.chip is None):
            raise HTTPException(status_code=400, detail="Send a question or a chip.")
        return await reads.ask(hub, body.question, body.chip, body.lang, body.spoilers, client_ip(request))

    # --- end ask the studio -------------------------------------------------------------------

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

    @app.get("/api/crew/status", dependencies=limited_read)
    async def crew_status() -> dict[str, Any]:
        return await reads.crew_status(hub)

    @app.get("/api/languages", dependencies=limited_read)
    async def languages() -> dict[str, Any]:
        return await reads.languages(hub)

    @app.get("/api/crew/trace", dependencies=limited_read)
    async def crew_trace(limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, Any]]:
        return await reads.crew_traces(hub, limit)

    # --- Metric registry and basic stats (docs/METRICS.md) -----------------------------------

    @app.get("/api/metrics", dependencies=limited_read)
    async def metric_registry() -> dict[str, Any]:
        return reads.metric_registry()

    @app.get("/api/match/stats/basic", dependencies=limited_read)
    async def basic_stats(spoilers: bool = True) -> dict[str, Any]:
        return await reads.basic_stats(hub, spoilers)

    # --- end metric registry and basic stats ----------------------------------------------------

    @app.get("/api/auto-eventing", dependencies=limited_read)
    async def auto_eventing() -> dict[str, Any]:
        return reads.auto_eventing(hub)

    # --- Dataset export and match source (docs/DATASET.md) ------------------------ begin
    # Read-only downloads of synthetic data. There is deliberately no upload route: an
    # external feed is a file the operator plays with matchmind-ingest or
    # MATCHMIND_MATCH_FILE (CLAUDE.md upload rules; docs/DATASET.md).

    export_limited = [Depends(ip_limit(EXPORT_BURST, EXPORT_PER_SECOND))]
    export_slots = threading.BoundedSemaphore(EXPORT_CONCURRENCY)

    @app.get("/api/dataset", dependencies=limited_get)
    async def dataset() -> JSONResponse:
        data = await asyncio.to_thread(dataset_index)
        return JSONResponse(data, headers={"Cache-Control": DATASET_CACHE})

    @app.get("/api/dataset/export", dependencies=export_limited)
    async def dataset_export(
        match_id: str = Query(min_length=3, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9-]+$"),
        format: Literal["jsonl", "csv", "zip"] = "zip",
        tracking_period: int | None = Query(default=None, ge=1, le=2),
        tracking_from: float | None = Query(default=None, ge=0, le=7200),
        tracking_to: float | None = Query(default=None, ge=0, le=7200),
    ) -> StreamingResponse:
        if dataset_catalog.find(match_id) is None:
            raise HTTPException(
                status_code=404, detail="We do not have that match. GET /api/dataset lists them."
            )
        window: tuple[int, float, float] | None = None
        given = [v is not None for v in (tracking_period, tracking_from, tracking_to)]
        if any(given):
            if not all(given):
                raise HTTPException(
                    status_code=400,
                    detail="A tracking sample needs tracking_period, tracking_from and tracking_to.",
                )
            assert tracking_period is not None and tracking_from is not None and tracking_to is not None
            if format != "zip":
                raise HTTPException(
                    status_code=400, detail="The tracking sample comes in the zip format only."
                )
            window = (tracking_period, round(tracking_from, 1), round(tracking_to, 1))
            try:
                TrackingWindow(*window)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Check the tracking window: {exc}.") from None
        if not export_slots.acquire(blocking=False):
            raise HTTPException(status_code=429, detail=EXPORTS_BUSY)
        try:
            name, media, body = await asyncio.to_thread(dataset_export_bytes, match_id, format, window)
        finally:
            export_slots.release()

        def chunks():
            for i in range(0, len(body), EXPORT_CHUNK):
                yield body[i : i + EXPORT_CHUNK]

        return StreamingResponse(
            chunks(),
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "Content-Length": str(len(body)),
                "Cache-Control": DATASET_CACHE,
            },
        )

    @app.get("/api/source", dependencies=limited_read)
    async def source() -> dict[str, Any]:
        return await hub.run(hub.session.source_status)

    # --- Dataset export and match source ------------------------------------------------ end

    # --- WebSocket ---------------------------------------------------------------------------

    def _origin_ok(ws: WebSocket) -> bool:
        origin = ws.headers.get("origin")
        if origin is None:
            return True  # not a browser; browsers always send Origin
        return origin.rstrip("/") in ws_origins  # the Host header is never trusted for this

    @app.websocket("/ws/match")
    async def ws_match(ws: WebSocket) -> None:
        profile = _view_from_url(ws)
        if not _origin_ok(ws) or hub._session is None or profile is None:
            await ws.close(code=1008)
            return
        ip = client_ip(ws)
        if not hub.reserve(ip):
            await ws.close(code=1008)
            return
        conn: Connection | None = None
        writer: asyncio.Task[None] | None = None
        try:
            await ws.accept()
            conn = Connection(ws, hub.clock, on_drop=hub.drop, budget=hub.send_budget)
            conn.profile = profile  # catch-up from the first frame: the snapshot never has the score
            rewind = hub.join(conn)
            writer = conn.start()
            if rewind:
                await hub.rewind_for_new_visitor()
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
            if conn is not None:
                conn.drain_queue()  # whatever a stuck writer left behind goes back to the budget

    def _view_from_url(ws: WebSocket) -> ViewerProfile | None:
        """The viewer's starting choices from `?spoilers=0|1&persona=&lang=` (all optional),
        or None when one is not valid or given twice (the handshake is refused)."""
        params = ws.query_params
        keys = {"spoilers": "spoilers", "persona": "persona", "lang": "language"}
        changes: dict[str, Any] = {}
        for key, field in keys.items():
            values = params.getlist(key)
            if not values:
                continue
            if len(values) > 1:
                return None
            changes[field] = values[0]
        if "spoilers" in changes:
            flag = {"0": False, "false": False, "1": True, "true": True}.get(changes["spoilers"])
            if flag is None:
                return None
            changes["spoilers"] = flag
        try:
            return ViewerProfile.model_validate(changes)
        except ValidationError:
            return None

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
            conn.error(TOO_MANY_ACTIONS)
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
            before = conn.profile.spoilers
            language_before = conn.profile.language
            _set_view(conn, changes)
            if conn.profile.spoilers != before or conn.profile.language != language_before:
                # Catch-up turned on or the viewer tapped reveal: what is on screen changes at once.
                # A new language also brings the jump list's titles in that language.
                await hub.send_snapshots([conn])

    def _set_view(conn: Connection, changes: dict[str, Any]) -> None:
        session = hub.session
        # An unknown club or player (e.g. a choice saved during another match) is left out
        # with a message; the rest still applies, so catch-up mode is never lost with it.
        team = changes.get("favourite_team")
        if team is not None and not session.is_known_team(team):
            conn.error(NO_CLUB_HERE)
            changes.pop("favourite_team")
        player = changes.get("focus_player_id")
        if player is not None and not session.is_known_player(player):
            conn.error(NO_PLAYER_HERE)
            changes.pop("focus_player_id")
        if not changes:
            return
        for key in ("persona", "language", "spoilers"):
            if key in changes and changes[key] is None:
                changes.pop(key)  # these always have a value
        if not conn.view_limiter.allow():
            conn.error(VIEW_TOO_FAST)
            return
        conn.profile = conn.profile.model_copy(update=changes)
        conn.view_state = ViewerState()
        conn.send(view.message("PROFILE_CHANGED", conn.profile.model_dump()))
        conn.send(view.message("PERSONA_CHANGED", {"persona": conn.profile.persona}))

    # --- MCP (Streamable HTTP at /mcp; docs/MCP.md) -----------------------------------------
    # Read-only tools on this same live session, through the same accessors as the REST
    # routes (api/reads.py). The REST GET routes' per-IP bucket, Origin and Host checks from the
    # allow-list above, 16 KB bodies, one request per POST. MATCHMIND_MCP_ENABLED=false
    # turns it off.
    mcp_http = None
    if mcp_enabled if mcp_enabled is not None else _mcp_enabled_from_env():
        from matchmind.mcp import MCPHttpEndpoint, build_server
        from matchmind.mcp.server import allowed_hosts

        mcp_origins = sorted(ws_origins | ({own} if own and own != "*" else set()))
        mcp_http = MCPHttpEndpoint(
            build_server(hub),
            allowed_origins=sorted(ws_origins),
            hosts=allowed_hosts(mcp_origins),
            rate_check=get_limit,  # shared with the REST GET routes
        )
        app.add_route("/mcp", mcp_http, methods=["POST"], include_in_schema=False)
    # --- end MCP ------------------------------------------------------------------------------

    # --- Built frontend ----------------------------------------------------------------------

    if serves_frontend:
        # Compressed, and the hashed build files cached for good, so a phone on a slow network
        # gets the first screen sooner (the page itself is re-checked on every visit).
        app.mount(
            "/",
            GZipMiddleware(_StaticCache(StaticFiles(directory=static, html=True)), minimum_size=1024),
            name="static",
        )

    return app


app = create_app()
