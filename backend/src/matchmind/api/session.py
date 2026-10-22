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
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from matchmind.crew.audit import moment_audit
from matchmind.crew.contracts import (
    CrewStatus,
    CrewTrace,
    Moment,
    MomentAudit,
    MomentBundle,
    OverlayCard,
    Recap,
    ViewerProfile,
)
from matchmind.crew.cues import Cue, CueCompiler, CueTime, RibbonSample, active_cues
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
_CUE_CACHE_SIZE = 16
CUE_PAGE_MAX = 500
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
    # True when a later correction (a VAR review) ruled this moment out.
    ruled_out: bool = False


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
    index: int = -1  # position of the event in the match


@dataclass
class _CueCompile:
    """One audience's cue sheet compiled up to a position (cached)."""

    sheet: list[Cue]
    state: ViewerState  # producer memory plus the cue compiler, ready to continue live


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
        self.live_dropped = 0  # live events the load-time pass could not process
        self._waiting_live: tuple[Any, Any] | None = None  # (feed, consumer) before a live match starts
        self._switched = False
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
        self._spotter_checkpoints: dict[int, Any] = {}  # index -> spotter rolling state before it
        self._event_metrics: list[EventMetrics] = []  # per event, from the load-time pass
        self.bookmarks: list[Bookmark] = []
        self._samples: list[RibbonSample] = []  # momentum and pressure after each event
        self._retractions: list[tuple[int, list[str]]] = []  # (event index, moment ids ruled out)
        self._cue_cache: OrderedDict[tuple[str, int], _CueCompile] = OrderedDict()
        self._cue_lock = threading.Lock()
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
                spotter = getattr(self._bookmark_crew, "spotter", None)
                if spotter is not None:
                    self._spotter_checkpoints[i] = copy.deepcopy(spotter.state)
            metrics = stats.process(event)
            self._event_metrics.append(metrics)
            snap = stats.snapshot()
            self._samples.append(
                RibbonSample(snap.momentum, snap.home.pressure_index, snap.away.pressure_index)
            )
            for bundle in self._bookmark_crew.process(event, metrics, snap, stats.players()):
                m = bundle.moment
                self._bundles[m.moment_id] = bundle
                self._moment_at[m.moment_id] = i
                self._bundle_index.append((i, bundle))
                if m.retracts:
                    self._retractions.append((i, list(m.retracts)))
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
        ruled_out = {mid for _, ids in self._retractions for mid in ids}
        self.bookmarks = [replace(b, ruled_out=b.moment_id in ruled_out) for b in self.bookmarks]

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

    def retracted_so_far(self) -> set[str]:
        """Moment ids that a correction played so far has ruled out."""
        done = self._live.next_index
        return {mid for idx, ids in self._retractions if idx < done for mid in ids}

    def recent_bundles(self) -> list[MomentBundle]:
        """The last few moments, never one a correction has already ruled out (so a
        seek or reconnect after a VAR overturn cannot show the goal as live)."""
        gone = self.retracted_so_far()
        return [b for b in self._live.recent if b.moment.moment_id not in gone]

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

    def moment_audit(self, moment_id: str) -> MomentAudit | None:
        """Facts, claims, parity and trace for one moment (docs/TRUST.md). The
        renderings come from the template-only bookmark crew plus whatever the live
        crew already has cached, so an audit never calls a paid model."""
        bundle = self._bundles.get(moment_id)
        if bundle is None:
            return None
        audit = moment_audit(bundle, self._bookmark_crew, self.crew)
        # A goal VAR later ruled out says so, whatever the live position (an audit is a record).
        by = next((b.moment.moment_id for _, b in self._bundle_index if moment_id in b.moment.retracts), None)
        return audit.model_copy(update={"retracts": list(bundle.moment.retracts), "ruled_out_by": by})

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

    # --- cue sheet ---------------------------------------------------------------------------

    def cue_time(self, index: int) -> CueTime:
        index = max(0, min(index, len(self.events) - 1))
        e = self.events[index]
        return CueTime(
            period=e.period, clock_s=e.clock_s, match_clock=e.match_clock, t_s=round(self._tl[index], 2)
        )

    def _compile(self, profile: ViewerProfile, upto: int) -> _CueCompile:
        """The audience's cue sheet for events[:upto], from the load-time moments and the
        template crew (no paid calls; same input, same sheet). Cached per position."""
        key = (profile.model_dump_json(), upto)
        with self._cue_lock:
            hit = self._cue_cache.get(key)
            if hit is not None:
                self._cue_cache.move_to_end(key)
                return hit
            state = ViewerState()
            state.cues = CueCompiler.for_profile(self.match_id, self.home_id, self.away_id, profile)
            by_index: dict[int, list[MomentBundle]] = {}
            for idx, bundle in self._bundle_index:
                if idx >= upto:
                    break
                by_index.setdefault(idx, []).append(bundle)
            sheet: list[Cue] = []
            for i in range(upto):
                bundles = by_index.get(i, [])
                cards = self._bookmark_crew.cards_for(bundles, profile, state) if bundles else []
                sheet += state.cues.feed(
                    i, self.cue_time(i), str(self.events[i].type), bundles, cards, self._samples[i]
                )
            compiled = _CueCompile(sheet=sheet, state=state)
            self._cue_cache[key] = compiled
            while len(self._cue_cache) > _CUE_CACHE_SIZE:
                self._cue_cache.popitem(last=False)
            return compiled

    def viewer_state(self, profile: ViewerProfile, upto: int | None = None) -> ViewerState:
        """Producer memory and cue sheet for a viewer joining at `upto` (default: now):
        everything before it is already compiled, so their live cues continue the same
        sheet, and what is on air goes out once in `cue_active`."""
        upto = self._live.next_index if upto is None else max(0, min(upto, len(self.events)))
        compiled = self._compile(profile, upto)
        state = compiled.state.fork()
        now = self._tl[upto - 1] if upto else 0.0
        state.cue_active = active_cues(compiled.sheet, now)
        return state

    def tick_cues(self, tick: Tick, cards: list[OverlayCard], state: ViewerState) -> list[Cue]:
        """This viewer's new cues for one played tick (empty if it was already fed)."""
        if state.cues is None or tick.index < 0:
            return []
        return state.cues.feed(
            tick.index,
            self.cue_time(tick.index),
            str(tick.event.type),
            tick.bundles,
            cards,
            self._samples[tick.index],
        )

    def cue_sheet(
        self, profile: ViewerProfile, since_seq: int = 0, limit: int = CUE_PAGE_MAX
    ) -> dict[str, Any]:
        """The compiled sheet so far for one audience, cues with seq > since_seq, at most
        `limit` per page. Deterministic: the same position and query give the same JSON."""
        upto = self._live.next_index
        compiled = self._compile(profile, upto)
        limit = max(1, min(limit, CUE_PAGE_MAX))
        newer = [c for c in compiled.sheet if c.seq > since_seq]
        page = newer[:limit]
        assert compiled.state.cues is not None
        return {
            "schema_version": "1.0",
            "match_id": self.match_id,
            "sheet_id": compiled.state.cues.sheet_id,
            "persona": profile.persona,
            "language": profile.language,
            "position": self.cue_time(upto - 1).model_dump() if upto else None,
            "last_seq": compiled.state.cues.seq,
            "since_seq": since_seq,
            "has_more": len(newer) > len(page),
            "next_since_seq": page[-1].seq if page else since_seq,
            "cues": [c.model_dump(mode="json") for c in page],
        }

    # --- live source -------------------------------------------------------------------------

    @property
    def is_live(self) -> bool:
        return self._feed is not None

    def append(self, events: list[Event]) -> None:
        """Add events a live feed has just delivered (already checked, in seq order).
        Callers hold the same locks as for a seek: the load-time pass grows here.

        All or nothing per event: an event the load-time pass cannot process is taken back
        out (events, timeline, metrics, moments, checkpoints and stats) and counted in
        `live_dropped`, so every list stays the same length as the events."""
        if not events:
            return
        if not self._open:
            raise ValueError("This match is complete; nothing more can be added")
        if events[0].seq <= self.events[-1].seq or events[0].match_id != self.match_id:
            raise ValueError("Live events must follow the match so far")
        for event in events:
            self._append_one(event)
            if event.type == EventType.MATCH_END and self.events[-1] is event:
                self._open = False
                break

    def _append_one(self, event: Event) -> None:
        i = len(self.events)
        marks = (len(self._bundle_index), len(self.bookmarks), len(self._checkpoints))
        _extend_timeline(self._tl, self.events, [event])
        self.events.append(event)
        new_period = event.period not in self._period_starts
        self._period_starts.setdefault(event.period, event.clock_s)
        try:
            self._precompute_from(i)
        except Exception:  # noqa: BLE001 - one bad live event must not corrupt the match
            logger.exception("live event %s could not be processed; dropped", event.seq)
            for _, bundle in self._bundle_index[marks[0] :]:
                self._bundles.pop(bundle.moment.moment_id, None)
                self._moment_at.pop(bundle.moment.moment_id, None)
            del self._bundle_index[marks[0] :]
            del self.bookmarks[marks[1] :]
            del self._checkpoints[marks[2] :]
            del self._event_metrics[i:]
            del self.events[i:]
            del self._tl[i:]
            if new_period:
                self._period_starts.pop(event.period, None)
            # Stats back to "after events[:i]": the nearest checkpoint, replayed (stats only).
            start, stats = max(self._checkpoints, key=lambda cp: cp[0])
            stats = copy.deepcopy(stats)
            for e in self.events[start:i]:
                stats.process(e)
            self._pre_stats = stats
            self.live_dropped += 1

    def await_live(self, feed: Any, consumer: Any) -> None:
        """Keep playing this (file) match until the live feed's match_start arrives, then
        switch to the live match. Start-up never waits on the stream."""
        self._waiting_live = (feed, consumer)
        self._source["stream_wait"] = True

    def poll_live(self) -> bool:
        """Switch to a live match that has just started. True once per switch, so the
        transport can tell viewers to reset and send fresh snapshots."""
        if self._waiting_live is not None:
            self._maybe_go_live()
        switched, self._switched = self._switched, False
        return switched

    def _maybe_go_live(self) -> None:
        assert self._waiting_live is not None
        feed, consumer = self._waiting_live
        start = feed.wait_for_start(0)
        if start is None:
            if feed.closed:
                self._waiting_live = None
                self._source.pop("stream_wait", None)
                self._source["note"] = (
                    "The live stream stopped before a match started; replaying the match file."
                )
            return
        engines, clock, base_rate = self._engines, self._clock, self.base_rate
        # Same object, new match: the hub keeps its reference and only resets viewers.
        self.__init__(  # type: ignore[misc]
            [start],
            teams=feed.teams,
            engines=engines,
            clock=clock,
            base_rate=base_rate,
            live_feed=feed,
            source={"source": "eventhubs", "starting_position": consumer.starting_position},
        )
        self.consumer = consumer
        self._switched = True

    def _pull(self) -> None:
        """Take what the live feed has ready. A feed that stops for good closes the match."""
        if self._waiting_live is not None:
            self._maybe_go_live()
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
        out.update(
            {
                "match_id": self.match_id,
                "events_loaded": len(self.events),
                "complete": not self._open,
                "events_dropped": self.live_dropped,
            }
        )
        if self._feed is not None:
            out["stream"] = self._feed.status()
        elif self._waiting_live is not None:
            out["stream"] = self._waiting_live[0].status()
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
            event, metrics, snapshot, changed, bundles, live.score_home, live.score_away, is_last, players, i
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
        with self._cue_lock:
            self._cue_cache.clear()
        self._live = _Live(stats=copy.deepcopy(stats), next_index=start)
        # The spotter's rolling memory (momentum history, pressure spells, gaps between
        # tags) is brought back too, so moments after the jump are the ones a straight run
        # finds, and the live cue stream continues the compiled sheet exactly.
        spotter = getattr(self.crew, "spotter", None)
        warm = spotter is not None and start in self._spotter_checkpoints
        if warm:
            spotter.state = copy.deepcopy(self._spotter_checkpoints[start])
        for i in range(start, target):
            tick = self._play(i, with_crew=False)
            if warm:
                spotter.spot(tick.event, tick.metrics, tick.snapshot, self._live.stats.players())
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
DEFAULT_LIVE_WAIT_S = 30.0  # build_live_session only; the app itself never waits


