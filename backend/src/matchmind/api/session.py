"""One shared demo match session: playback, seek, bookmarks and recap.

Framework-free on purpose: the FastAPI layer (`app.py`) only moves messages in
and out. Time comes from an injectable clock so tests never sleep.

Playback runs on a *timeline* rather than the raw match clock. The match clock
restarts at 45:00 (2700 s) for the second half while first-half stoppage time
runs past it, so `clock_s` alone is not monotonic. The timeline glues the
periods end to end with no half-time wait.

Speed: `speed_multiplier` is 1, 10 or 60. One real second plays
`BASE_RATE x speed_multiplier` match seconds. BASE_RATE defaults to 10 (env
MATCHMIND_BASE_RATE), so 1x plays the 90 minutes in about 9 real minutes, 10x in
about 54 seconds and 60x in about 9 seconds.

Source: the match comes from a file (MATCHMIND_MATCH_FILE, default the bundled
demo; JSON lines in our schema or the generic CSV, both through the strict
checks in `matchmind.ingest`) or, with MATCHMIND_SOURCE=eventhubs, from the live
Event Hubs stream the simulator publishes. A live session grows as events
arrive (`append`) and only ends at match_end.

Seek replays stats from the nearest checkpoint (a copy of the stats engine taken
every CHECKPOINT_EVERY events at load), so a jump costs at most that many
events of work. Moments before the jump point come from the load-time pass, so
the recap after a jump is the same as after watching straight through.
"""

from __future__ import annotations

import copy
import logging
import os
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from matchmind.crew.contracts import (
    CrewStatus,
    CrewTrace,
    Moment,
    MomentBundle,
    OverlayCard,
    Recap,
    ViewerProfile,
)
from matchmind.crew.llm import ai_enabled
from matchmind.crew.producer import ViewerState
from matchmind.crew.translator import TRANSIENT_REASONS
from matchmind.schema import Event, EventType
from matchmind.simulator.teams import Team, get_team
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

logger = logging.getLogger("pitchpulse.session")

SPEEDS: tuple[int, ...] = (1, 10, 60)
DEFAULT_SPEED = 10
DEFAULT_BASE_RATE = 10.0
RECENT_BUNDLES = 8
_RECAP_CACHE_SIZE = 32
CHECKPOINT_EVERY = 200
# Pitch tags and pass ratings are shown on ticks but would flood "jump to moment".
NO_BOOKMARK_KINDS = frozenset({"speed_burst", "rocket_shot", "distance_milestone", "hard_pass"})

BACKEND_DIR = Path(__file__).resolve().parents[3]
_DEMO = Path("data") / "matches" / "MM-DEMO-001.jsonl"


def _default_match_file() -> Path:
    """The demo match next to the source tree, or under the working directory
    (a non-editable install puts this module in site-packages)."""
    for base in (BACKEND_DIR, Path.cwd(), Path.cwd() / "backend"):
        if (base / _DEMO).is_file():
            return base / _DEMO
    return BACKEND_DIR / _DEMO


DEFAULT_MATCH_FILE = _default_match_file()


class SessionError(ValueError):
    """A request the session cannot carry out. The message is plain words for viewers."""


# --- What the session needs from the stats engine and the crew -------------------------------


class LiveFeedLike(Protocol):
    """A live source (matchmind.ingest.live.LiveFeed): checked events in seq order."""

    def drain(self, limit: int = ...) -> list[Event]: ...
    @property
    def exhausted(self) -> bool: ...
    def status(self) -> dict[str, Any]: ...


class StatsEngineLike(Protocol):
    def process(self, event: Event) -> EventMetrics: ...
    def snapshot(self) -> MatchStateSnapshot: ...
    def players(self) -> Mapping[str, PlayerStats]: ...
    def changed_players(self) -> list[PlayerStats]: ...


