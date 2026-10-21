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
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from matchmind.crew.contracts import (
    CrewStatus,
    CrewTrace,
    MomentBundle,
    OverlayCard,
    Recap,
    ViewerProfile,
)
from matchmind.crew.producer import ViewerState
from matchmind.schema import Event, EventType
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import Team, get_team
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

logger = logging.getLogger("pitchpulse.session")

SPEEDS: tuple[int, ...] = (1, 10, 60)
DEFAULT_SPEED = 10
DEFAULT_BASE_RATE = 10.0
RECENT_BUNDLES = 8
_RECAP_CACHE_SIZE = 32

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
        self, snapshot: MatchStateSnapshot, players: Mapping[str, PlayerStats], profile: ViewerProfile
    ) -> Recap: ...
    def status(self) -> CrewStatus: ...
    def traces(self, limit: int) -> list[CrewTrace]: ...
    def reset(self) -> None: ...


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
    llm = live_llm()
    # The pre-pass over the whole match always runs in template mode, so loading a match
    # never spends on paid AI calls.
    return Engines(
        stats=StatsEngine,
        crew=lambda teams: Crew(teams, llm=llm),
        bookmark_crew=lambda teams: Crew(teams, llm=None),
    )


def ai_enabled() -> bool:
    return os.environ.get("MATCHMIND_AI_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def live_llm() -> Any:
    """The paid model client only when MATCHMIND_AI_ENABLED is on; otherwise None (templates).

    The client reads its own AZURE_OPENAI_* settings. If it cannot be built, the crew
    stays on templates rather than stopping the match.
    """
    if not ai_enabled():
        return None
    try:
        from matchmind.crew.llm import AzureOpenAILLM

        return AzureOpenAILLM()
    except Exception:  # noqa: BLE001 - optional, paid add-on
        logger.warning("MATCHMIND_AI_ENABLED is on but the model client could not start; using templates")
        return None


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


@dataclass
class _Live:
    stats: StatsEngineLike
    next_index: int = 0
    metrics: EventMetrics | None = None
    snapshot: MatchStateSnapshot | None = None
    recent: deque[MomentBundle] = field(default_factory=lambda: deque(maxlen=RECENT_BUNDLES))
    score_home: int = 0
    score_away: int = 0


def load_events(path: str | Path | None = None) -> list[Event]:
    path = Path(path or os.environ.get("MATCHMIND_MATCH_FILE") or DEFAULT_MATCH_FILE)
    if not path.is_file():
        raise RuntimeError(f"Match file not found: {path}")
    events = read_jsonl(path)
    if not events or events[0].type != EventType.MATCH_START:
        raise RuntimeError(f"{path} does not start with a match_start event")
    return events


def _timeline(events: list[Event]) -> list[float]:
    """Monotonic playback seconds: periods glued end to end."""
    out: list[float] = []
    offset, last_tl, period = 0.0, 0.0, None
    for e in events:
        if period is not None and e.period != period:
            offset = last_tl - e.clock_s
        period = e.period
        tl = max(last_tl, e.clock_s + offset)
        out.append(tl)
        last_tl = tl
    return out


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
        self._tl = _timeline(events)
        self._period_starts = self._first_clock_per_period()
        self._player_ids = {p.player_id for t in self.teams.values() for p in t.players}

        self.crew: CrewLike = engines.crew(self.teams)
        self._bookmark_crew: CrewLike = (engines.bookmark_crew or engines.crew)(self.teams)
        self._bundles: dict[str, MomentBundle] = {}
        self._bundle_index: list[tuple[int, MomentBundle]] = []
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
        stats = self._new_stats()
        for i, event in enumerate(self.events):
            metrics = stats.process(event)
            for bundle in self._bookmark_crew.process(event, metrics, stats.snapshot(), stats.players()):
                m = bundle.moment
                self._bundles[m.moment_id] = bundle
                self._bundle_index.append((i, bundle))
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
            players = self._live.stats.players()
            cards.extend(
                self.crew.metric_alerts(tick.event, tick.metrics, tick.snapshot, players, profile, state)
            )
        cards.sort(key=lambda c: (-c.priority, c.show_at_s))
        return cards

    def card_for_moment(self, moment_id: str, profile: ViewerProfile) -> OverlayCard | None:
        bundle = self._bundles.get(moment_id)
        return self.crew.render(bundle, profile) if bundle is not None else None

    def recap(self, profile: ViewerProfile) -> Recap:
        key = (profile.model_dump_json(), self._live.next_index)
        if key not in self._recaps:
            if len(self._recaps) >= _RECAP_CACHE_SIZE:
                self._recaps.pop(next(iter(self._recaps)))
            self._recaps[key] = self.crew.recap(self.snapshot, self._live.stats.players(), profile)
        return self._recaps[key]

    def crew_status(self) -> CrewStatus:
        return self.crew.status()

    def crew_traces(self, limit: int) -> list[CrewTrace]:
        return self.crew.traces(limit)

    # --- playback ----------------------------------------------------------------------------

    def touch(self) -> None:
        """Keep the wall clock reference fresh without playing (e.g. nobody is watching)."""
        self._last_wall = self._clock()

    def advance(self) -> list[Tick]:
        """Play every event that is due by now. Returns them in order."""
        now = self._clock()
        if self.is_running and not self.ended:
            self._position += max(0.0, now - self._last_wall) * self.base_rate * self.speed
        self._last_wall = now
        ticks: list[Tick] = []
        while self.is_running and not self.ended and self._live.next_index < len(self.events):
            i = self._live.next_index
            if self._tl[i] > self._position + 1e-6:
                break
            ticks.append(self._play(i, with_crew=True))
        return ticks

    def _play(self, i: int, with_crew: bool) -> Tick:
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
        is_last = live.next_index >= len(self.events)
        if is_last:
            self.ended = True
            self.is_running = False
        return Tick(event, metrics, snapshot, changed, bundles, live.score_home, live.score_away, is_last)

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
            raise SessionError("That time is after full time.")
        # Landing on the start of the match or a half includes its kick-off markers.
        while target < len(self.events) - 1 and self.events[target].type in (
            EventType.MATCH_START,
            EventType.PERIOD_START,
        ):
            target += 1
        self.crew.reset()
        self._live = self._fresh_live()
        for i in range(target):
            self._play(i, with_crew=False)
        self._live.recent.extend(b for idx, b in self._bundle_index if idx < target)
        self.ended = False
        self._position = self._tl[target - 1]
        if self.events[target].period == period:
            # Land on the requested clock so the wait for the next event is right.
            self._position = max(self._position, clock_s + (self._tl[target] - self.events[target].clock_s))
            self._position = min(self._position, self._tl[target])
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


def build_session(match_file: str | Path | None = None, engines: Engines | None = None) -> MatchSession:
    """The real session: demo match (or MATCHMIND_MATCH_FILE), real stats engine and crew."""
    events = load_events(match_file)
    return MatchSession(events, engines=engines or real_engines(), auto_eventing=_auto_eventing(events))


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