def build_session(match_file: str | Path | None = None, engines: Engines | None = None) -> MatchSession:
    """The real session: demo match (or MATCHMIND_MATCH_FILE), real stats engine and crew.

    MATCHMIND_SOURCE=eventhubs plays the live Event Hubs stream instead (off by default)."""
    source = (os.environ.get("MATCHMIND_SOURCE") or "file").strip().lower()
    if source not in SOURCES:
        raise RuntimeError("MATCHMIND_SOURCE must be 'file' or 'eventhubs'")
    engines = engines or real_engines()
    if source == "eventhubs" and match_file is None:
        # Start-up never waits on the stream: the file match plays at once and the session
        # switches to the live match when its match_start arrives.
        note = "Waiting for a live match on Event Hubs; replaying the match file until one starts."
        session = _file_session(
            match_file, engines, {"source": "file", "requested": "eventhubs", "note": note}
        )
        session.await_live(*start_live_source())
        return session
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


def start_live_source(consumer_factory: Callable[[], Any] | None = None) -> tuple[Any, Any]:
    """The live feed and its running Event Hubs consumer (keyless)."""
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
    return feed, consumer


def build_live_session(
    engines: Engines,
    consumer_factory: Callable[[], Any] | None = None,
    wait_s: float | None = None,
) -> MatchSession | None:
    """A session on the live stream once its match_start arrives (blocking; tests and tools).
    None if none does in time. The app uses build_session, which never waits."""
    feed, consumer = start_live_source(consumer_factory)
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