class CrewLike(Protocol):
    def process(
        self,
        event: Event,
        metrics: EventMetrics,
        snapshot: MatchStateSnapshot,
        players: Mapping[str, PlayerStats],
    ) -> list[MomentBundle]: ...
    def render(self, bundle: MomentBundle, profile: ViewerProfile) -> OverlayCard | None: ...
    def cards_for(
        self, bundles: list[MomentBundle], profile: ViewerProfile, state: ViewerState
    ) -> list[OverlayCard]: ...
    def metric_alerts(
        self,
        event: Event,
        metrics: EventMetrics,
        snapshot: MatchStateSnapshot,
        players: Mapping[str, PlayerStats],
        profile: ViewerProfile,
        state: ViewerState,
    ) -> list[OverlayCard]: ...
    def recap(
        self,
        snapshot: MatchStateSnapshot,
        players: Mapping[str, PlayerStats],
        profile: ViewerProfile,
        moments: list[Moment] | None = None,
    ) -> Recap: ...
    def translate_recap(
        self,
        english: Recap,
        moments: list[Moment],
        profile: ViewerProfile,
        snapshot: MatchStateSnapshot,
    ) -> Recap: ...
    def status(self) -> CrewStatus: ...
    def traces(self, limit: int) -> list[CrewTrace]: ...
    def reset(self) -> None: ...
    def restore(self, bundles: list[MomentBundle]) -> None: ...


StatsFactory = Callable[[str, str, str], StatsEngineLike]
CrewFactory = Callable[[dict[str, Team]], CrewLike]


@dataclass(frozen=True)
class Engines:
    """Builds fresh stats engines and crews. The only place the real ones are named."""

    stats: StatsFactory
    crew: CrewFactory
    bookmark_crew: CrewFactory | None = None  # template-only crew for the whole-match pre-pass


def real_engines() -> Engines:
    """The real stats engine and crew, or a clear error if they are not installed yet."""
    try:
        from matchmind.stats.state import StatsEngine
    except ImportError as exc:
        raise RuntimeError(
            "The stats engine (matchmind.stats.state.StatsEngine) is not available in this build."
        ) from exc
    try:
        from matchmind.crew.crew import Crew
    except ImportError as exc:
        raise RuntimeError(
            "The studio crew (matchmind.crew.crew.Crew) is not available in this build."
        ) from exc
    from matchmind.crew.llm import TemplateLLM
    from matchmind.crew.translator import OffTranslator

    llm = live_llm()
    translator = live_translator()
    # The pre-pass over the whole match always runs in template mode and never
    # translates, so loading a match never spends on paid AI calls. (llm=None or
    # translator=None would mean "whatever the switch says".)
    return Engines(
        stats=StatsEngine,
        crew=lambda teams: Crew(teams, llm=llm, translator=translator),
        bookmark_crew=lambda teams: Crew(teams, llm=TemplateLLM(), translator=OffTranslator()),
    )


def live_llm() -> Any:
    """The paid model client only when MATCHMIND_AI_ENABLED is on; otherwise None (templates).

    MATCHMIND_LLM_PROVIDER picks Azure OpenAI (default) or Foundry Agent Service; the
    client reads its own settings. If it cannot be built, the crew stays on templates
    rather than stopping the match.
    """
    if not ai_enabled():
        return None
    try:
        from matchmind.crew.llm import make_llm

        return make_llm()
    except Exception:  # noqa: BLE001 - optional, paid add-on
        logger.warning("MATCHMIND_AI_ENABLED is on but the model client could not start; using templates")
        return None


def live_translator() -> Any:
    """Azure AI Translator only when MATCHMIND_TRANSLATOR_ENABLED and MATCHMIND_AI_ENABLED
    are both on; otherwise the off mode (world languages shown in English)."""
    from matchmind.crew.translator import AzureTranslator, OffTranslator, translator_enabled

    if not translator_enabled():
        return OffTranslator()
    return AzureTranslator()  # reads AZURE_TRANSLATOR_ENDPOINT; builds no client until first use


# --- Results handed to the transport ----------------------------------------------------------


@dataclass(frozen=True)
class Bookmark:
    moment_id: str
    kind: str
    match_clock: str
    clock_s: float
    period: int
    title: str


@dataclass(frozen=True)
class Tick:
    """Everything that happened when one event was played."""

    event: Event
    metrics: EventMetrics
    snapshot: MatchStateSnapshot
    players_changed: list[PlayerStats]
    bundles: list[MomentBundle]
    score_home: int
    score_away: int
    is_last: bool
    # Player stats as they were after this event (a copy), for crew work done later.
    players: Mapping[str, PlayerStats] | None = None


@dataclass
class _Live:
    stats: StatsEngineLike
    next_index: int = 0
    metrics: EventMetrics | None = None
    snapshot: MatchStateSnapshot | None = None
    recent: deque[MomentBundle] = field(default_factory=lambda: deque(maxlen=RECENT_BUNDLES))
    score_home: int = 0
    score_away: int = 0


