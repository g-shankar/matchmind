"""Studio crew: spotter, analyst, commentator, fact-checker, producer, recap."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from matchmind.crew import fact_checker
from matchmind.crew.analyst import AnalystOut
from matchmind.crew.commentator import CommentatorOut, template_narrative
from matchmind.crew.contracts import LANGUAGES, PERSONAS, MomentKind, OverlayCard, ViewerProfile
from matchmind.crew.crew import BREAKER_OPEN_S, Crew
from matchmind.crew.fact_checker import BANNED_NAMES, check
from matchmind.crew.llm import AzureOpenAILLM, LLMError, LLMSchemaError, TemplateLLM, make_llm
from matchmind.crew.producer import ViewerState, select
from matchmind.crew.recap import RecapOut, player_of_the_match
from matchmind.crew.spotter import Spotter
from matchmind.crew.wording import template_key
from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import TEAMS
from matchmind.stats.models import (
    XY,
    BetterOption,
    EventMetrics,
    MatchStateSnapshot,
    PlayerStats,
    TeamWindow,
    UnfoundRun,
)

CREW_DIR = Path(__file__).resolve().parents[1] / "src" / "matchmind" / "crew"
DEMO = Path(__file__).resolve().parents[1] / "data" / "matches" / "MM-DEMO-001.jsonl"

# --------------------------------------------------------------- fixtures


def clock(s: float) -> str:
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def ev(seq: int, type: EventType, t: float = 600.0, period: int = 1, **kw) -> Event:
    return Event(
        event_id=f"T-{seq:05d}",
        match_id="T",
        seq=seq,
        ts=datetime(2026, 10, 24, 15, tzinfo=UTC),
        period=period,
        clock_s=t,
        match_clock=clock(t),
        type=type,
        **kw,
    )


def window(**kw) -> TeamWindow:
    base = dict(
        possession_pct=50.0,
        field_tilt_pct=50.0,
        pressure_index=20.0,
        shots=1,
        xg=0.1,
        final_third_passes=3,
        box_entries=1,
    )
    base.update(kw)
    return TeamWindow(**base)


def snap(
    t: float = 600.0, period: int = 1, momentum: float = 0.0, home=None, away=None, **kw
) -> MatchStateSnapshot:
    base = dict(
        match_id="T",
        clock_s=t,
        match_clock=clock(t),
        period=period,
        home_id="NBR",
        away_id="HCY",
        score_home=1,
        score_away=0,
        home=home or window(),
        away=away or window(),
        momentum=momentum,
        control_chaos=0.1,
        tempo="Controlled",
        events_per_min=20.0,
        turnovers_per_min=2.0,
        avg_chain_passes=3.0,
        xg_home=1.24,
        xg_away=0.37,
        shots_home=8,
        shots_away=4,
    )
    base.update(kw)
    return MatchStateSnapshot(**base)


def players(**overrides) -> dict[str, PlayerStats]:
    out = {
        "NBR-9": PlayerStats(
            player_id="NBR-9",
            team="NBR",
            passes=20,
            passes_completed=16,
            key_passes=2,
            shots=4,
            goals=1,
            assists=0,
            xg=0.84,
            xa=0.12,
            tackles_won=1,
            top_speed_kmh=32.4,
            sprints=3,
            distance_km=2.4,
        ),
        "NBR-7": PlayerStats(
            player_id="NBR-7",
            team="NBR",
            passes=30,
            passes_completed=25,
            key_passes=3,
            shots=1,
            assists=1,
            xg=0.05,
            xa=0.41,
            tackles_won=2,
            top_speed_kmh=31.0,
            sprints=2,
            distance_km=2.1,
        ),
        "HCY-10": PlayerStats(
            player_id="HCY-10",
            team="HCY",
            passes=25,
            passes_completed=20,
            key_passes=1,
            shots=2,
            xg=0.3,
            xa=0.1,
            tackles_won=0,
            top_speed_kmh=29.0,
            sprints=1,
            distance_km=1.5,
        ),
    }
    for pid, fields in overrides.items():
        out[pid] = out[pid].model_copy(update=fields)
    return out


def better_option_metrics(event_id: str) -> EventMetrics:
    return EventMetrics(
        event_id=event_id,
        chance_quality=0.08,
        better_option=BetterOption(
            shot_event_id=event_id,
            shooter_id="NBR-9",
            teammate_id="NBR-7",
            shot_chance_quality=0.08,
            alt_chance_quality=0.31,
            pass_success=0.8,
            alt_value=0.248,
            times_better=3.1,
            pass_distance_m=11.6,
            nearest_marker_m=4.2,
            shooter_pos=XY(x=88, y=30),
            teammate_pos=XY(x=95, y=38),
            defenders=[XY(x=90, y=33)],
            keeper=XY(x=103, y=34),
        ),
    )


def unfound_run_metrics(event_id: str) -> EventMetrics:
    return EventMetrics(
        event_id=event_id,
        unfound_run=UnfoundRun(
            run_event_id=event_id,
            runner_id="NBR-9",
            carrier_id="NBR-7",
            found=False,
            pass_on_at_s=1.5,
            pass_on_clock="12:01",
            clear_of_line_m=4.3,
            projected_chance_quality=0.38,
            one_on_one=True,
            carrier_pos=XY(x=60, y=30),
            runner_path=[XY(x=70, y=34), XY(x=80, y=34)],
            target=XY(x=85, y=34),
            defenders_at_pass=[XY(x=75, y=30)],
        ),
    )


def all_moments():
    """One spotter run that produces every MomentKind (and every milestone phase)."""
    sp = Spotter(TEAMS)
    pl = players()
    out = []

    def add(event, metrics, snapshot, ps=pl):
        out.extend(sp.spot(event, metrics, snapshot, ps))

    add(ev(1, EventType.PERIOD_START, 0.0), EventMetrics(event_id="T-00001"), snap(0.0, score_home=0))
    goal = ev(
        2,
        EventType.SHOT,
        610.0,
        team="NBR",
        player_id="NBR-9",
        outcome=Outcome.GOAL,
        details={"assist_id": "NBR-7", "score_home": 1, "score_away": 0},
    )
    add(
        goal,
        EventMetrics(
            event_id="T-00002",
            chance_quality=0.42,
            distance_to_goal_m=11.3,
            ball_speed_kmh=104.6,
            pitch_zone="Penalty Box",
        ),
        snap(610.0),
    )
    add(
        ev(3, EventType.SHOT, 640.0, team="NBR", player_id="NBR-9", outcome=Outcome.SAVED),
        EventMetrics(event_id="T-00003", chance_quality=0.35, distance_to_goal_m=9.0, ball_speed_kmh=80.0),
        snap(640.0),
    )
    add(
        ev(4, EventType.CARD, 700.0, team="HCY", player_id="HCY-10", details={"card": "yellow"}),
        EventMetrics(event_id="T-00004"),
        snap(700.0),
    )
    add(
        ev(5, EventType.SHOT, 720.0, team="NBR", player_id="NBR-9", outcome=Outcome.OFF_TARGET),
        better_option_metrics("T-00005"),
        snap(720.0),
    )
    add(
        ev(6, EventType.RUN, 730.0, team="NBR", player_id="NBR-9"),
        unfound_run_metrics("T-00006"),
        snap(730.0),
    )
    add(
        ev(
            7,
            EventType.PASS,
            740.0,
            team="NBR",
            player_id="NBR-7",
            receiver_id="NBR-9",
            outcome=Outcome.COMPLETE,
        ),
        EventMetrics(
            event_id="T-00007", pass_difficulty=82, pass_distance_m=34.2, xt_delta=0.071, progressive=True
        ),
        snap(740.0),
    )
    add(
        ev(8, EventType.CARRY, 750.0, team="NBR", player_id="NBR-9"),
        EventMetrics(event_id="T-00008", player_speed_kmh=33.4),
        snap(750.0),
    )
    add(
        ev(
            9,
            EventType.PASS,
            760.0,
            team="NBR",
            player_id="NBR-7",
            receiver_id="NBR-9",
            outcome=Outcome.COMPLETE,
        ),
        EventMetrics(event_id="T-00009"),
        snap(760.0),
    )  # distance milestones fire here (players already past 1 and 2 km)
    # Momentum swing: flat for 5+ minutes then +55.
    for i, t in enumerate(range(800, 1130, 10)):
        add(ev(100 + i, EventType.PASS, float(t)), EventMetrics(event_id=f"T-{100 + i:05d}"), snap(float(t)))
    add(ev(200, EventType.PASS, 1140.0), EventMetrics(event_id="T-00200"), snap(1140.0, momentum=55.0))
    # Pressure spell: HCY tilt 80% for 3+ minutes.
    for i, t in enumerate(range(1200, 1400, 20)):
        add(
            ev(300 + i, EventType.PASS, float(t)),
            EventMetrics(event_id=f"T-{300 + i:05d}"),
            snap(
                float(t),
                momentum=55.0,
                away=window(field_tilt_pct=80.0, pressure_index=48.0, shots=3, xg=0.4),
            ),
        )
    add(
        ev(
            400,
            EventType.MILESTONE,
            1500.0,
            team="HCY",
            player_id="HCY-10",
            details={"label": "100th club appearance"},
        ),
        EventMetrics(event_id="T-00400"),
        snap(1500.0, momentum=55.0),
    )
    add(
        ev(401, EventType.PERIOD_END, 2760.0, details={"score_home": 1, "score_away": 0}),
        EventMetrics(event_id="T-00401"),
        snap(2760.0, momentum=55.0),
    )
    add(
        ev(402, EventType.MATCH_END, 5500.0, period=2, details={"score_home": 1, "score_away": 0}),
        EventMetrics(event_id="T-00402"),
        snap(5500.0, period=2, momentum=55.0),
    )
    return out


@pytest.fixture(scope="module")
def moments():
    return all_moments()


def first(moments, kind: MomentKind, phase: str | None = None):
    for m in moments:
        if m.kind == kind and (phase is None or m.facts.get("phase") == phase):
            return m
    raise AssertionError(f"no {kind} moment")


def bundles_from(crew: Crew, moments):
    from matchmind.crew.contracts import MomentBundle

    return [MomentBundle(moment=m, explanation=crew._explain(m)) for m in moments]


# ----------------------------------------------------------------- spotter


def test_spotter_finds_every_kind(moments):
    kinds = {m.kind for m in moments}
    assert kinds == set(MomentKind)
    phases = {m.facts["phase"] for m in moments if m.kind == MomentKind.MILESTONE}
    assert phases == {"kick_off", "half_time", "full_time", "player"}


def test_moment_facts_hold_names_and_rounded_numbers(moments):
    bo = first(moments, MomentKind.BETTER_OPTION)
    assert bo.facts["player"] == "Adam Kerrigan" and bo.facts["teammate_short"] == "Mallick"
    assert (
        bo.facts["times_better"] == 3.1
        and bo.facts["pass_success_pct"] == 80
        and bo.facts["alt_value"] == 0.25
    )
    assert bo.source_event_ids == ["T-00005"]
    goal = first(moments, MomentKind.GOAL)
    assert goal.facts["xg"] == 0.42 and goal.facts["assist"] == "Dev Mallick" and goal.priority == 95
    assert first(moments, MomentKind.ROCKET_SHOT).facts["shot_speed_kmh"] == 105


def test_spotter_rate_limits_speed_bursts_and_fires_pressure_once():
    sp = Spotter(TEAMS)
    pl = players()
    fast = EventMetrics(event_id="x", player_speed_kmh=31.0)
    hits = [
        sp.spot(ev(i, EventType.CARRY, t, team="NBR", player_id="NBR-9"), fast, snap(t), pl)
        for i, t in enumerate([100.0, 300.0, 1350.0])
    ]
    assert [len([m for m in h if m.kind == MomentKind.SPEED_BURST]) for h in hits] == [1, 0, 1]

    spells = []
    for i, t in enumerate(range(0, 600, 20)):
        tilt = 80.0 if t < 400 else 40.0
        s = snap(float(t), away=window(field_tilt_pct=tilt))
        spells += [
            m
            for m in sp.spot(ev(50 + i, EventType.PASS, float(t)), EventMetrics(event_id="y"), s, pl)
            if m.kind == MomentKind.PRESSURE_SPELL
        ]
    assert len(spells) == 1 and spells[0].team == "HCY" and spells[0].facts["team_field_tilt_pct"] == 80


def test_distance_milestones_fire_once_each():
    sp = Spotter(TEAMS)
    seen = []
    for i, km in enumerate([0.5, 2.2, 2.3, 3.4]):
        pl = {"NBR-9": PlayerStats(player_id="NBR-9", team="NBR", distance_km=km)}
        seen += [
            m.facts["milestone_km"]
            for m in sp.spot(ev(i, EventType.PASS), EventMetrics(event_id="z"), snap(), pl)
        ]
    assert seen == [2, 3]


# ------------------------------------------------------------ fact-checker


def test_fact_checker_rejects_unbacked_percentage_and_accepts_times():
    facts = {"times_better": 3.1, "player": "Adam Kerrigan"}
    assert not check("The pass was 72% better.", facts).ok
    assert check("The pass was 3.1x better.", facts).ok
    assert check("Kerrigan: 3x better.", facts).ok  # rounding tolerance
    assert not check("It was 3.4x better.", facts).ok


def test_fact_checker_reads_every_digit_style():
    facts = {"times_better": 3.1, "pass_success_pct": 62, "match_clock": "67:28"}
    assert check("التمريرة أفضل بـ٣٫١ أضعاف", facts, "ar").ok
    assert not check("نسبة ٧٢٪", facts, "ar").ok
    assert check("成功率６２%", facts, "ja").ok
    assert check("El pase valía 3,1 veces más, al 62 %.", facts, "es").ok
    assert check("At 67:28 it was 3.1x.", facts).ok  # clock string is a fact
    assert not check("At 70:00 it was 3.1x.", facts).ok


def test_fact_checker_length_and_banned_names():
    assert not check("one two three four five six seven eight nine", {}, field="headline").ok
    assert not check("One. Two. Three.", {}, field="body").ok
    assert check("One. Two.", {}, field="body").ok
    for name in BANNED_NAMES[:3]:
        verdict = check(f"A pass like {name} would make.", {})
        assert not verdict.ok and any("real name" in r for r in verdict.reasons)


def test_no_real_names_anywhere_in_crew_code_or_phrases():
    for path in sorted(CREW_DIR.rglob("*.py")):
        if path.name == "fact_checker.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert fact_checker.banned_names_in(text) == [], path.name
    assert fact_checker.banned_names_in(Path(__file__).read_text(encoding="utf-8")) == []


# ------------------------------------------------------------- templates


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("persona", PERSONAS)
def test_every_kind_renders_a_card_that_passes(moments, persona, language):
    crew = Crew(TEAMS, llm=TemplateLLM())
    for bundle in bundles_from(crew, moments):
        for fav, focus in (
            (None, None),
            ("NBR", bundle.moment.player_ids[0] if bundle.moment.player_ids else None),
            ("HCY", None),
        ):
            profile = ViewerProfile(
                persona=persona, language=language, favourite_team=fav, focus_player_id=focus
            )
            card = crew.render(bundle, profile)
            m = bundle.moment
            assert card is not None, (template_key(m), persona, language, fav)
            assert check(card.headline, m.facts, language, "headline").ok
            assert check(card.body, m.facts, language, "body").ok
            assert card.why and check(card.why, m.facts, language, "why").ok
            assert card.rtl == (language == "ar")
            assert card.produced_by == "template" and card.fallback_reason is None
    assert crew.status().rejections == 0


@pytest.mark.parametrize("language", ["en", "es", "ar"])
def test_template_crew_cards_for_better_option(moments, language):
    crew = Crew(TEAMS, llm=TemplateLLM())
    pl = players()
    event = ev(5, EventType.SHOT, 720.0, team="NBR", player_id="NBR-9", outcome=Outcome.OFF_TARGET)
    bundles = crew.process(event, better_option_metrics("T-00005"), snap(720.0), pl)
    bo = [b for b in bundles if b.moment.kind == MomentKind.BETTER_OPTION]
    assert len(bo) == 1
    cards = crew.cards_for(bo, ViewerProfile(language=language), ViewerState())
    assert len(cards) == 1
    card = cards[0]
    assert card.kind == MomentKind.BETTER_OPTION and card.slot == "side_panel"
    assert card.rtl is (language == "ar")
    assert card.replay is not None and card.replay["times_better"] == 3.1
    assert {e.label_key for e in card.evidence} >= {"times_better", "shot_xg"}
    assert ("3,1" if language == "es" else "3.1") in card.body + card.why or "3.1" in card.why
    # the same event again changes nothing (at-least-once delivery)
    assert crew.process(event, better_option_metrics("T-00005"), snap(720.0), pl) == bundles
    assert crew.status().moments == len(bundles)


def test_evidence_labels_are_localised_without_touching_the_bundle():
    from matchmind.crew import analyst
    from matchmind.crew.i18n import pack

    crew = Crew(TEAMS, llm=TemplateLLM())
    event = ev(5, EventType.SHOT, 720.0, team="NBR", player_id="NBR-9", outcome=Outcome.OFF_TARGET)
    bundles = crew.process(event, better_option_metrics("T-00005"), snap(720.0), players())
    bo = [b for b in bundles if b.moment.kind == MomentKind.BETTER_OPTION]
    for language in ("es", "ar"):
        card = crew.cards_for(bo, ViewerProfile(language=language), ViewerState())[0]
        assert card.evidence and all(e.label_key for e in card.evidence)
        for e in card.evidence:
            assert e.label == pack(language)["labels"][e.label_key]
            assert e.label != analyst.LABELS[e.label_key]
    assert all(e.label == analyst.LABELS[e.label_key] for e in bo[0].explanation.evidence)


def test_every_label_key_exists_in_every_language_pack():
    from matchmind.crew import analyst
    from matchmind.crew.i18n import PACKS

    for language, p in PACKS.items():
        assert set(analyst.LABELS) <= set(p["labels"]), language
    assert PACKS["en"]["labels"] == analyst.LABELS


def test_favourite_club_is_phrased_from_the_viewers_side(moments):
    goal = first(moments, MomentKind.GOAL)
    mine = template_narrative(goal, "casual", "en", favourite_name="Northbridge FC")
    theirs = template_narrative(goal, "casual", "en", favourite_name="Harbour City")
    assert "your team" in mine.headline.lower() and "GOAL" in mine.headline
    assert "against your team" in theirs.headline
    es = template_narrative(goal, "casual", "es", favourite_name="Northbridge FC")
    assert "tu equipo" in es.headline


# --------------------------------------------------------------- AI path


class FakeLLM:
    enabled = True
    model = "fake-model"

    def __init__(
        self, answer=None, delay: float = 0.0, error: Exception | None = None, schema_failures: int = 0
    ):
        self.answer = answer
        self.delay = delay
        self.error = error
        self.schema_failures = schema_failures
        self.calls = 0

    def complete_json(self, system: str, user: dict, schema: type[BaseModel], timeout_s: float) -> BaseModel:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        if self.schema_failures > 0:
            self.schema_failures -= 1
            raise LLMSchemaError("bad json")
        return self.answer(schema, user) if callable(self.answer) else self.answer


def good_answer(schema, user):
    facts = user["facts"]
    if schema is AnalystOut:
        return AnalystOut(
            why=f"The pass was {facts['times_better']}x the better bet.", tactical_tag="decision_making"
        )
    if schema is CommentatorOut:
        return CommentatorOut(
            headline="Kerrigan should have squared it", body=f"Pass value {facts['alt_value']}."
        )
    return RecapOut(title="Recap", headline="Northbridge FC lead", summary_paragraphs=["One.", "Two."])


def trace_of(crew: Crew, moment_id: str):
    return next(t for t in crew.traces(100) if t.moment_id == moment_id)


def better_option_bundle(crew: Crew):
    event = ev(5, EventType.SHOT, 720.0, team="NBR", player_id="NBR-9", outcome=Outcome.OFF_TARGET)
    still = {pid: {"distance_km": 0.0} for pid in ("NBR-9", "NBR-7", "HCY-10")}
    bundles = crew.process(event, better_option_metrics("T-00005"), snap(720.0), players(**still))
    assert [b.moment.kind for b in bundles] == [MomentKind.BETTER_OPTION]
    return bundles[0]


def test_ai_answers_pass_through_when_they_check_out():
    crew = Crew(TEAMS, llm=FakeLLM(answer=good_answer))
    bundle = better_option_bundle(crew)
    assert bundle.explanation.produced_by == "ai"
    card = crew.render(bundle, ViewerProfile())
    assert card.produced_by == "ai" and card.headline == "Kerrigan should have squared it"
    assert crew.status().mode == "ai" and crew.status().model == "fake-model"


def test_timeout_falls_back_to_template_and_is_traced():
    crew = Crew(TEAMS, llm=FakeLLM(answer=good_answer, delay=0.3), timeout_s=0.05)
    bundle = better_option_bundle(crew)
    assert bundle.explanation.produced_by == "template" and bundle.explanation.fallback_reason == "timeout"
    card = crew.render(bundle, ViewerProfile(language="es"))
    assert card.produced_by == "template" and card.fallback_reason == "timeout"
    steps = trace_of(crew, bundle.moment.moment_id).steps
    assert any(s.agent == "analyst" and s.status == "fallback" and s.detail == "timeout" for s in steps)
    assert any(s.agent == "commentator" and s.status == "fallback" for s in steps)
    assert crew.status().fallbacks >= 2


def test_circuit_breaker_opens_after_three_failures_then_recovers():
    now = [1000.0]
    llm = FakeLLM(error=LLMError("down"))
    crew = Crew(TEAMS, llm=llm, clock=lambda: now[0])
    bundle = better_option_bundle(crew)  # analyst failure 1
    for persona in ("casual", "tactical", "fantasy"):  # commentator failures 1-3
        crew.render(bundle, ViewerProfile(persona=persona))
    assert "commentator" in crew.status().breakers_open
    calls = llm.calls
    card = crew.render(bundle, ViewerProfile(persona="player_spotlight"))
    assert llm.calls == calls and card.fallback_reason == "circuit_open"
    now[0] += BREAKER_OPEN_S + 1
    assert "commentator" not in crew.status().breakers_open
    llm.error = None
    llm.answer = good_answer
    card = crew.render(bundle, ViewerProfile(language="fr"))
    assert card.produced_by == "template"  # explanation was a template, but the commentator ran
    assert llm.calls == calls + 1


def test_unbacked_number_from_model_is_rejected_and_template_used():
    def liar(schema, user):
        if schema is CommentatorOut:
            return CommentatorOut(headline="Pass was 72% better", body="He should have passed.")
        return good_answer(schema, user)

    crew = Crew(TEAMS, llm=FakeLLM(answer=liar))
    bundle = better_option_bundle(crew)
    card = crew.render(bundle, ViewerProfile())
    assert "72" not in card.headline and card.produced_by == "template"
    assert card.fallback_reason.startswith("fact_check:")
    assert crew.status().rejections == 1
    assert any(s.status == "rejected" for s in trace_of(crew, bundle.moment.moment_id).steps)


def test_schema_failure_gets_one_repair_retry():
    llm = FakeLLM(answer=good_answer, schema_failures=1)
    crew = Crew(TEAMS, llm=llm)
    bundle = better_option_bundle(crew)
    assert bundle.explanation.produced_by == "ai" and llm.calls == 2


def test_make_llm_is_template_unless_switched_on(monkeypatch):
    monkeypatch.delenv("MATCHMIND_AI_ENABLED", raising=False)
    assert isinstance(make_llm(), TemplateLLM)
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "true")
    assert isinstance(make_llm(), AzureOpenAILLM)  # client is built lazily: no network here
    with pytest.raises(LLMError):
        TemplateLLM().complete_json("s", {}, AnalystOut, 1.0)


# --------------------------------------------------------------- producer


def card(
    moment_id: str, t: float, priority: int = 60, slot="lower_third", team="NBR", players_=()
) -> OverlayCard:
    return OverlayCard(
        card_id=moment_id,
        moment_id=moment_id,
        kind=MomentKind.BIG_CHANCE,
        slot=slot,
        priority=priority,
        show_at_s=t,
        duration_s=7.0,
        persona="casual",
        language="en",
        headline="h",
        body="b",
        why="w",
        tactical_tag="chance_creation",
        evidence=[],
        player_ids=list(players_),
        team=team,
        produced_by="template",
    )


def test_producer_allows_one_lower_third_per_eight_seconds():
    state = ViewerState()
    profile = ViewerProfile()
    out = select([card("a", 100.0, 70), card("b", 101.0, 65), card("c", 102.0, 30)], profile, state)
    lower = [c for c in out if c.slot == "lower_third"]
    assert [c.moment_id for c in lower] == ["a"]
    assert {c.moment_id: c.slot for c in out} == {
        "a": "lower_third",
        "b": "side_panel",
    }  # c is minor: dropped
    later = select([card("d", 107.0, 70), card("e", 108.5, 70)], profile, state)
    assert [(c.moment_id, c.slot) for c in later] == [("d", "side_panel"), ("e", "lower_third")]
    assert select([card("a", 100.0, 70)], profile, state) == []  # de-duplicated
    # second half restarts the clock at 2700 s: an earlier clock is a fresh gap
    state.last_lower_third_s = 2800.0
    assert select([card("f", 2701.0, 70)], profile, state)[0].slot == "lower_third"


def test_producer_boosts_favourite_club_and_keeps_focus_player(moments):
    crew = Crew(TEAMS, llm=TemplateLLM())
    burst = next(b for b in bundles_from(crew, moments) if b.moment.kind == MomentKind.SPEED_BURST)
    plain = crew.render(burst, ViewerProfile(persona="fantasy"))
    fav = crew.render(burst, ViewerProfile(persona="fantasy", favourite_team="NBR"))
    assert fav.priority == plain.priority + 15 and fav.favourite_side is True and plain.favourite_side is None
    other = crew.render(burst, ViewerProfile(persona="fantasy", favourite_team="HCY"))
    assert other.favourite_side is False and other.priority == plain.priority
    # fantasy viewers do not get speed tags... unless it is their focus player
    assert select([plain], ViewerProfile(persona="fantasy"), ViewerState()) == []
    focus = ViewerProfile(persona="fantasy", focus_player_id="NBR-9")
    kept = crew.cards_for([burst], focus, ViewerState())
    assert len(kept) == 1 and kept[0].priority > plain.priority and kept[0].slot == "pitch_tag"
    # a focus-player lower third is demoted, never dropped
    state = ViewerState(last_lower_third_s=100.0)
    low = card("z", 101.0, 10, players_=["NBR-9"])
    assert select([low], ViewerProfile(focus_player_id="NBR-9"), state)[0].slot == "side_panel"


def test_metric_alerts_follow_the_focus_metric():
    crew = Crew(TEAMS, llm=TemplateLLM())
    state = ViewerState()
    profile = ViewerProfile(focus_metric="pressure", favourite_team="HCY", language="ja")
    pl = players()
    first_alerts = crew.metric_alerts(
        ev(1, EventType.PASS, 100.0),
        EventMetrics(event_id="a"),
        snap(100.0, away=window(pressure_index=20.0)),
        pl,
        profile,
        state,
    )
    assert first_alerts == []  # baseline only
    alerts = crew.metric_alerts(
        ev(2, EventType.PASS, 160.0),
        EventMetrics(event_id="b"),
        snap(160.0, away=window(pressure_index=37.0)),
        pl,
        profile,
        state,
    )
    assert len(alerts) == 1 and alerts[0].slot == "metric_alert" and alerts[0].favourite_side is True
    assert "37" in alerts[0].headline and "応援チーム" in alerts[0].headline
    small = crew.metric_alerts(
        ev(3, EventType.PASS, 200.0),
        EventMetrics(event_id="c"),
        snap(200.0, away=window(pressure_index=45.0)),
        pl,
        profile,
        state,
    )
    assert small == []  # moved 8 < 15
    hard = crew.metric_alerts(
        ev(4, EventType.PASS, 210.0, team="NBR", player_id="NBR-7", outcome=Outcome.COMPLETE),
        EventMetrics(event_id="d", pass_difficulty=80),
        snap(210.0),
        pl,
        ViewerProfile(focus_metric="pass_difficulty", focus_player_id="NBR-7"),
        ViewerState(),
    )
    assert len(hard) == 1 and "80" in hard[0].headline


# ------------------------------------------------------------------ recap


def test_player_of_the_match_is_deterministic():
    pl = players()
    assert player_of_the_match(pl).player_id == "NBR-9"
    tie = {
        "B-1": PlayerStats(player_id="B-1", team="NBR", goals=1),
        "A-1": PlayerStats(player_id="A-1", team="NBR", goals=1),
    }
    assert player_of_the_match(tie).player_id == "A-1"
    assert player_of_the_match({"A-1": PlayerStats(player_id="A-1", team="NBR")}) is None


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("persona", PERSONAS)
def test_recap_passes_fact_checker(moments, persona, language):
    crew = Crew(TEAMS, llm=TemplateLLM())
    crew._bundles = {b.moment.moment_id: b for b in bundles_from(crew, moments)}
    profile = ViewerProfile(persona=persona, language=language, favourite_team="NBR", focus_player_id="NBR-7")
    recap = crew.recap(snap(5500.0, period=2), players(), profile)
    assert recap.fact_check.ok, recap.fact_check.reasons
    assert 2 <= len(recap.summary_paragraphs) <= 3
    assert recap.player_of_the_match == "Adam Kerrigan" and recap.player_of_the_match_id == "NBR-9"
    assert recap.rtl == (language == "ar") and recap.key_moments
    for p in recap.summary_paragraphs:
        assert check(p, recap.stats, language, "paragraph").ok


def test_recap_rejects_ai_text_with_unbacked_numbers():
    def liar(schema, user):
        if schema is RecapOut:
            return RecapOut(title="Recap", headline="A 9-0 rout", summary_paragraphs=["It was 9-0.", "Huge."])
        return good_answer(schema, user)

    crew = Crew(TEAMS, llm=FakeLLM(answer=liar))
    recap = crew.recap(snap(1000.0), players(), ViewerProfile())
    assert recap.produced_by == "template" and recap.fact_check.ok and "9-0" not in recap.headline


# ------------------------------------------------------------ whole match


def test_demo_match_end_to_end_every_card_checks_out():
    from matchmind.stats.state import StatsEngine

    events = list(read_jsonl(DEMO))
    engine = StatsEngine(events[0].match_id, "NBR", "HCY")
    crew = Crew(TEAMS, llm=TemplateLLM())
    state = ViewerState()
    profile = ViewerProfile(persona="tactical", language="fr", favourite_team="HCY", focus_metric="momentum")
    bundles, cards = [], []
    for e in events:
        metrics = engine.process(e)
        snapshot, pl = engine.snapshot(), engine.players()
        new = crew.process(e, metrics, snapshot, pl)
        bundles += new
        cards += crew.cards_for(new, profile, state)
        cards += crew.metric_alerts(e, metrics, snapshot, pl, profile, state)
    kinds = {b.moment.kind for b in bundles}
    assert {
        MomentKind.GOAL,
        MomentKind.BETTER_OPTION,
        MomentKind.UNFOUND_RUN,
        MomentKind.PRESSURE_SPELL,
    } <= kinds
    assert crew.status().rejections == 0 and cards
    lowers = sorted(c.show_at_s for c in cards if c.slot == "lower_third")
    assert all(b - a >= 8 or b < a for a, b in zip(lowers, lowers[1:], strict=False))
    recap = crew.recap(engine.snapshot(), engine.players(), profile)
    assert recap.fact_check.ok and recap.title.startswith("Fin du match")
