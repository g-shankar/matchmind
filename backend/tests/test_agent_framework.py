"""The crew chained by Microsoft Agent Framework workflows (MATCHMIND_ORCHESTRATOR).

The parity tests replay the whole demo match through both orchestrators and
require identical bundles, cards and traces (timings aside).
"""

from __future__ import annotations

import importlib.util
import sys
import threading

import pytest

from matchmind.crew.commentator import CommentatorOut
from matchmind.crew.contracts import LANGUAGES, PERSONAS, ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.llm import LLMError, ModelBudget, TemplateLLM
from matchmind.crew.producer import ViewerState
from matchmind.crew.translator import OffTranslator
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import TEAMS
from matchmind.stats.state import StatsEngine
from test_crew import DEMO, FakeLLM, better_option_bundle, good_answer, trace_of

HAS_AF = importlib.util.find_spec("agent_framework") is not None
needs_af = pytest.mark.skipif(not HAS_AF, reason="needs agent-framework-core (the agent-framework extra)")


def replay(crew: Crew, profiles: list[ViewerProfile]):
    """Every demo event through the crew, every moment voiced for every profile."""
    events = list(read_jsonl(DEMO))
    engine = StatsEngine(events[0].match_id, "NBR", "HCY")
    bundles, cards = [], []
    for e in events:
        metrics = engine.process(e)
        new = crew.process(e, metrics, engine.snapshot(), engine.players())
        bundles += new
        for b in new:
            for p in profiles:
                card = crew.render(b, p)
                cards.append(None if card is None else card.model_dump(mode="json"))
    again = crew.process(events[-1], engine.process(events[-1]), engine.snapshot(), engine.players())
    return bundles, cards, again


def trace_dump(crew: Crew) -> list[dict]:
    out = []
    for t in crew.traces(1000):
        d = t.model_dump(mode="json")
        for step in d["steps"]:
            step.pop("ms")
        out.append(d)
    return out


def status_dump(crew: Crew) -> dict:
    d = crew.status().model_dump(mode="json")
    d.pop("orchestrator")
    # Latency is wall-clock time and differs run to run; sample counts must still match.
    for row in d["health"]["latency"]:
        for k in ("p50_ms", "p95_ms", "max_ms"):
            row.pop(k)
    return d


PROFILES = [
    ViewerProfile(persona=persona, language=language, favourite_team=fav)
    for persona, language, fav in [
        *[(p, "en", None) for p in PERSONAS],
        *[(p, lang, "HCY") for p in ("casual", "tactical") for lang in LANGUAGES[:6]],
    ]
]


def pair(llm_factory=TemplateLLM) -> tuple[Crew, Crew]:
    def crew(orchestrator: str) -> Crew:
        return Crew(
            TEAMS,
            llm=llm_factory(),
            budget=ModelBudget(total=1_000_000, per_minute=1_000_000),
            translator=OffTranslator(),
            orchestrator=orchestrator,
        )

    return crew("in_process"), crew("agent_framework")


@needs_af
def test_template_cards_are_identical_under_agent_framework():
    in_process, framework = pair()
    assert in_process.orchestrator == "in_process" and framework.orchestrator == "agent_framework"
    a, b = replay(in_process, PROFILES), replay(framework, PROFILES)
    bundles_a, cards_a, again_a = a
    bundles_b, cards_b, again_b = b
    assert len(bundles_a) > 20 and any(c is not None for c in cards_a)
    assert [x.model_dump(mode="json") for x in bundles_a] == [x.model_dump(mode="json") for x in bundles_b]
    assert cards_a == cards_b  # byte-identical cards, one per moment x profile
    # Claims are made on the Agent Framework path too (and so compared above).
    assert all(c["claims"] for c in cards_b if c is not None)
    assert [x.model_dump(mode="json") for x in again_a] == [x.model_dump(mode="json") for x in again_b]
    assert trace_dump(in_process) == trace_dump(framework)
    assert status_dump(in_process) == status_dump(framework)


def scripted_llm() -> FakeLLM:
    """A deterministic model: good answers, but every third commentator answer
    carries an unbacked number (the fact-checker must reject it) and every
    seventh call fails."""
    state = {"n": 0}

    def answer(schema, user):
        state["n"] += 1
        if state["n"] % 7 == 0:
            raise LLMError("down")
        if schema is CommentatorOut and state["n"] % 3 == 0:
            return CommentatorOut(headline="Pass was 72% better", body="He should have passed.")
        if "times_better" in user["facts"] or "alt_value" in user["facts"]:
            return good_answer(schema, user)
        if schema is CommentatorOut:
            return CommentatorOut(headline="Big moment", body="The crowd is up.")
        return good_answer(schema, {"facts": {"times_better": 0, "alt_value": 0}})

    class Scripted(FakeLLM):
        def complete_json(self, system, user, schema, timeout_s):
            self.calls += 1
            return answer(schema, user)

    return Scripted()