def load_match_feed(path: str | Path | None = None) -> Any:
    """The match file (MATCHMIND_MATCH_FILE or the bundled demo), checked by the ingest
    adapter. MATCHMIND_ROSTER_FILE adds invented clubs; MATCHMIND_FEED_MAPPING maps a CSV."""
    from matchmind.ingest.errors import IngestError
    from matchmind.ingest.feed import load_feed

    path = Path(path or os.environ.get("MATCHMIND_MATCH_FILE") or DEFAULT_MATCH_FILE)
    if not path.is_file():
        raise RuntimeError(f"Match file not found: {path}")
    try:
        return load_feed(
            path,
            roster=os.environ.get("MATCHMIND_ROSTER_FILE") or None,
            mapping=os.environ.get("MATCHMIND_FEED_MAPPING") or None,
        )
    except IngestError as exc:
        raise RuntimeError(f"{path.name} cannot be played: {exc}") from None


def load_events(path: str | Path | None = None) -> list[Event]:
    return load_match_feed(path).events


def _timeline(events: list[Event]) -> list[float]:
    """Monotonic playback seconds: periods glued end to end."""
    out: list[float] = []
    _extend_timeline(out, [], events)
    return out


def _extend_timeline(tl: list[float], before: list[Event], new: list[Event]) -> None:
    """Append the playback seconds of `new`, which follow `before` (whose seconds are in `tl`)."""
    last_tl = tl[-1] if tl else 0.0
    prev = before[-1] if before else None
    offset = (last_tl - prev.clock_s) if prev is not None else 0.0
    # Within a period the offset is constant; recover it from the last event.
    for e in new:
        if prev is not None and e.period != prev.period:
            offset = last_tl - e.clock_s
        tl_e = max(last_tl, e.clock_s + offset)
        tl.append(tl_e)
        last_tl, prev = tl_e, e


