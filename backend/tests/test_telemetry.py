"""Crew tracing: OpenTelemetry spans per agent step, GenAI conventions, no
message text or viewer data, and a no-op whenever it is not configured."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import BaseModel

from matchmind.crew import telemetry
from matchmind.crew.analyst import AnalystOut
from matchmind.crew.commentator import CommentatorOut
from matchmind.crew.contracts import ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.llm import LLMError, TemplateLLM
from matchmind.simulator.publisher import read_jsonl
from matchmind.simulator.teams import TEAMS
from matchmind.stats.state import StatsEngine

DEMO = Path(__file__).resolve().parents[1] / "data" / "matches" / "MM-DEMO-001.jsonl"
GEN_AI_KEYS = {"gen_ai.operation.name", "gen_ai.agent.name", "gen_ai.agent.id"}
ALLOWED_KEYS = GEN_AI_KEYS | {
    "gen_ai.system",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "error.type",
    "pitchpulse.step.status",
    "pitchpulse.moment.id",
    "pitchpulse.moment.kind",
    "pitchpulse.crew.mode",
    "pitchpulse.produced_by",
    "pitchpulse.fallback_reason",
    "pitchpulse.fact_check.verdict",
}


@pytest.fixture
def spans():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry.set_tracer(provider.get_tracer("test"))
    yield exporter
    telemetry.reset()


@pytest.fixture(autouse=True)
def _no_env_tracing(monkeypatch):
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("APPLICATIONINSIGHTS_AUTHENTICATION_STRING", raising=False)
    telemetry.reset()
    yield
    telemetry.reset()


class ScriptedLLM:
    """Answers each agent with a fixed object; never a network call."""

    enabled = True
    model = "gpt-4o-mini"

    def __init__(self, answers: dict[type, BaseModel | Exception]) -> None:
        self.answers = answers

    def complete_json(self, system, user, schema, timeout_s):
        answer = self.answers.get(schema, LLMError("no answer"))
        if isinstance(answer, Exception):
            raise answer
        return answer


def _run(crew: Crew, limit: int = 400):
    events = read_jsonl(DEMO)[:limit]
    stats = StatsEngine(events[0].match_id, "NBR", "HCY")
    bundles = []
    for e in events:
        bundles += crew.process(e, stats.process(e), stats.snapshot(), stats.players())
    return bundles


def _attrs(exporter) -> list[dict]:
    return [dict(s.attributes) for s in exporter.get_finished_spans()]


def test_off_without_connection_string_and_never_raises():
    assert telemetry.tracer() is None
    telemetry.record_step(
        agent="analyst", status="ok", ms=1.0, moment_id="m", moment_kind="goal", detail="ai", model=None
    )


def test_off_when_extra_is_not_installed(monkeypatch):
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000")
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", None)  # import fails
    assert telemetry.tracer() is None


def test_env_setup_uses_entra_id_and_collects_crew_spans_only(monkeypatch):
    calls: dict = {}
    fake_monitor = types.ModuleType("azure.monitor.opentelemetry")
    fake_monitor.configure_azure_monitor = lambda **kw: calls.update(kw)
    fake_identity = types.ModuleType("azure.identity")

    class FakeCredential:
        def __init__(self, managed_identity_client_id=None):
            self.client_id = managed_identity_client_id

    fake_identity.DefaultAzureCredential = FakeCredential
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", fake_monitor)
    monkeypatch.setitem(sys.modules, "azure.identity", fake_identity)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000")
    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_AUTHENTICATION_STRING",
        "Authorization=AAD;ClientId=11111111-2222-3333-4444-555555555555",
    )
    assert telemetry.tracer() is not None
    assert calls["credential"].client_id == "11111111-2222-3333-4444-555555555555"
    assert calls["disable_logging"] and calls["disable_metrics"] and not calls["enable_live_metrics"]
    assert all(not opt["enabled"] for opt in calls["instrumentation_options"].values())
    assert "fastapi" in calls["instrumentation_options"]


def test_failed_setup_leaves_tracing_off(monkeypatch):
    fake_monitor = types.ModuleType("azure.monitor.opentelemetry")

    def boom(**kw):
        raise ValueError("provider says: secret detail")

    fake_monitor.configure_azure_monitor = boom
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", fake_monitor)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=00000000-0000")
    assert telemetry.tracer() is None


def test_template_crew_emits_one_invoke_agent_span_per_step(spans):
    crew = Crew(TEAMS, llm=TemplateLLM())
    bundles = _run(crew)
    assert bundles
    for b in bundles[:3]:
        crew.render(b, ViewerProfile(persona="tactical", language="es"))
    steps = sum(len(t.steps) for t in crew.traces(limit=500))
    finished = spans.get_finished_spans()
    assert len(finished) == steps
    attrs = _attrs(spans)
    assert {a["gen_ai.agent.name"] for a in attrs} >= {"Spotter", "Analyst", "Commentator", "Producer"}
    for s, a in zip(finished, attrs, strict=True):
        assert s.name == f"invoke_agent {a['gen_ai.agent.name']}"
        assert GEN_AI_KEYS <= a.keys() <= ALLOWED_KEYS
        assert a["gen_ai.operation.name"] == "invoke_agent"
        assert a["pitchpulse.crew.mode"] == "template"
        assert "gen_ai.request.model" not in a  # no model in template mode
        assert s.end_time >= s.start_time


def test_ai_spans_carry_model_verdict_and_fallback_reason_but_no_text(spans):
    invented = AnalystOut(why="A 97 percent chance, the best of the season.", tactical_tag="finishing")
    llm = ScriptedLLM(
        {
            AnalystOut: invented,  # 97 is not a fact: the fact-checker rejects it
            CommentatorOut: CommentatorOut(headline="What a moment", body="The crowd is up."),
        }
    )
    crew = Crew(TEAMS, llm=llm)
    bundles = _run(crew, limit=300)
    profile = ViewerProfile(persona="player_spotlight", language="fr", favourite_team="HCY")
    profile.focus_player_id = bundles[0].moment.player_ids[0] if bundles[0].moment.player_ids else None
    cards = [crew.render(b, profile) for b in bundles[:5]]
    attrs = _attrs(spans)

    analyst = [a for a in attrs if a["gen_ai.agent.name"] == "Analyst"]
    assert analyst and all(a["gen_ai.request.model"] == "gpt-4o-mini" for a in analyst)
    assert all(a["gen_ai.system"] == "az.ai.openai" for a in analyst)
    assert any(a.get("pitchpulse.fallback_reason") == "fact_check" for a in analyst)
    verdicts = {a["pitchpulse.fact_check.verdict"] for a in attrs if a["gen_ai.agent.name"] == "Fact-checker"}
    assert verdicts == {"pass", "rejected"}
    assert any(
        a.get("pitchpulse.produced_by") == "ai" for a in attrs if a["gen_ai.agent.name"] == "Commentator"
    )

    # Never text, never the viewer: no prompt, answer, card text, persona,
    # language, club or focus player in any attribute value.
    forbidden = {"97", "What a moment", "The crowd is up.", "player_spotlight", "fr", "HCY", "Harbour City"}
    forbidden |= {c.headline for c in cards if c} | {c.body for c in cards if c}
    if profile.focus_player_id:
        forbidden.add(profile.focus_player_id)
    for a in attrs:
        assert a.keys() <= ALLOWED_KEYS
        for value in a.values():
            text = str(value)
            assert not any(f == text or (len(f) > 3 and f in text) for f in forbidden), (value, a)


def test_recap_spans_never_carry_persona_or_language(spans):
    crew = Crew(TEAMS, llm=TemplateLLM())
    events = read_jsonl(DEMO)[:300]
    stats = StatsEngine(events[0].match_id, "NBR", "HCY")
    for e in events:
        crew.process(e, stats.process(e), stats.snapshot(), stats.players())
    for profile in (
        ViewerProfile(persona="player_spotlight", language="fr", favourite_team="HCY"),
        ViewerProfile(persona="tactical", language="ja"),
        ViewerProfile(persona="fantasy", language="pt"),  # world language: English recap, translator off
    ):
        crew.recap(stats.snapshot(), stats.players(), profile)
    recaps = [a for a in _attrs(spans) if a["gen_ai.agent.id"] == "pitchpulse-recap"]
    assert len(recaps) >= 3
    forbidden = {"player_spotlight", "tactical", "fantasy", "fr", "ja", "pt", "HCY", "Harbour City"}
    for a in recaps:
        for value in a.values():
            text = str(value)
            parts = text.split("-")
            assert not any(f == text or f in parts or (len(f) > 3 and f in text) for f in forbidden), a


def test_error_steps_are_marked_as_span_errors(spans):
    telemetry.record_step(
        agent="commentator",
        status="error",
        ms=0.0,
        moment_id="m1",
        moment_kind="goal",
        detail="casual/en: no template fits (team)",
        model=None,
    )
    (span,) = spans.get_finished_spans()
    assert span.status.status_code == StatusCode.ERROR


def test_a_broken_tracer_never_stops_the_crew():
    class Broken:
        def start_span(self, *a, **kw):
            raise RuntimeError("exporter down")

    telemetry.set_tracer(Broken())
    try:
        crew = Crew(TEAMS, llm=TemplateLLM())
        assert _run(crew, limit=200)
    finally:
        telemetry.reset()


@pytest.mark.parametrize(
    ("status", "detail", "reason"),
    [
        ("fallback", "timeout", "timeout"),
        ("fallback", "casual/en: budget", "budget"),
        ("fallback", "fact_check: number 97 is not in the facts", "fact_check"),
        ("fallback", "tactical/es: fact_check: body: number word error is not in the facts", "fact_check"),
        ("fallback", "something new", "other"),
        ("ok", "timeout", None),
    ],
)
def test_fallback_reason_is_always_from_the_fixed_list(status, detail, reason):
    assert telemetry.fallback_reason(status, detail) == reason
