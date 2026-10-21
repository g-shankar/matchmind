"""Small stand-ins for the stats engine and the crew, so the session and API are
tested on their own. They follow the Protocols in matchmind.api.session."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from matchmind.api.session import Engines, MatchSession
from matchmind.crew.contracts import (
    AgentStep,
    CrewStatus,
    CrewTrace,
    Evidence,
    Explanation,
    FactCheck,
    Moment,
    MomentBundle,
    MomentKind,
    OverlayCard,
    Recap,
    RecapMoment,
    ViewerProfile,
)
from matchmind.schema import Event
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats, TeamWindow

MATCH = "MM-TEST-001"


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class FakeStats:
    def __init__(self, match_id: str, home_id: str, away_id: str) -> None:
        self.match_id, self.home_id, self.away_id = match_id, home_id, away_id
        self.score = {home_id: 0, away_id: 0}
        self._players: dict[str, PlayerStats] = {}
        self._changed: list[PlayerStats] = []
        self.last: Event | None = None

    def process(self, event: Event) -> EventMetrics:
        self.last = event
        self._changed = []
        if event.type == "shot" and event.outcome == "goal" and event.team:
            self.score[event.team] += 1
        if event.player_id and event.team:
            p = self._players.setdefault(
                event.player_id, PlayerStats(player_id=event.player_id, team=event.team)
            )
            p.touches += 1
            if event.type == "pass":
                p.passes += 1
                p.passes_completed += event.outcome == "complete"
            self._changed = [p]
        return EventMetrics(event_id=event.event_id, pass_distance_m=10.0 if event.type == "pass" else None)

    def snapshot(self) -> MatchStateSnapshot:
        w = TeamWindow(
            possession_pct=55,
            field_tilt_pct=60,
            pressure_index=40,
            shots=1,
            xg=0.3,
            final_third_passes=3,
            box_entries=1,
        )
        e = self.last
        return MatchStateSnapshot(
            match_id=self.match_id,
            clock_s=e.clock_s if e else 0,
            match_clock=e.match_clock if e else "00:00",
            period=e.period if e else 1,
            home_id=self.home_id,
            away_id=self.away_id,
            score_home=self.score[self.home_id],
            score_away=self.score[self.away_id],
            home=w,
            away=w.model_copy(update={"possession_pct": 45}),
            momentum=12,
            control_chaos=0.2,
            tempo="Controlled",
            events_per_min=10,
            turnovers_per_min=2,
            avg_chain_passes=3,
            xg_home=0.3,
            xg_away=0.1,
            shots_home=1,
            shots_away=0,
        )

    def players(self) -> dict[str, PlayerStats]:
        return dict(self._players)

    def changed_players(self) -> list[PlayerStats]:
        return list(self._changed)


class FakeCrew:
    """Spots goals; renders one card per goal for any profile."""

    def __init__(self, teams) -> None:
        self.teams = teams
        self.process_calls = 0
        self.recap_calls = 0
        self.resets = 0
        self.restored: list[MomentBundle] = []
        self.recap_moments: list[Moment] | None = None

    def process(self, event, metrics, snapshot, players) -> list[MomentBundle]:
        self.process_calls += 1
        if not (event.type == "shot" and event.outcome == "goal"):
            return []
        moment = Moment(
            moment_id=f"goal-{event.event_id}",
            kind=MomentKind.GOAL,
            clock_s=event.clock_s,
            match_clock=event.match_clock,
            period=event.period,
            team=event.team,
            player_ids=[event.player_id],
            facts={"score_home": snapshot.score_home},
            source_event_ids=[event.event_id],
            priority=90,
        )
        expl = Explanation(
            moment_id=moment.moment_id,
            why="Goal",
            tactical_tag="Finish",
            produced_by="template",
            evidence=[Evidence(label="Score", value=snapshot.score_home)],
        )
        return [MomentBundle(moment=moment, explanation=expl)]

    def render(self, bundle: MomentBundle, profile: ViewerProfile) -> OverlayCard | None:
        m = bundle.moment
        return OverlayCard(
            card_id=f"{m.moment_id}-{profile.persona}-{profile.language}",
            moment_id=m.moment_id,
            kind=m.kind,
            slot="lower_third",
            priority=m.priority,
            show_at_s=m.clock_s,
            duration_s=8,
            persona=profile.persona,
            language=profile.language,
            rtl=profile.language == "ar",
            headline=f"Goal for {m.team}",
            body="b",
            why="w",
            tactical_tag="t",
            evidence=bundle.explanation.evidence,
            player_ids=m.player_ids,
            team=m.team,
            favourite_side=(m.team == profile.favourite_team) if profile.favourite_team else None,
            produced_by="template",
        )

    def cards_for(self, bundles, profile, state) -> list[OverlayCard]:
        return [c for b in bundles if (c := self.render(b, profile)) is not None]

    def metric_alerts(self, event, metrics, snapshot, players, profile, state) -> list[OverlayCard]:
        return []

    def recap(self, snapshot, players, profile, moments=None) -> Recap:
        self.recap_calls += 1
        self.recap_moments = moments
        return Recap(
            match_id=snapshot.match_id,
            persona=profile.persona,
            language=profile.language,
            rtl=profile.language == "ar",
            title="Recap",
            headline=f"{snapshot.score_home}-{snapshot.score_away}",
            summary_paragraphs=["p"],
            key_moments=[RecapMoment(match_clock="1:00", kind="goal", headline="h", moment_id="m")],
            player_of_the_match_id=None,
            player_of_the_match=None,
            stats={"shots": 1},
            generated_at_clock=snapshot.match_clock,
            produced_by="template",
            fact_check=FactCheck(ok=True),
        )

    def status(self) -> CrewStatus:
        return CrewStatus(mode="template", moments=self.process_calls)

    def traces(self, limit: int) -> list[CrewTrace]:
        step = AgentStep(agent="spotter", ms=1.0, status="ok")
        return [CrewTrace(moment_id="m1", match_clock="01:00", steps=[step])][:limit]

    def reset(self) -> None:
        self.resets += 1
        self.restored = []

    def restore(self, bundles) -> None:
        self.restored = list(bundles)


FAKE_ENGINES = Engines(stats=FakeStats, crew=FakeCrew)


def _ev(seq: int, type_: str, clock_s: float, period: int = 1, **kw) -> Event:
    m, s = divmod(int(clock_s), 60)
    return Event(
        event_id=f"{MATCH}-{seq:05d}",
        match_id=MATCH,
        seq=seq,
        ts=datetime(2026, 10, 24, 15, tzinfo=UTC),
        period=period,
        clock_s=clock_s,
        match_clock=kw.pop("match_clock", f"{m:02d}:{s:02d}"),
        type=type_,
        **kw,
    )


def make_events() -> list[Event]:
    """A tiny match: NBR scores at 1:00, HCY at 46:40, with first-half stoppage time."""
    return [
        _ev(0, "match_start", 0, details={"home": "NBR", "away": "HCY"}, labels=["truth"]),
        _ev(1, "period_start", 0),
        _ev(
            2,
            "pass",
            10,
            team="NBR",
            player_id="NBR-9",
            receiver_id="NBR-6",
            start={"x": 52.5, "y": 34},
            end={"x": 60, "y": 30},
            outcome="complete",
            labels=["scripted"],
        ),
        _ev(3, "shot", 60, team="NBR", player_id="NBR-9", start={"x": 95, "y": 34}, outcome="goal"),
        _ev(4, "pass", 2750, team="HCY", player_id="HCY-6", outcome="complete", match_clock="45+0:50"),
        _ev(5, "period_end", 2760, match_clock="45+1:00"),
        _ev(6, "period_start", 2700, period=2),
        _ev(
            7, "shot", 2800, period=2, team="HCY", player_id="HCY-9", start={"x": 10, "y": 34}, outcome="goal"
        ),
        _ev(8, "match_end", 2900, period=2),
    ]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def session(clock: FakeClock) -> MatchSession:
    return MatchSession(make_events(), engines=FAKE_ENGINES, clock=clock, base_rate=10)


@pytest.fixture(autouse=True)
def _fresh_model_budget(monkeypatch):
    """Each test gets its own process-wide model budget, so tests never share spend."""
    from matchmind.crew import llm

    monkeypatch.setattr(llm, "BUDGET", llm.ModelBudget(total=10_000, per_minute=10_000))