class MatchSession:
    """The single shared match. Not thread-safe: callers serialise access."""

    def __init__(
        self,
        events: list[Event],
        teams: dict[str, Team] | None = None,
        engines: Engines | None = None,
        clock: Callable[[], float] = time.monotonic,
        base_rate: float | None = None,
        auto_eventing: dict[str, Any] | None = None,
        live_feed: LiveFeedLike | None = None,
        source: dict[str, Any] | None = None,
    ) -> None:
        if not events or events[0].type != EventType.MATCH_START:
            raise ValueError("A match needs events starting with match_start")
        if engines is None:
            raise ValueError("engines are required; use build_session() for the real ones")
        self.events = events
        self.match_id = events[0].match_id
        self.home_id = str(events[0].details["home"])
        self.away_id = str(events[0].details["away"])
        self.teams = teams or {self.home_id: get_team(self.home_id), self.away_id: get_team(self.away_id)}
        self._engines = engines
        self._clock = clock
        self.base_rate = float(base_rate or os.environ.get("MATCHMIND_BASE_RATE") or DEFAULT_BASE_RATE)
        self.auto_eventing = auto_eventing
        self._feed = live_feed
        self.consumer: Any = None  # the live consumer, when there is one (kept alive with the session)
        self._source = source or {"source": "eventhubs" if live_feed is not None else "file"}
        # A live match stays open (not ended at its last event) until match_end arrives.
        self._open = live_feed is not None and events[-1].type != EventType.MATCH_END
        self._tl = _timeline(events)
        self._period_starts = self._first_clock_per_period()
        self._player_ids = {p.player_id for t in self.teams.values() for p in t.players}

        self.crew: CrewLike = engines.crew(self.teams)
        self._bookmark_crew: CrewLike = (engines.bookmark_crew or engines.crew)(self.teams)
        self._bundles: dict[str, MomentBundle] = {}
        self._bundle_index: list[tuple[int, MomentBundle]] = []
        self._moment_at: dict[str, int] = {}  # moment id -> index of the event that made it
        self._checkpoints: list[tuple[int, StatsEngineLike]] = []
        self._event_metrics: list[EventMetrics] = []  # per event, from the load-time pass
        self.bookmarks: list[Bookmark] = []
        self._precompute()

        self.is_running = True
        self.speed = DEFAULT_SPEED
        self.ended = False
        self._position = 0.0
        self._last_wall = clock()
        self._live = self._fresh_live()
        self._recaps: dict[tuple[str, int], Recap] = {}

    # --- setup -------------------------------------------------------------------------------

    def _new_stats(self) -> StatsEngineLike:
        return self._engines.stats(self.match_id, self.home_id, self.away_id)

    def _fresh_live(self) -> _Live:
        live = _Live(stats=self._new_stats())
        live.snapshot = live.stats.snapshot()
        return live

    def _first_clock_per_period(self) -> dict[int, float]:
        starts: dict[int, float] = {}
        for e in self.events:
            starts.setdefault(e.period, e.clock_s)
        return starts

    def _precompute(self) -> None:
        """Run stats and a template crew over the whole match once, for bookmarks and replays."""
        self._pre_stats = self._new_stats()
        self._precompute_from(0)

    def _precompute_from(self, start: int) -> None:
        """The load-time pass over events[start:] (all of them, or the ones a live feed just added)."""
        stats = self._pre_stats
        for i in range(start, len(self.events)):
            event = self.events[i]
            if i % CHECKPOINT_EVERY == 0:
                self._checkpoints.append((i, copy.deepcopy(stats)))  # stats after events[:i]
            metrics = stats.process(event)
            self._event_metrics.append(metrics)
            for bundle in self._bookmark_crew.process(event, metrics, stats.snapshot(), stats.players()):
                m = bundle.moment
                self._bundles[m.moment_id] = bundle
                self._moment_at[m.moment_id] = i
                self._bundle_index.append((i, bundle))
                if str(m.kind) in NO_BOOKMARK_KINDS:
                    continue
                self.bookmarks.append(
                    Bookmark(
                        moment_id=m.moment_id,
                        kind=str(m.kind),
                        match_clock=m.match_clock,
                        clock_s=m.clock_s,
                        period=m.period,
                        title=self._title(bundle),
                    )
                )

    def _title(self, bundle: MomentBundle) -> str:
        card = self._bookmark_crew.render(bundle, ViewerProfile())
        if card is not None and card.headline:
            return card.headline
        return bundle.explanation.tactical_tag or str(bundle.moment.kind).replace("_", " ").capitalize()

    # --- read-only views ---------------------------------------------------------------------

    @property
    def next_index(self) -> int:
        return self._live.next_index

    @property
    def snapshot(self) -> MatchStateSnapshot:
        assert self._live.snapshot is not None
        return self._live.snapshot

    @property
    def score(self) -> tuple[int, int]:
        return self._live.score_home, self._live.score_away

    @property
    def last_event(self) -> Event | None:
        i = self._live.next_index
        return self.events[i - 1] if i else None

    @property
    def clock_s(self) -> float:
        last = self.last_event
        return last.clock_s if last else 0.0

    @property
    def period(self) -> int:
        last = self.last_event
        return last.period if last else 1

    @property
    def match_clock(self) -> str:
        last = self.last_event
        return last.match_clock if last else "00:00"

    def players(self) -> list[PlayerStats]:
        """All player stats so far, in line-up order (home first)."""
        stats = self._live.stats.players()
        ordered = []
        for team_id in (self.home_id, self.away_id):
            for p in self.teams[team_id].players:
                if p.player_id in stats:
                    ordered.append(stats[p.player_id])
        ordered.extend(s for pid, s in stats.items() if pid not in self._player_ids)
        return ordered

    def recent_bundles(self) -> list[MomentBundle]:
        return list(self._live.recent)

    def bundle(self, moment_id: str) -> MomentBundle | None:
        return self._bundles.get(moment_id)

    def is_played(self, moment_id: str) -> bool:
        """Whether the moment's event has been played at the current position."""
        at = self._moment_at.get(moment_id)
        return at is not None and at < self._live.next_index

    def recent_events(self, limit: int) -> list[tuple[Event, EventMetrics]]:
        """The last `limit` events played, oldest first, with their metrics. Metrics come from
        the load-time pass: the same events in the same order give the same numbers live."""
        done = self._live.next_index
        start = max(0, done - max(0, limit))
        return [(self.events[i], self._event_metrics[i]) for i in range(start, done)]

    def is_known_team(self, team_id: str) -> bool:
        return team_id in self.teams

    def is_known_player(self, player_id: str) -> bool:
        return player_id in self._player_ids

    # --- cards: the one place a profile turns moments into overlays ---------------------------

    def cards_for(
        self,
        bundles: list[MomentBundle],
        profile: ViewerProfile,
        state: ViewerState | None = None,
        tick: Tick | None = None,
    ) -> list[OverlayCard]:
        """Cards for one viewer, highest priority first: the crew's producer picks
        and times them; focus-metric alerts are added when a tick is given."""
        state = state if state is not None else ViewerState()
        cards = list(self.crew.cards_for(bundles, profile, state))
        if tick is not None and profile.focus_metric is not None:
            players = tick.players if tick.players is not None else self._live.stats.players()
            cards.extend(
                self.crew.metric_alerts(tick.event, tick.metrics, tick.snapshot, players, profile, state)
            )
        cards.sort(key=lambda c: (-c.priority, c.show_at_s))
        return cards

    def card_for_moment(self, moment_id: str, profile: ViewerProfile) -> OverlayCard | None:
        bundle = self._bundles.get(moment_id)
        return self.crew.render(bundle, profile) if bundle is not None else None

    def moments_so_far(self) -> list[Moment]:
        """Every moment up to the current position, from the load-time pass. The same
        list whether the viewer watched straight through or jumped here."""
        done = self._live.next_index
        return [b.moment for idx, b in self._bundle_index if idx < done]

    def recap(self, profile: ViewerProfile) -> Recap:
        key = (profile.model_dump_json(), self._live.next_index)
        cached = self._recaps.get(key)
        if cached is not None:
            return cached
        recap = self.crew.recap(self.snapshot, self._live.stats.players(), profile, self.moments_so_far())
        # A recap left in English by a passing translator problem is not kept, so the
        # next request can try again (the crew still caches what it can).
        if recap.fallback_reason not in TRANSIENT_REASONS:
            if len(self._recaps) >= _RECAP_CACHE_SIZE:
                self._recaps.pop(next(iter(self._recaps)))
            self._recaps[key] = recap
        return recap

    def recap_source(self, profile: ViewerProfile) -> tuple[Recap, list[Moment], MatchStateSnapshot]:
        """What a world-language recap is translated from: the English recap for the same
        audience, the moments so far and the snapshot. Quick; call it under the crew lock."""
        english = self.recap(profile.model_copy(update={"language": "en"}))
        return english, self.moments_so_far(), self.snapshot

    def translate_recap(
        self, english: Recap, moments: list[Moment], snapshot: MatchStateSnapshot, profile: ViewerProfile
    ) -> Recap:
        """The translation step (may wait on Azure AI Translator). Needs no session lock."""
        return self.crew.translate_recap(english, moments, profile, snapshot)

    def crew_status(self) -> CrewStatus:
        return self.crew.status()

    def crew_traces(self, limit: int) -> list[CrewTrace]:
        return self.crew.traces(limit)

    # --- live source -------------------------------------------------------------------------

    @property
    def is_live(self) -> bool:
        return self._feed is not None

    def append(self, events: list[Event]) -> None:
        """Add events a live feed has just delivered (already checked, in seq order).
        Callers hold the same locks as for a seek: the load-time pass grows here."""
        if not events:
            return
        if not self._open:
            raise ValueError("This match is complete; nothing more can be added")
        if events[0].seq <= self.events[-1].seq or events[0].match_id != self.match_id:
            raise ValueError("Live events must follow the match so far")
        start = len(self.events)
        _extend_timeline(self._tl, self.events, events)
        self.events.extend(events)
        for e in events:
            self._period_starts.setdefault(e.period, e.clock_s)
        self._precompute_from(start)
        if self.events[-1].type == EventType.MATCH_END:
            self._open = False

    def _pull(self) -> None:
        """Take what the live feed has ready. A feed that stops for good closes the match."""
        if self._feed is None or not self._open:
            return
        self.append(self._feed.drain())
        if self._open and self._feed.exhausted:
            self._open = False
            if self._live.next_index >= len(self.events) and self._live.next_index > 0:
                self.ended = True
                self.is_running = False

    def source_status(self) -> dict[str, Any]:
        """Where the match comes from, for GET /api/source (counts only, no event content)."""
        out = dict(self._source)
        out.update({"match_id": self.match_id, "events_loaded": len(self.events), "complete": not self._open})
        if self._feed is not None:
            out["stream"] = self._feed.status()
        return out

    # --- playback ----------------------------------------------------------------------------

    def touch(self) -> None:
        """Keep the wall clock reference fresh without playing (e.g. nobody is watching)."""
        self._pull()
        self._last_wall = self._clock()

    def advance(self, with_crew: bool = True) -> list[Tick]:
        """Play every event that is due by now. Returns them in order.

        `with_crew=False` plays stats only; the caller then runs `crew_tick` on each
        tick, in order, outside the playback lock (model calls can be slow)."""
        self._pull()
        now = self._clock()
        if self.is_running and not self.ended:
            self._position += max(0.0, now - self._last_wall) * self.base_rate * self.speed
        self._last_wall = now
        ticks: list[Tick] = []
        while self.is_running and not self.ended and self._live.next_index < len(self.events):
            i = self._live.next_index
            if self._tl[i] > self._position + 1e-6:
                break
            ticks.append(self._play(i, with_crew=with_crew, keep_players=not with_crew))
        return ticks

    def crew_tick(self, tick: Tick) -> Tick:
        """The crew's moments for a tick played with `with_crew=False`."""
        players = tick.players if tick.players is not None else self._live.stats.players()
        bundles = self.crew.process(tick.event, tick.metrics, tick.snapshot, players)
        self._live.recent.extend(bundles)
        return replace(tick, bundles=bundles)

    def _play(self, i: int, with_crew: bool, keep_players: bool = False) -> Tick:
        live = self._live
        event = self.events[i]
        metrics = live.stats.process(event)
        snapshot = live.stats.snapshot()
        changed = live.stats.changed_players()
        bundles: list[MomentBundle] = []
        if with_crew:
            bundles = self.crew.process(event, metrics, snapshot, live.stats.players())
            live.recent.extend(bundles)
        live.metrics, live.snapshot = metrics, snapshot
        live.score_home, live.score_away = snapshot.score_home, snapshot.score_away
        live.next_index = i + 1
        is_last = live.next_index >= len(self.events) and not self._open
        if is_last:
            self.ended = True
            self.is_running = False
        players = None
        if keep_players:
            players = {pid: p.model_copy() for pid, p in live.stats.players().items()}
        return Tick(
            event, metrics, snapshot, changed, bundles, live.score_home, live.score_away, is_last, players
        )

    def toggle_pause(self) -> None:
        if self.ended:
            raise SessionError("The match has finished. Reset or jump back to watch it again.")
        self.is_running = not self.is_running
        self._last_wall = self._clock()

    def set_speed(self, speed: int) -> None:
        if speed not in SPEEDS:
            raise SessionError("Speed must be 1, 10 or 60.")
        self.speed = speed
        self._last_wall = self._clock()

    def reset(self) -> None:
        """Back to kick-off and play."""
        self.seek(0.0, period=1)
        self.is_running = True

    def seek(self, clock_s: float, period: int | None = None) -> None:
        """Jump to a match clock time. Stats replay from kick-off; no cards are produced on the way."""
        if clock_s < 0:
            raise SessionError("Pick a time between kick-off and full time.")
        if period is None:
            period = max((p for p, start in self._period_starts.items() if start <= clock_s), default=1)
        if period not in self._period_starts:
            raise SessionError("That half is not in this match.")
        target = len(self.events)
        for i, e in enumerate(self.events):
            if e.period > period or (e.period == period and e.clock_s >= clock_s):
                target = i
                break
        if target >= len(self.events):
            if self._open:
                raise SessionError("That part of the match has not been played yet.")
            raise SessionError("That time is after full time.")
        # Landing on the start of the match or a half includes its kick-off markers.
        while target < len(self.events) - 1 and self.events[target].type in (
            EventType.MATCH_START,
            EventType.PERIOD_START,
        ):
            target += 1
        start, stats = max((cp for cp in self._checkpoints if cp[0] < target), key=lambda cp: cp[0])
        before = [b for idx, b in self._bundle_index if idx < target]
        self.crew.reset()
        self.crew.restore(before)
        self._recaps.clear()
        self._live = _Live(stats=copy.deepcopy(stats), next_index=start)
        for i in range(start, target):
            self._play(i, with_crew=False)
        self._live.recent.extend(before)
        self.ended = False
        self._position = self._tl[target - 1]
        if self.events[target].period == period:
            # Land on the requested clock so the wait for the next event is right.
            self._position = max(self._position, clock_s + (self._tl[target] - self.events[target].clock_s))
            self._position = min(self._position, self._tl[target])
        self._last_wall = self._clock()

    def play_to_end(self) -> None:
        """Jump to full time (stats only, no cards on the way), e.g. for a tool that reads a
        finished match. Moments come from the load-time pass, as after a seek."""
        self.crew.reset()
        self.crew.restore([b for _, b in self._bundle_index])
        self._recaps.clear()
        self._live = self._fresh_live()
        for i in range(len(self.events)):
            self._play(i, with_crew=False)
        self._live.recent.extend(b for _, b in self._bundle_index)
        self._position = self._tl[-1]
        self._last_wall = self._clock()

    def playback(self) -> dict[str, Any]:
        return {
            "is_running": self.is_running,
            "speed_multiplier": self.speed,
            "clock_s": self.clock_s,
            "match_clock": self.match_clock,
            "period": self.period,
            "ended": self.ended,
        }


