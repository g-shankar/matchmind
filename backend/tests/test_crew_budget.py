"""Paid model spend: a process-wide budget and rate, and recaps only at full time."""

from __future__ import annotations

from matchmind.crew.contracts import LANGUAGES, PERSONAS, ViewerProfile, is_world_language
from matchmind.crew.crew import Crew
from matchmind.crew.llm import ModelBudget
from matchmind.simulator.teams import TEAMS
from test_crew import FakeLLM, better_option_bundle, good_answer, moments, players, snap  # noqa: F401


def many_profiles(n: int) -> list[ViewerProfile]:
    combos = [
        (persona, language, fav, focus)
        for persona in PERSONAS
        for language in LANGUAGES
        for fav in (None, "NBR", "HCY")
        for focus in (None, *[p.player_id for t in TEAMS.values() for p in t.players])
    ]
    combos = (combos * (n // len(combos) + 1))[:n]
    return [
        ViewerProfile(persona=p, language=lang, favourite_team=fav, focus_player_id=focus)
        for p, lang, fav, focus in combos
    ]


def test_model_budget_caps_total_calls_across_many_viewers():
    llm = FakeLLM(answer=good_answer)
    crew = Crew(TEAMS, llm=llm, budget=ModelBudget(total=25, per_minute=10_000))
    bundle = better_option_bundle(crew)
    cards = [crew.render(bundle, p) for p in many_profiles(1000)]
    assert llm.calls <= 25
    assert cards[-1].produced_by == "template" and cards[-1].fallback_reason == "budget"
    assert crew.status().fallbacks > 0


def test_model_budget_rate_limit_refills_after_a_minute():
    now = [0.0]
    budget = ModelBudget(total=1000, per_minute=5, clock=lambda: now[0])
    assert [budget.take() for _ in range(7)] == [True] * 5 + [False] * 2
    now[0] += 61
    assert budget.take()


def test_model_budget_reads_env(monkeypatch):
    monkeypatch.setenv("MATCHMIND_AI_BUDGET", "7")
    monkeypatch.setenv("MATCHMIND_AI_RATE_PER_MIN", "nonsense")
    budget = ModelBudget()
    assert budget.total == 7 and budget.per_minute == 30


def test_crew_uses_the_process_wide_budget_by_default(monkeypatch):
    from matchmind.crew import llm as llm_mod

    shared = ModelBudget(total=2, per_minute=10_000)
    monkeypatch.setattr(llm_mod, "BUDGET", shared)
    llm = FakeLLM(answer=good_answer)
    for _ in range(3):
        crew = Crew(TEAMS, llm=llm)  # a new crew does not get a new budget
        better_option_bundle(crew)
    assert llm.calls == 2 and shared.used == 2


def test_recap_uses_templates_until_full_time_then_one_model_call_per_audience(moments):  # noqa: F811
    llm = FakeLLM(answer=good_answer)
    crew = Crew(TEAMS, llm=llm, budget=ModelBudget(total=10_000, per_minute=10_000))
    live = [m for m in moments if m.facts.get("phase") != "full_time"]
    profiles = many_profiles(1000)
    for p in profiles:
        assert crew.recap(snap(3000.0, period=2), players(), p, live).produced_by == "template"
    assert llm.calls == 0  # no model recap during live play
    for p in profiles:
        crew.recap(snap(5500.0, period=2), players(), p, moments)
    # World languages reuse the English recap (then translate it): no extra model calls.
    audiences = {
        (p.persona, "en" if is_world_language(p.language) else p.language, p.favourite_team) for p in profiles
    }
    assert llm.calls == len(audiences) <= 60  # cached per persona x language x favourite club


def test_recap_respects_the_budget_at_full_time(moments):  # noqa: F811
    llm = FakeLLM(answer=good_answer)
    crew = Crew(TEAMS, llm=llm, budget=ModelBudget(total=3, per_minute=10_000))
    for p in many_profiles(1000):
        crew.recap(snap(5500.0, period=2), players(), p, moments)
    assert llm.calls == 3
    assert any(s.detail == "budget" for t in crew.traces(500) for s in t.steps)
