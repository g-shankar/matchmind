"""Club heart: a fan of one club sees a different selection, priority and
framing of the same match, while every number stays the neutral fact."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from matchmind.crew import club_heart
from matchmind.crew.club_heart import RULES, frames_for, policy_markdown
from matchmind.crew.contracts import (
    PERSONAS,
    STUDIO_LANGUAGES,
    Moment,
    MomentKind,
    OverlayCard,
    ViewerProfile,
)
from matchmind.crew.crew import Crew
from matchmind.crew.fact_checker import check
from matchmind.crew.i18n import GLOSSARY_TERMS, PACKS, glossary_markdown
from matchmind.crew.llm import TemplateLLM
from matchmind.crew.producer import PERSONA_KINDS, ViewerState, card_priority, select, wanted
from matchmind.foundry import evaluation
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import TEAMS
from matchmind.stats.state import StatsEngine

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "backend" / "data" / "matches" / "MM-DEMO-001.jsonl"
MINOR = {MomentKind.SPEED_BURST, MomentKind.DISTANCE_MILESTONE, MomentKind.HARD_PASS}
VIEWERS = (None, "NBR", "HCY")
NAMES = {"NBR": "Northbridge FC", "HCY": "Harbour City"}


# --------------------------------------------------------------- fixtures


class Replay:
    def __init__(self) -> None:
        events = list(read_jsonl(DEMO))
        engine = StatsEngine(events[0].match_id, "NBR", "HCY")
        self.crew = Crew(TEAMS, llm=TemplateLLM())
        self.ticks = []
        self.bundles = []
        for e in events:
            metrics = engine.process(e)
            snapshot, players = engine.snapshot(), engine.players()
            new = self.crew.process(e, metrics, snapshot, players)
            self.ticks.append((e, metrics, snapshot, players, new))
            self.bundles += new
        self.by_id = {b.moment.moment_id: b for b in self.bundles}
        self.facts_before = copy.deepcopy({k: b.moment.facts for k, b in self.by_id.items()})

    def watch(self, profile: ViewerProfile) -> list[OverlayCard]:
        """The whole match for one viewer, tick by tick, as the live session does."""
        state = ViewerState()
        cards: list[OverlayCard] = []
        for e, metrics, snapshot, players, new in self.ticks:
            cards += self.crew.cards_for(new, profile, state)
            if profile.focus_metric:
                cards += self.crew.metric_alerts(e, metrics, snapshot, players, profile, state)
        return cards


def standing_goals(cards: list[OverlayCard]) -> list[OverlayCard]:
    """Goal cards a later correction card (VAR) did not rule out."""
    ruled = {mid for c in cards for mid in c.retracts}
    return [c for c in cards if c.kind == MomentKind.GOAL and c.moment_id not in ruled]


@pytest.fixture(scope="module")
def replay() -> Replay:
    return Replay()


def moment(kind: MomentKind, team: str | None = "Northbridge FC", clock_s: float = 600.0, **facts) -> Moment:
    base = {"home": "Northbridge FC", "away": "Harbour City", "match_clock": "10:00"}
    if team:
        base |= {"team": team, "opp": "Harbour City" if team == "Northbridge FC" else "Northbridge FC"}
    return Moment(
        moment_id=f"{kind.value}-x",
        kind=kind,
        clock_s=clock_s,
        match_clock="10:00",
        period=1 if clock_s < 2700 else 2,
        team={"Northbridge FC": "NBR", "Harbour City": "HCY"}.get(team or ""),
        facts=base | facts,
        source_event_ids=["e"],
        priority=60,
    )


# ------------------------------------------------------------- the table


def test_policy_has_one_row_per_moment_kind():
    kinds = [r.kind for r in club_heart.POLICY]
    assert sorted(kinds) == sorted(MomentKind) and len(kinds) == len(set(kinds))
    assert set(club_heart.METRIC_RULES) == {"pressure", "xg", "pass_difficulty", "top_speed", "momentum"}
    for rule in club_heart.POLICY:
        assert rule.own.show and rule.own.boost == club_heart.OWN_BOOST
        assert rule.rival.boost <= 0  # a rival moment never outranks the same moment for a neutral
        assert rule.note


def test_docs_tables_are_generated_from_the_code():
    personalisation = (ROOT / "docs" / "PERSONALISATION.md").read_text(encoding="utf-8")
    assert policy_markdown() in personalisation, "regenerate the club-heart table in docs/PERSONALISATION.md"
    languages = (ROOT / "docs" / "LANGUAGES.md").read_text(encoding="utf-8")
    assert glossary_markdown() in languages, "regenerate the glossary table in docs/LANGUAGES.md"


@pytest.mark.parametrize("language", STUDIO_LANGUAGES)
def test_every_pack_has_every_frame_and_glossary_term(language):
    p = PACKS[language]
    assert set(p["glossary"]) == set(GLOSSARY_TERMS)
    for frame in club_heart.all_frames():
        assert p["heart"][frame]["casual"], (language, frame)
    assert set(p["heart"]) == set(club_heart.all_frames())
    for rule in club_heart.METRIC_POLICY:
        assert p["metric"][rule.own_template]
        if rule.rival_template:
            assert p["metric"][rule.rival_template]
    text = repr(p)
    for key in GLOSSARY_TERMS:
        assert "{g_" + key + "}" in text, f"{language}: glossary term {key} is not used by any template"


def test_fantasy_templates_use_only_our_own_stats():
    """No game points, bonus systems or real-league fantasy branding in the
    Stats scout voice (API value `fantasy`)."""
    banned = re.compile(r"points?|puntos|bonus|BPS|FPL|fantasy|fantas|نقاط|ポイント|ボーナス", re.IGNORECASE)
    for language, p in PACKS.items():
        texts = [t for kind in p["narr"].values() for option in kind.get("fantasy", []) for t in option]
        texts += [t for frame in p["heart"].values() for option in frame.get("fantasy", []) for t in option]
        texts.append(p["recap"]["potm"]["fantasy"])
        for text in texts:
            assert not banned.search(text), (language, text)


# --------------------------------------------------------------- framing


@pytest.mark.parametrize(
    ("team", "home", "away", "clock_s", "fan", "expected"),
    [
        ("Northbridge FC", 1, 0, 600, "Northbridge FC", ["goal_for_lead", "goal_for"]),
        ("Northbridge FC", 2, 0, 600, "Northbridge FC", ["goal_for"]),
        ("Northbridge FC", 1, 1, 600, "Northbridge FC", ["goal_for_level", "goal_for"]),
        ("Northbridge FC", 1, 2, 600, "Northbridge FC", ["goal_for_pull_back", "goal_for"]),
        ("Harbour City", 2, 1, 4000, "Northbridge FC", ["goal_against_lead_cut", "goal_against"]),
        ("Harbour City", 2, 2, 5000, "Northbridge FC", ["goal_against_level", "goal_against"]),
        ("Harbour City", 0, 1, 600, "Northbridge FC", ["goal_against"]),
        ("Harbour City", 2, 3, 5543, "Northbridge FC", ["goal_against_late", "goal_against"]),
        ("Harbour City", 2, 3, 5543, "Harbour City", ["goal_for_lead", "goal_for"]),
        ("Harbour City", 2, 3, 5543, None, []),
        ("Harbour City", 2, 3, 5543, "Another Club", []),
    ],
)
def test_goal_frames_follow_the_score_from_the_fans_side(team, home, away, clock_s, fan, expected):
    m = moment(MomentKind.GOAL, team, clock_s, score_home=home, score_away=away)
    assert frames_for(m, fan) == expected


def test_other_frames():
    fan = "Harbour City"
    assert frames_for(moment(MomentKind.BIG_CHANCE), fan) == ["let_off"]
    assert frames_for(moment(MomentKind.BIG_CHANCE), "Northbridge FC") == []
    assert frames_for(moment(MomentKind.ROCKET_SHOT, outcome="saved"), fan) == ["let_off_shot"]
    assert frames_for(moment(MomentKind.ROCKET_SHOT, outcome="goal"), fan) == []  # voiced as the goal
    assert frames_for(moment(MomentKind.BETTER_OPTION), "Northbridge FC") == ["lesson_choice"]
    assert frames_for(moment(MomentKind.SPEED_BURST), fan) == []  # dropped, never voiced
    ft = moment(MomentKind.MILESTONE, None, phase="full_time", score_home=2, score_away=3)
    assert frames_for(ft, fan) == ["full_time_won"]
    assert frames_for(ft, "Northbridge FC") == ["full_time_lost"]
    level = moment(MomentKind.MILESTONE, None, phase="full_time", score_home=1, score_away=1)
    assert frames_for(level, fan) == ["full_time_drawn"]
    assert (
        frames_for(moment(MomentKind.MILESTONE, None, phase="half_time", score_home=2, score_away=0), fan)
        == []
    )


# ----------------------------------------------------- selection, priority


def _card(
    kind: MomentKind, team: str | None, priority: int = 60, players: list[str] | None = None
) -> OverlayCard:
    return OverlayCard(
        card_id=f"{kind.value}-{team}",
        moment_id=f"{kind.value}-{team}",
        kind=kind,
        slot="pitch_tag",
        priority=priority,
        show_at_s=100.0,
        duration_s=4.0,
        persona="casual",
        language="en",
        headline="h",
        body="b",
        why="w",
        tactical_tag="pace",
        evidence=[],
        player_ids=players or [],
        team=team,
        produced_by="template",
    )


def test_rival_minor_moments_are_dropped_unless_they_are_the_focus_player():
    for kind in MINOR:
        persona = "casual" if kind in PERSONA_KINDS["casual"] else "tactical"
        fan = ViewerProfile(persona=persona, favourite_team="NBR")
        assert wanted(_card(kind, "NBR"), fan) and not wanted(_card(kind, "HCY"), fan)
        assert wanted(_card(kind, "HCY"), ViewerProfile(persona=persona))  # a neutral still gets it
    fan = ViewerProfile(favourite_team="NBR")
    focus = ViewerProfile(favourite_team="NBR", focus_player_id="HCY-9")
    assert wanted(_card(MomentKind.SPEED_BURST, "HCY", players=["HCY-9"]), focus)
    alert = _card(MomentKind.SPEED_BURST, "HCY").model_copy(update={"slot": "metric_alert"})
    assert wanted(alert, fan)
    assert wanted(_card(MomentKind.MILESTONE, None), fan)  # kick-off, half-time, full-time


def test_priority_is_clamped_and_follows_the_table():
    m = moment(MomentKind.MOMENTUM_SWING, "Harbour City").model_copy(update={"priority": 5})
    assert card_priority(m, ViewerProfile(favourite_team="NBR")) == 0
    m = m.model_copy(update={"priority": 95, "player_ids": ["HCY-9"]})
    assert card_priority(m, ViewerProfile(favourite_team="HCY", focus_player_id="HCY-9")) == 100
    assert card_priority(m, ViewerProfile(favourite_team="NBR")) == 85


# ------------------------------------------------- the whole demo match


def test_three_viewers_get_different_cards_with_identical_numbers(replay):
    """NBR fan, HCY fan and a neutral watch the whole demo match: different
    selection, priority and framing; every number is the neutral fact."""
    watched = {fan: replay.watch(ViewerProfile(favourite_team=fan)) for fan in VIEWERS}
    ids = {fan: [c.moment_id for c in cards] for fan, cards in watched.items()}
    for cards in ids.values():
        assert len(cards) == len(set(cards))  # de-duplicated per viewer

    # selection: each fan loses the rival's minor moments, and only those
    neutral_ids = set(ids[None])
    for fan in ("NBR", "HCY"):
        rival = "HCY" if fan == "NBR" else "NBR"
        dropped = neutral_ids - set(ids[fan])
        assert dropped, fan
        for mid in dropped:
            m = replay.by_id[mid].moment
            assert m.team == rival and not RULES[m.kind].rival.show, (fan, mid, m.kind)
        assert not any(c.team == rival and c.kind in MINOR for c in watched[fan])
    assert set(ids["NBR"]) != set(ids["HCY"])

    neutral = {c.moment_id: c for c in watched[None]}
    framed = {"NBR": 0, "HCY": 0}
    for fan in ("NBR", "HCY"):
        for card in watched[fan]:
            m = replay.by_id[card.moment_id].moment
            base = neutral.get(card.moment_id)
            # priority: exactly the table's boost over the neutral's, clamped
            expected = max(0, min(100, m.priority + club_heart.boost(m.kind, m.team, fan)))
            assert card.priority == expected
            assert card.favourite_side == (None if m.team is None else m.team == fan)
            if base is None:
                continue
            # numbers: the same evidence, and every printed number is a fact
            assert [e.model_dump() for e in card.evidence] == [e.model_dump() for e in base.evidence]
            for field in ("headline", "body", "why"):
                text = getattr(card, field)
                assert check(text, m.facts, "en", field).ok, (fan, field, text)
            if frames_for(m, NAMES[fan]):
                framed[fan] += 1
                assert (card.headline, card.body) != (base.headline, base.body)
    # framing: every goal, let-off and lesson reads differently for each fan
    assert framed["NBR"] >= 10 and framed["HCY"] >= 10, framed
    goals = {fan: [c.headline for c in standing_goals(watched[fan])] for fan in VIEWERS}
    assert len(goals[None]) == 5
    for a, b in zip(goals["NBR"], goals["HCY"], strict=True):
        assert a != b
    # the bundles (the facts) were never touched by any viewer
    assert {k: b.moment.facts for k, b in replay.by_id.items()} == replay.facts_before


def test_the_demo_storyline_reads_from_each_side(replay):
    def headlines(fan: str) -> list[str]:
        return [c.headline for c in standing_goals(replay.watch(ViewerProfile(favourite_team=fan)))]

    nbr, hcy = headlines("NBR"), headlines("HCY")
    assert nbr[0] == "GOAL! Kerrigan puts your team in front" and nbr[-1] == "Late blow: Clarke scores"
    assert hcy[2] == "Varga pulls a goal back!" and hcy[3].startswith("Level!")
    assert hcy[-1] == "GOAL! Clarke puts your team in front"
    ft = {
        fan: [c for c in replay.watch(ViewerProfile(favourite_team=fan)) if c.kind == MomentKind.MILESTONE][
            -1
        ]
        for fan in ("NBR", "HCY")
    }
    assert ft["NBR"].headline == "Full-time: defeat for your team"
    assert ft["HCY"].headline == "Full-time: your team win!"


@pytest.mark.parametrize("language", STUDIO_LANGUAGES)
@pytest.mark.parametrize("persona", PERSONAS)
def test_persona_by_club_matrix(replay, persona, language):
    """Every persona x language x club over the whole match: every moment
    renders, framed cards pass the evaluation suite, the policy holds."""
    rejections = replay.crew.status().rejections
    for fan in VIEWERS:
        focus = "NBR-9" if persona == "player_spotlight" else None
        profile = ViewerProfile(persona=persona, language=language, favourite_team=fan, focus_player_id=focus)
        for bundle in replay.bundles:
            m = bundle.moment
            card = replay.crew.render(bundle, profile)
            assert card is not None, (persona, language, fan, m.kind)
            for field in ("headline", "body", "why"):
                assert check(getattr(card, field), m.facts, language, field).ok, (
                    fan,
                    field,
                    getattr(card, field),
                )
            if fan and frames_for(m, NAMES[fan]) and not (focus and focus in m.player_ids):
                record = {
                    "type": "card",
                    "persona": persona,
                    "language": language,
                    "facts": dict(m.facts),
                    "headline": card.headline,
                    "body": card.body,
                    "response": f"{card.headline}\n{card.body}",
                    "focus_player": None,
                }
                for name in ("groundedness_numbers", "length", "persona_vocab", "language"):
                    ok, reason = evaluation.EVALUATORS[name](record)
                    assert ok, (name, reason, persona, language, fan, card.headline, card.body)
        cards = replay.watch(profile)
        if fan:
            rival = "HCY" if fan == "NBR" else "NBR"
            assert not any(
                c.team == rival and c.kind in MINOR and not (focus and focus in c.player_ids) for c in cards
            )
    assert replay.crew.status().rejections == rejections


@pytest.mark.parametrize("language", ["ar", "ja"])
def test_rtl_and_japanese_punctuation(replay, language):
    cards = replay.watch(ViewerProfile(language=language, favourite_team="HCY"))
    framed = [c for c in cards if frames_for(replay.by_id[c.moment_id].moment, "Harbour City")]
    assert framed
    for c in framed:
        text = c.headline + c.body
        if language == "ar":
            assert c.rtl and re.search(r"[؀-ۿ]", text)
            assert not re.search(r"[A-Za-z],|;", re.sub(r"xG|km/h", "", text)), (
                text
            )  # Arabic comma and semicolon
        else:
            assert not c.rtl and re.search(r"[぀-ヿ]", text)
            assert c.body.endswith(("。", "！")) and ". " not in c.body, c.body


def test_metric_alerts_follow_the_club(replay):
    """Momentum is one number: a fan sees moves both ways, the rival's as a
    warning; pressure alerts follow only the fan's club."""
    nbr = replay.watch(ViewerProfile(favourite_team="NBR", focus_metric="momentum"))
    alerts = [c for c in nbr if c.slot == "metric_alert"]
    against = [c for c in alerts if c.team == "HCY"]
    assert against and all("away from your team" in c.body for c in against)
    assert all("away from your team" not in c.body for c in alerts if c.team == "NBR")
    pressure = replay.watch(ViewerProfile(favourite_team="HCY", focus_metric="pressure"))
    assert {c.team for c in pressure if c.slot == "metric_alert"} == {"HCY"}
    neutral = replay.watch(ViewerProfile(focus_metric="pressure"))
    assert {c.team for c in neutral if c.slot == "metric_alert"} == {"NBR", "HCY"}


def test_select_keeps_fan_cards_in_priority_order(replay):
    fan = ViewerProfile(favourite_team="HCY")
    cards = [replay.crew.render(b, fan) for b in replay.bundles[:40]]
    chosen = select([c for c in cards if c], fan, ViewerState())
    assert [c.priority for c in chosen] == sorted((c.priority for c in chosen), reverse=True)