SOURCES = ("file", "eventhubs")
DEFAULT_LIVE_WAIT_S = 90.0


def build_session(match_file: str | Path | None = None, engines: Engines | None = None) -> MatchSession:
    """The real session: demo match (or MATCHMIND_MATCH_FILE), real stats engine and crew.

    MATCHMIND_SOURCE=eventhubs plays the live Event Hubs stream instead (off by default)."""
    source = (os.environ.get("MATCHMIND_SOURCE") or "file").strip().lower()
    if source not in SOURCES:
        raise RuntimeError("MATCHMIND_SOURCE must be 'file' or 'eventhubs'")
    engines = engines or real_engines()
    if source == "eventhubs" and match_file is None:
        live = build_live_session(engines)
        if live is not None:
            return live
        note = "No live match started within the wait; replaying the match file instead."
        return _file_session(match_file, engines, {"source": "file", "requested": "eventhubs", "note": note})
    return _file_session(match_file, engines, None)


def _file_session(
    match_file: str | Path | None, engines: Engines, source: dict[str, Any] | None
) -> MatchSession:
    feed = load_match_feed(match_file)
    return MatchSession(
        feed.events,
        teams=feed.teams,
        engines=engines,
        auto_eventing=_auto_eventing(feed.events),
        source=source or {"source": "file", "format": feed.source},
    )