@needs_af
def test_model_mode_with_rejections_and_failures_is_identical_under_agent_framework():
    # Each crew gets its own scripted model, so both see the same answer sequence.
    in_process, framework = pair(scripted_llm)
    profiles = PROFILES[:4]
    a, b = replay(in_process, profiles), replay(framework, profiles)
    assert a[1] == b[1]
    assert [x.model_dump(mode="json") for x in a[0]] == [x.model_dump(mode="json") for x in b[0]]
    assert trace_dump(in_process) == trace_dump(framework)
    sa = status_dump(in_process)
    assert sa == status_dump(framework)
    assert sa["rejections"] > 0 and sa["fallbacks"] > 0  # the gate and the fallbacks really ran
    assert any(c and c["produced_by"] == "ai" for c in a[1])


@needs_af
def test_fact_checker_gate_holds_inside_the_workflow():
    def liar(schema, user):
        if schema is CommentatorOut:
            return CommentatorOut(headline="Pass was 72% better", body="He should have passed.")
        return good_answer(schema, user)

    crew = Crew(TEAMS, llm=FakeLLM(answer=liar), orchestrator="agent_framework")
    bundle = better_option_bundle(crew)
    assert bundle.explanation.produced_by == "ai"
    card = crew.render(bundle, ViewerProfile())
    assert "72" not in card.headline and card.produced_by == "template"
    assert card.fallback_reason.startswith("fact_check:")
    agents = [s.agent for s in trace_of(crew, bundle.moment.moment_id).steps]
    assert agents == ["spotter", "fact_checker", "analyst", "fact_checker", "commentator", "producer"]


@needs_af
def test_timeout_falls_back_inside_the_workflow():
    crew = Crew(
        TEAMS, llm=FakeLLM(answer=good_answer, delay=0.3), timeout_s=0.05, orchestrator="agent_framework"
    )
    bundle = better_option_bundle(crew)
    assert bundle.explanation.fallback_reason == "timeout"
    assert crew.render(bundle, ViewerProfile()).fallback_reason == "timeout"


@needs_af
def test_workflows_are_agent_framework_workflows_with_one_executor_per_agent():
    from agent_framework import Executor, Workflow

    from matchmind.crew.workflow import build_process_workflow, build_render_workflow

    crew = Crew(TEAMS, llm=TemplateLLM(), orchestrator="agent_framework")
    process, render = build_process_workflow(crew), build_render_workflow(crew)
    assert isinstance(process, Workflow) and isinstance(render, Workflow)
    assert set(process.executors) == {"spotter", "analyst", "fact_checker"}
    assert set(render.executors) == {"commentator", "fact_checker", "producer"}
    assert all(isinstance(e, Executor) for e in [*process.executors.values(), *render.executors.values()])


@needs_af
def test_concurrent_renders_each_get_their_own_workflow_run():
    crew = Crew(TEAMS, llm=TemplateLLM(), orchestrator="agent_framework")
    bundle = better_option_bundle(crew)
    profiles = [ViewerProfile(persona=p, language=lang) for p in PERSONAS for lang in ("en", "es", "fr")]
    results: dict[int, object] = {}
    errors: list[BaseException] = []

    def go(i: int, profile: ViewerProfile) -> None:
        try:
            results[i] = crew.render(bundle, profile)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go, args=(i, p)) for i, p in enumerate(profiles)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    expected = Crew(TEAMS, llm=TemplateLLM(), orchestrator="in_process")
    ref = better_option_bundle(expected)
    for i, p in enumerate(profiles):
        assert results[i].model_dump() == expected.render(ref, p).model_dump()


@needs_af
def test_cards_for_and_reset_work_under_agent_framework():
    crew = Crew(TEAMS, llm=TemplateLLM(), orchestrator="agent_framework")
    bundle = better_option_bundle(crew)
    assert crew.cards_for([bundle], ViewerProfile(), ViewerState())
    crew.reset()
    assert crew.moments() == [] and better_option_bundle(crew).moment == bundle.moment


@needs_af
def test_environment_selects_agent_framework(monkeypatch):
    monkeypatch.setenv("MATCHMIND_ORCHESTRATOR", "agent_framework")
    crew = Crew(TEAMS, llm=TemplateLLM())
    assert crew.orchestrator == "agent_framework" and crew.status().orchestrator == "agent_framework"


def test_unknown_orchestrator_setting_stays_in_process(monkeypatch):
    monkeypatch.setenv("MATCHMIND_ORCHESTRATOR", "something-else")
    assert Crew(TEAMS, llm=TemplateLLM()).orchestrator == "in_process"
    with pytest.raises(ValueError):
        Crew(TEAMS, llm=TemplateLLM(), orchestrator="something-else")


def test_missing_package_falls_back_from_the_environment_but_not_from_code(monkeypatch):
    monkeypatch.setitem(sys.modules, "matchmind.crew.workflow", None)  # import now fails
    monkeypatch.setenv("MATCHMIND_ORCHESTRATOR", "agent_framework")
    crew = Crew(TEAMS, llm=TemplateLLM())
    assert crew.orchestrator == "in_process" and crew.status().orchestrator == "in_process"
    with pytest.raises(ImportError):
        Crew(TEAMS, llm=TemplateLLM(), orchestrator="agent_framework")


def test_default_is_in_process():
    crew = Crew(TEAMS, llm=TemplateLLM())
    status = crew.status()
    assert status.orchestrator == "in_process" and status.provider == "templates"
