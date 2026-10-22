"""Trust layer: per-sentence claims, the bounded sanity checks, cross-persona and
cross-language fact parity, the moment audit route and the crew's service levels."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import FAKE_ENGINES, FakeClock, make_events
from matchmind.api import app as app_mod
from matchmind.api.app import create_app
from matchmind.api.session import Engines, MatchSession, load_events
from matchmind.crew import claims as claims_mod
from matchmind.crew.audit import moment_audit
from matchmind.crew.claims import card_claims, fact_parity, split_sentences, text_claims
from matchmind.crew.commentator import CommentatorOut
from matchmind.crew.contracts import (
    PERSONAS,
    STUDIO_LANGUAGES,
    MomentKind,
    OverlayCard,
    Recap,
    ViewerProfile,
)
from matchmind.crew.crew import Crew
from matchmind.crew.fact_checker import check, number_spans, sanity_problems
from matchmind.crew.llm import ModelBudget, TemplateLLM
from matchmind.crew.recap import RecapOut
from matchmind.crew.telemetry import HealthTracker, percentile
from matchmind.crew.translator import OffTranslator
from matchmind.foundry.evaluation import _replay, match_files
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import TEAMS, get_team
from matchmind.stats.state import StatsEngine
from test_crew import FakeLLM, better_option_bundle, bundles_from, first, good_answer, moments  # noqa: F401
from test_translator import FakeAzure, service

SCORE_FACTS = {
    "home": "Northbridge FC",
    "away": "Harbour City",
    "score_home": 2,
    "score_away": 1,
    "xg_home": 1.94,
    "xg_away": 1.08,
    "shots_home": 13,
    "shots_away": 6,
}


def template_crew() -> Crew:
    return Crew(
        TEAMS, llm=TemplateLLM(), budget=ModelBudget(total=0, per_minute=0), translator=OffTranslator()
    )


# ------------------------------------------------------------- sentences


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Shot at 0.05 xG. The pass was 3.1x better!", ["Shot at 0.05 xG.", "The pass was 3.1x better!"]),
        (
            "Kerrigan passes 12 km (est.) for Northbridge FC",
            ["Kerrigan passes 12 km (est.) for Northbridge FC"],
        ),
        (
            "هل كان على Asante أن يمرر؟ التمريرة كانت أفضل.",
            ["هل كان على Asante أن يمرر؟", "التمريرة كانت أفضل."],
        ),
        ("ゴール！スコアは1-0。重要な場面です", ["ゴール！", "スコアは1-0。", "重要な場面です"]),
        ("«Quoted.» Next one?", ["«Quoted.»", "Next one?"]),
        ("", []),
    ],
)
def test_sentences_split_by_script(text, expected):
    assert split_sentences(text) == expected


# ---------------------------------------------------------------- claims


def test_template_claims_bind_each_number_to_its_fact_key(moments):  # noqa: F811
    crew = template_crew()
    m = first(moments, MomentKind.BETTER_OPTION)
    (bundle,) = bundles_from(crew, [m])
    card = crew.render(bundle, ViewerProfile(persona="casual"))
    by_sentence = {c.sentence: c for c in card.claims}
    times = next(c for s, c in by_sentence.items() if "x more than the shot" in s)
    assert times.check == "verified_numeric" and times.fact_keys == ["times_better"]
    assert [(b.text, b.fact_key, b.unit) for b in times.bindings if b.kind == "number"] == [
        (str(m.facts["times_better"]).removesuffix(".0"), "times_better", "x")
    ]
    assert times.source_event_ids == m.source_event_ids
    assert "wording not machine-checked" in times.reason
    names = next(c for c in card.claims if c.field == "headline")
    assert names.check == "verified_name"
    assert {b.entity_id for b in names.bindings if b.kind == "name"} == {m.player_ids[0]}
    # Every field is covered, sentence by sentence.
    assert {c.field for c in card.claims} == {"headline", "body", "why"}
    assert sum(c.field == "body" for c in card.claims) == len(split_sentences(card.body))


def test_wording_only_sentence_is_marked_unverified_never_verified():
    claim = text_claims("Something may have to give.", "body", {"team": "Northbridge FC"}, "en")[0]
    assert claim.check == "unverified_text"
    assert "not machine-verified" in claim.reason and claim.fact_keys == []


def test_template_knows_keys_even_when_two_facts_share_a_value():
    # "{shots_home} for {home}, {shots_away} for {away}" with equal values: the template says which is which.
    facts = {**SCORE_FACTS, "shots_home": 6, "shots_away": 6}
    tpl = "Shots so far: {shots_home} for {home}, {shots_away} for {away}."
    claim = text_claims(
        "Shots so far: 6 for Northbridge FC, 6 for Harbour City.", "body", facts, "en", template=tpl
    )[0]
    assert claim.fact_keys == ["shots_home", "home", "shots_away", "away"]


def test_model_text_binds_by_value_closest_first_and_by_unit():
    facts = {"xg": 0.13, "score_away": 0, "distance_m": 18, "shot_speed_kmh": 18}
    claim = text_claims("A 0 xG miss? No: 0 goals, 18 m out at 18 km/h.", "body", facts, "en")
    numbers = [(b.text, b.fact_key) for c in claim for b in c.bindings if b.kind == "number"]
    assert ("18", "distance_m") in numbers and ("18", "shot_speed_kmh") in numbers
    assert numbers[1] == ("0", "score_away")  # exact value before a rounded one


def test_unbacked_number_makes_the_claim_unverified_with_the_reason():
    claim = text_claims("He ran 99 km.", "body", {"milestone_km": 2}, "en")[0]
    assert claim.check == "unverified_text" and claim.reason.startswith("number 99 is not in the facts")


def test_old_payloads_without_claims_still_parse():
    card = OverlayCard.model_validate(
        {
            "card_id": "c",
            "moment_id": "m",
            "kind": "goal",
            "slot": "lower_third",
            "priority": 50,
            "show_at_s": 1,
            "duration_s": 1,
            "persona": "casual",
            "language": "en",
            "headline": "h",
            "body": "b",
            "why": "w",
            "tactical_tag": "t",
            "evidence": [],
            "produced_by": "template",
        }
    )
    assert card.claims == []


# ---------------------------------------------------------- sanity checks


def test_unit_must_match_the_fact_it_prints():
    facts = {"pass_distance_m": 16, "shot_speed_kmh": 104}
    assert check("A 16 m pass at 104 km/h.", facts).ok
    bad = check("A 16 km/h pass.", facts)
    assert not bad.ok and any(r.startswith("unit:") for r in bad.reasons)
    assert not check("時速16kmのパス", facts, "ja").ok  # 時速 marks a speed in Japanese
    assert check("時速104kmのシュート、16mのパス", facts, "ja").ok


def test_percentage_over_100_is_rejected():
    assert any(r.startswith("range:") for r in check("A 120% chance", {"pass_success_pct": 120}).reasons)


@pytest.mark.parametrize(
    "text, ok",
    [
        ("Northbridge FC 2, Harbour City 1.", True),
        ("Harbour City 2, Northbridge FC 1.", False),
        ("xG: Northbridge FC 1.94, Harbour City 1.08.", True),
        ("xG: Northbridge FC 1.08, Harbour City 1.94.", False),
        ("Northbridge FC 2-1 Harbour City.", True),
        ("Harbour City 1-2 Northbridge FC.", True),
        ("Harbour City 2-1 Northbridge FC.", False),
        ("Northbridge FC beat Harbour City 2-1.", True),  # winner first: not a club-adjacent scoreline
        ("Shots: 13 for Northbridge FC, 6 for Harbour City.", True),
    ],
)
def test_per_club_numbers_must_belong_to_the_club_named(text, ok):
    result = check(text, SCORE_FACTS)
    assert result.ok is ok, result.reasons
    if not ok:
        assert any(r.startswith("attribution:") for r in result.reasons)


@pytest.mark.parametrize(
    "text, facts, ok",
    [
        ("The pass (0.24 xG) was more than the shot's 0.05 xG.", {"alt_xg": 0.24, "shot_xg": 0.05}, True),
        ("The shot at 0.05 xG was more than the pass at 0.24 xG.", {"alt_xg": 0.24, "shot_xg": 0.05}, False),
        ("0.05 xG is less than 0.24 xG.", {"alt_xg": 0.24, "shot_xg": 0.05}, True),
        ("The pass was 0.8x more valuable.", {"times_better": 0.8}, False),
        ("The pass was 3.1x more valuable.", {"times_better": 3.1}, True),
    ],
)
def test_comparisons_must_point_the_right_way(text, facts, ok):
    result = check(text, facts)
    assert result.ok is ok, result.reasons


def test_squad_name_not_in_the_facts_is_rejected_only_with_a_roster():
    facts = {"player": "Adam Kerrigan", "player_short": "Kerrigan", "xg": 0.42}
    roster = ("Adam Kerrigan", "Kerrigan", "Niall Prescott", "Prescott", "Harbour City")
    assert check("Kerrigan scores from a 0.42 xG chance.", facts, roster=roster).ok
    bad = check("Prescott scores from a 0.42 xG chance.", facts, roster=roster)
    assert bad.reasons == ["name Prescott is not in the facts"]
    assert check("Prescott scores from a 0.42 xG chance.", facts).ok  # no roster: old behaviour


def test_negation_is_documented_as_out_of_scope():
    # A known limit, pinned so the docs stay honest: the checker reads numbers and names, not meaning.
    assert check("Kerrigan did not score from 0.42 xG.", {"player_short": "Kerrigan", "xg": 0.42}).ok
    assert any("Negation" in line for line in claims_mod.NOT_CHECKED)


def test_number_spans_skip_clocks_and_names_and_keep_positions():
    text = "Pass on at 67:28; ٣٫١x better, 1,000 m"
    spans = number_spans(text, "en", {"pass_on_clock": "67:28"})
    assert [(s.token, s.unit) for s in spans] == [("3.1", "x"), ("1000", "m")]
    assert text[spans[0].start : spans[0].end] == "٣٫١"
    assert (
        sanity_problems(text, {"pass_on_clock": "67:28", "times_better": 3.1, "pass_distance_m": 1000}) == []
    )


def test_model_text_naming_the_wrong_player_falls_back_to_the_template():
    def wrong_player(schema, user):
        if schema is CommentatorOut:
            return CommentatorOut(headline="Prescott should have squared it", body="He chose the shot.")
        return good_answer(schema, user)

    crew = Crew(TEAMS, llm=FakeLLM(answer=wrong_player))
    bundle = better_option_bundle(crew)
    card = crew.render(bundle, ViewerProfile())
    assert card.produced_by == "template" and "Prescott" not in card.headline
    assert card.fallback_reason == "fact_check: headline: name Prescott is not in the facts"


def test_model_text_gets_matched_claims():
    crew = Crew(TEAMS, llm=FakeLLM(answer=good_answer))
    bundle = better_option_bundle(crew)
    card = crew.render(bundle, ViewerProfile())
    assert card.produced_by == "ai"
    body = next(c for c in card.claims if c.field == "body")
    assert body.check == "verified_numeric" and body.fact_keys == ["alt_value"]
    assert "matched to facts" in body.reason
    why = next(c for c in card.claims if c.field == "why")
    assert why.fact_keys == ["times_better"]


# ------------------------------------------------------------------ recap


def test_recap_claims_cover_every_sentence_and_point_at_goal_events():
    events = read_jsonl(match_files()[0])
    crew, stats, bundles = _replay(events)
    recap: Recap = crew.recap(stats.snapshot(), stats.players(), ViewerProfile(persona="casual"))
    fields = {c.field for c in recap.claims}
    assert {"title", "headline", "paragraph", "key_moment"} <= fields
    goals = [b.moment for b in bundles if b.moment.kind == MomentKind.GOAL]
    goal_line = next(c for c in recap.claims if "goals_line" in c.fact_keys)
    assert set(goal_line.source_event_ids) >= {goals[0].source_event_ids[0]}
    key = next(c for c in recap.claims if c.field == "key_moment")
    assert key.source_event_ids  # each key-moment line points at its own events
    assert all(c.check != "unverified_text" or c.reason.startswith("no number") for c in recap.claims)


# ----------------------------------------------------------------- parity


def _sweep_match(path):
    crew, _, bundles = _replay(read_jsonl(path))
    out = []
    for b in bundles:
        m = b.moment
        cards, withheld = [], 0
        for persona in PERSONAS:
            focus = m.player_ids[0] if persona == "player_spotlight" and m.player_ids else None
            for language in STUDIO_LANGUAGES:
                card = crew.render(
                    b, ViewerProfile(persona=persona, language=language, focus_player_id=focus)
                )
                if card is None:
                    withheld += 1
                else:
                    cards.append(card)
        out.append((m, cards, fact_parity(m, cards, withheld)))
    return out


@pytest.fixture(scope="module")
def sweep():
    return [item for path in match_files() for item in _sweep_match(path)]


def test_parity_holds_for_every_moment_persona_and_studio_language(sweep):
    assert len({p.parent for p in match_files()}) == 1 and len(match_files()) == 5
    failures = [(m.moment_id, p.problems[:3]) for m, _, p in sweep if not p.ok]
    assert failures == []
    assert len(sweep) >= 300
    assert all(p.renderings + p.withheld == 20 for _, _, p in sweep)
    # Every shown sentence carries a claim, and none of them failed a check.
    for _, cards, _ in sweep:
        for card in cards:
            assert card.claims
            assert all(c.check != "unverified_text" or c.reason.startswith("no number") for c in card.claims)


def test_parity_catches_a_language_that_drops_a_key_fact(sweep):
    m, cards, _ = next(item for item in sweep if item[0].kind == MomentKind.GOAL)
    broken = []
    for card in cards:
        if (card.persona, card.language) == ("casual", "es"):
            headline, body = "¡GOL!", "Qué partido."
            card = card.model_copy(
                update={
                    "headline": headline,
                    "body": body,
                    "claims": card_claims(m, headline, body, "", "es"),
                }
            )
        broken.append(card)
    result = fact_parity(m, broken)
    assert not result.ok
    assert any(p.startswith("casual/es: key facts differ") for p in result.problems)
    assert any(p.startswith("casual/es: does not say who or what") for p in result.problems)


def test_parity_catches_a_number_outside_the_facts(sweep):
    m, cards, _ = next(item for item in sweep if item[0].kind == MomentKind.GOAL)
    card = cards[0]
    lie = card.model_copy(update={"claims": card_claims(m, card.headline, "It ends 7-0.", "", card.language)})
    result = fact_parity(m, [lie, *cards[1:]])
    assert not result.ok and any("number 7 is not in the facts" in p for p in result.problems)


def test_parity_includes_translated_world_languages():
    crew = Crew(TEAMS, llm=TemplateLLM(), translator=service(FakeAzure()))
    bundle = better_option_bundle(crew)
    english = crew.render(bundle, ViewerProfile(language="en"))
    german = crew.render(bundle, ViewerProfile(language="de"))
    assert german.translated_by == "azure_ai_translator"
    assert german.claims and german.claims[0].sentence.startswith("«de»")
    result = fact_parity(bundle.moment, [english, german], sources=["template_sweep", "live"])
    assert result.ok, result.problems
    assert result.stated["casual/de (live)"] == result.stated["casual/en"]


# ------------------------------------------------------------------ audit


def _real_session(llm=None) -> MatchSession:
    events = load_events()
    home, away = str(events[0].details["home"]), str(events[0].details["away"])
    teams = {home: get_team(home), away: get_team(away)}
    engines = Engines(
        stats=StatsEngine,
        crew=lambda t: Crew(t, llm=llm or TemplateLLM(), translator=OffTranslator()),
        bookmark_crew=lambda t: Crew(t, llm=TemplateLLM(), translator=OffTranslator()),
    )
    return MatchSession(events, teams=teams, engines=engines, clock=FakeClock(), base_rate=10)


@pytest.fixture(scope="module")
def real_session():
    return _real_session()


def test_audit_has_facts_evidence_claims_parity_and_trace(real_session):
    mid = next(b.moment_id for b in real_session.bookmarks if b.kind == "better_option")
    audit = real_session.moment_audit(mid)
    assert audit is not None and audit.moment_id == mid
    assert audit.facts["times_better"] and audit.source_event_ids
    assert audit.explanation.evidence
    assert len(audit.renderings) == 20 and {r.source for r in audit.renderings} == {"template_sweep"}
    assert all(r.fact_check.ok and r.claims for r in audit.renderings)
    assert audit.parity.ok and audit.parity.key_facts == ["player", "teammate", "times_better"]
    assert audit.trace and audit.trace[0].agent == "spotter"
    assert audit.not_checked
    assert real_session.moment_audit("nope") is None


def test_audit_never_calls_the_model_and_shows_live_cards():
    llm = FakeLLM(answer=good_answer)
    session = _real_session(llm=llm)
    mid = next(b.moment_id for b in session.bookmarks if b.kind == "better_option")
    assert llm.calls == 0  # the load-time pass is template-only
    audit = session.moment_audit(mid)
    assert llm.calls == 0 and {r.source for r in audit.renderings} == {"template_sweep"}
    session.card_for_moment(mid, ViewerProfile())  # a viewer asks: one model call
    calls = llm.calls
    audit = session.moment_audit(mid)
    assert llm.calls == calls  # the audit only reads the live cache
    live = [r for r in audit.renderings if r.source == "live"]
    # The model wrote the headline and body; the explanation came from the template pre-pass.
    assert len(live) == 1 and live[0].fact_check.ok
    assert {c.origin for c in live[0].claims if c.field in ("headline", "body")} == {"matched"}
    # Read-only: asking again changes nothing the live crew reports.
    before = session.crew.status().model_dump()
    session.moment_audit(mid)
    assert session.crew.status().model_dump() == before
    # After a reset (a seek), the live cache is gone and the audit still answers from the sweep.
    session.reset()
    audit = session.moment_audit(mid)
    assert {r.source for r in audit.renderings} == {"template_sweep"} and audit.trace
    assert audit.parity.ok, audit.parity.problems


def test_audit_route_shape_404_and_rate_limit(real_session):
    clock = FakeClock()
    app = create_app(
        session=real_session, tick_interval=None, allowed_origins=[], static_dir="/nonexistent", clock=clock
    )
    mid = next(b.moment_id for b in real_session.bookmarks if b.kind == "goal")
    with TestClient(app) as client:
        r = client.get(f"/api/match/moment/{mid}/audit")
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        data = r.json()
        assert set(data) >= {"facts", "source_event_ids", "explanation", "renderings", "parity", "trace"}
        assert data["renderings"][0]["claims"][0]["check"] in (
            "verified_numeric",
            "verified_name",
            "unverified_text",
        )
        assert len(r.content) < 200_000  # bounded
        assert client.get("/api/match/moment/nope/audit").status_code == 404
        assert client.get(f"/api/match/moment/{'x' * 81}/audit").status_code == 404
        codes = [
            client.get(f"/api/match/moment/{mid}/audit").status_code for _ in range(app_mod.GET_BURST + 3)
        ]
        assert 429 in codes and codes.count(200) <= app_mod.GET_BURST


def test_audit_route_with_a_stand_in_crew_still_answers():
    session = MatchSession(make_events(), engines=FAKE_ENGINES, clock=FakeClock(), base_rate=10)
    app = create_app(session=session, tick_interval=None, allowed_origins=[], static_dir="/nonexistent")
    with TestClient(app) as client:
        r = client.get("/api/match/moment/goal-MM-TEST-001-00007/audit")
        assert r.status_code == 200
        assert r.json()["renderings"] and r.json()["renderings"][0]["claims"]


def test_audit_function_is_bounded_in_live_cards():
    crew = template_crew()
    bundle = better_option_bundle(crew)
    for language in STUDIO_LANGUAGES:
        for persona in PERSONAS:
            crew.render(bundle, ViewerProfile(persona=persona, language=language))
    audit = moment_audit(bundle, template_crew(), crew)
    assert len([r for r in audit.renderings if r.source == "live"]) == 16


# -------------------------------------------------------------- telemetry


def test_percentile_is_nearest_rank():
    ms = [float(i) for i in range(1, 101)]
    assert percentile(ms, 0.5) == 50 and percentile(ms, 0.95) == 95 and percentile([], 0.5) == 0


def test_health_tracker_is_deterministic_and_bounded():
    now = [100.0]
    h = HealthTracker(clock=lambda: now[0], window=10)
    for i in range(1, 31):
        h.step("commentator", float(i), "fallback" if i % 5 == 0 else "ok")
    h.step("spotter", 2.0, "ok")
    for ok in (True, True, False, True):
        h.verdict(ok)
    h.moments(3)
    now[0] += 30
    h.moments(2)
    snap = h.snapshot()
    commentator = next(a for a in snap.latency if a.agent == "commentator")
    assert commentator.samples == 10  # only the last 10 of 30 are kept
    assert (commentator.p50_ms, commentator.p95_ms, commentator.max_ms) == (25.0, 30.0, 30.0)
    assert snap.model_steps == 10 and snap.fallback_steps == 2 and snap.fallback_rate == 0.2
    assert snap.checks == 4 and snap.rejected_checks == 1 and snap.rejection_rate == 0.25
    assert snap.moments_per_min == 5
    now[0] += 45  # the first batch is now 75 s old
    assert h.snapshot().moments_per_min == 2
    now[0] += 60
    assert h.snapshot().moments_per_min == 0
    for i in range(30):
        h.step(f"agent-{i}", 1.0, "ok")
    assert len(h.snapshot().latency) <= 16  # bounded even if asked for more agents


def test_crew_status_reports_latency_fallback_and_rejection_rates():
    now = [1000.0]

    def liar(schema, user):
        if schema is CommentatorOut:
            return CommentatorOut(headline="Pass was 72% better", body="He should have passed.")
        return good_answer(schema, user)

    crew = Crew(TEAMS, llm=FakeLLM(answer=liar), clock=lambda: now[0])
    bundle = better_option_bundle(crew)
    crew.render(bundle, ViewerProfile())
    health = crew.status().health
    agents = {a.agent for a in health.latency}
    assert {"spotter", "analyst", "commentator", "fact_checker", "producer"} <= agents
    assert health.fallback_steps == 1 and health.model_steps == 2  # analyst ok, commentator fell back
    assert health.rejected_checks == 1 and health.checks >= 3
    assert health.moments_per_min == 1
    now[0] += 61
    assert crew.status().health.moments_per_min == 0
    crew.reset()
    assert crew.status().health.checks == 0 and crew.status().health.latency == []


def test_template_mode_reports_zero_fallbacks(moments):  # noqa: F811
    crew = template_crew()
    bundle = better_option_bundle(crew)
    for language in STUDIO_LANGUAGES:
        crew.render(bundle, ViewerProfile(language=language))
    health = crew.status().health
    assert health.fallback_rate == 0.0 and health.rejection_rate == 0.0 and health.checks >= 10


def test_recap_ai_text_claims_are_matched():
    def recap_answer(schema, user):
        if schema is RecapOut:
            facts = user["facts"]
            return RecapOut(
                title="Recap",
                headline=f"{facts['home']} {facts['score_home']}-{facts['score_away']} {facts['away']}",
                summary_paragraphs=[
                    "A tight game.",
                    f"Expected goals {facts['xg_home']} to {facts['xg_away']}.",
                ],
            )
        return good_answer(schema, user)

    events = read_jsonl(match_files()[0])
    crew, stats, _ = _replay(events)
    crew.llm = FakeLLM(answer=recap_answer)
    crew.budget = ModelBudget(total=100, per_minute=100)
    recap = crew.recap(stats.snapshot(), stats.players(), ViewerProfile())
    assert recap.produced_by == "ai", recap.fallback_reason
    para = next(c for c in recap.claims if c.field == "paragraph" and c.numbers)
    assert para.check == "verified_numeric" and set(para.fact_keys) <= {"xg_home", "xg_away", "p_xg"}
    assert "matched to facts" in para.reason


def test_metric_alert_cards_carry_template_claims():
    from matchmind.crew.producer import ViewerState
    from matchmind.schema import EventType
    from matchmind.stats.models import EventMetrics
    from test_crew import ev, players, snap, window

    crew = template_crew()
    state, profile = (
        ViewerState(),
        ViewerProfile(focus_metric="pressure", favourite_team="HCY", language="ja"),
    )
    for seq, t, idx in ((1, 100.0, 20.0), (2, 160.0, 37.0)):
        alerts = crew.metric_alerts(
            ev(seq, EventType.PASS, t),
            EventMetrics(event_id=f"e{seq}"),
            snap(t, away=window(pressure_index=idx)),
            players(),
            profile,
            state,
        )
    (alert,) = alerts
    numeric = [c for c in alert.claims if c.numbers]
    assert numeric and all(c.check == "verified_numeric" and c.origin == "template" for c in numeric)
    assert any("pressure_index" in c.fact_keys for c in numeric)


def test_club_heart_framings_keep_exact_claims_and_parity():
    """A fan of either club gets framed templates ("your team"); their claims still come
    from template placeholders, and every persona and language still agrees."""
    from matchmind.crew import club_heart

    demo = next(p for p in match_files() if "DEMO" in p.name)
    crew, _, bundles = _replay(read_jsonl(demo))
    framed = 0
    for fav in ("NBR", "HCY"):
        fav_name = crew.team_name(fav)
        for b in bundles:
            m = b.moment
            framed += bool(club_heart.frames_for(m, fav_name))
            cards, withheld = [], 0
            for persona in PERSONAS:
                focus = m.player_ids[0] if persona == "player_spotlight" and m.player_ids else None
                for language in STUDIO_LANGUAGES:
                    profile = ViewerProfile(
                        persona=persona, language=language, favourite_team=fav, focus_player_id=focus
                    )
                    card = crew.render(b, profile)
                    if card is None:
                        withheld += 1
                        continue
                    assert all(c.origin == "template" for c in card.claims), card.card_id
                    cards.append(card)
            result = fact_parity(m, cards, withheld)
            assert result.ok, (m.moment_id, fav, result.problems[:3])
    assert framed > 20  # the sweep really covered framed templates


def test_your_team_in_a_framed_template_is_bound_to_the_club():
    claim = text_claims(
        "Your team turn the screw",
        "headline",
        {"team": "Northbridge FC", "home": "Northbridge FC"},
        "en",
        template="Your team turn the screw",
        roster={"Northbridge FC": "NBR"},
        favourite=("your team", "Northbridge FC"),
    )[0]
    assert claim.check == "verified_name" and claim.fact_keys == ["team"]
    assert claim.bindings[0].text == "Your team" and claim.bindings[0].entity_id == "NBR"