def build_live_session(
    engines: Engines,
    consumer_factory: Callable[[], Any] | None = None,
    wait_s: float | None = None,
) -> MatchSession | None:
    """A session on the live stream, once its match_start arrives; None if none does in time."""
    from matchmind.ingest.eventhubs import EventHubsSource, default_consumer
    from matchmind.ingest.live import LiveFeed
    from matchmind.ingest.roster import load_roster
    from matchmind.ingest.stream import StreamValidator

    roster_file = os.environ.get("MATCHMIND_ROSTER_FILE")
    validator = StreamValidator(
        match_id=os.environ.get("MATCHMIND_EVENTHUBS_MATCH_ID") or None,
        roster=load_roster(roster_file) if roster_file else None,
    )
    feed = LiveFeed(validator)
    consumer = EventHubsSource(feed, consumer_factory or default_consumer)
    consumer.start()
    wait = (
        wait_s
        if wait_s is not None
        else float(os.environ.get("MATCHMIND_EVENTHUBS_WAIT_S") or DEFAULT_LIVE_WAIT_S)
    )
    start = feed.wait_for_start(wait)
    if start is None:
        logger.warning("no live match_start within %.0f s; falling back to the match file", wait)
        consumer.close()
        return None
    assert feed.teams is not None
    session = MatchSession(
        [start],
        teams=feed.teams,
        engines=engines,
        live_feed=feed,
        source={"source": "eventhubs", "starting_position": consumer.starting_position},
    )
    session.consumer = consumer  # kept alive with the session
    return session


def _auto_eventing(events: list[Event]) -> dict[str, Any] | None:
    """Auto-eventing check results when that module is built; None until then."""
    try:
        from matchmind import autoevent  # type: ignore[attr-defined]
    except ImportError:
        return None
    try:
        result = autoevent.evaluate(events)
    except Exception:  # noqa: BLE001 - an optional add-on must never stop the match
        return None
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    return dict(result) if result else None
