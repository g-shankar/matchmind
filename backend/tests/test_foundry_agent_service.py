"""Foundry Agent Service runtime and registration, against a fake service (no network)."""

from __future__ import annotations

import importlib.util
import inspect
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from matchmind.crew import analyst, commentator, recap
from matchmind.crew.analyst import AnalystOut
from matchmind.crew.breaker import BREAKER_OPEN_S
from matchmind.crew.commentator import CommentatorOut
from matchmind.crew.contracts import ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.llm import AzureOpenAILLM, LLMError, ModelBudget, TemplateLLM, make_llm
from matchmind.crew.recap import RecapOut
from matchmind.foundry import agent_service, cli
from matchmind.foundry.agent_service import (
    DIGEST_KEY,
    AgentRecord,
    AzureAgentService,
    FoundryAgentsLLM,
    agent_specs,
    register,
)
from matchmind.simulator.teams import TEAMS
from test_crew import better_option_bundle, moments, players, snap, trace_of  # noqa: F401

AGENTS_DIR = Path(__file__).resolve().parents[2] / "foundry" / "agents"
SCHEMAS = {"AnalystOut": AnalystOut, "CommentatorOut": CommentatorOut, "RecapOut": RecapOut}


def good_json(name: str, user: dict) -> str:
    facts = user.get("facts", {})
    if name == "pitchpulse-analyst":
        return json.dumps(
            {
                "why": f"The pass was {facts['times_better']}x the better bet.",
                "tactical_tag": "decision_making",
            }
        )
    if name == "pitchpulse-commentator":
        return json.dumps(
            {"headline": "Kerrigan should have squared it", "body": f"Pass value {facts['alt_value']}."}
        )
    return json.dumps(
        {"title": "Recap", "headline": "Northbridge FC lead", "summary_paragraphs": ["One.", "Two."]}
    )


class FakeAgentService:
    """Agent Service in memory: named agents with numbered versions, and runs."""

    def __init__(self, answer=good_json, delay: float = 0.0, error: Exception | None = None):
        self.agents: dict[str, list[AgentRecord]] = {}
        self.bodies: dict[str, list[dict]] = {}
        self.answer = answer
        self.delay = delay
        self.error = error
        self.runs: list[dict] = []
        self.gets = 0
        self._lock = threading.Lock()

    def get_agent(self, name: str) -> AgentRecord | None:
        with self._lock:
            self.gets += 1
            versions = self.agents.get(name)
            return versions[-1] if versions else None

    def create_version(self, name: str, body: dict) -> AgentRecord:
        json.dumps(body)  # the body is plain JSON
        with self._lock:
            versions = self.agents.setdefault(name, [])
            record = AgentRecord(name=name, version=str(len(versions) + 1), metadata=dict(body["metadata"]))
            versions.append(record)
            self.bodies.setdefault(name, []).append(body)
            return record

    def respond(self, name, version, text, timeout_s, max_output_tokens):
        with self._lock:
            self.runs.append(
                {"name": name, "version": version, "input": json.loads(text), "timeout_s": timeout_s}
            )
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.answer(name, json.loads(text))


def foundry_crew(service: FakeAgentService, **kw) -> Crew:
    return Crew(TEAMS, llm=FoundryAgentsLLM(service, model="gpt-4o-mini"), **kw)


# ----------------------------------------------------------------- the specs


def test_three_model_steps_become_three_agents_built_from_the_cards():
    specs = agent_specs("gpt-4o-mini")
    assert [s.name for s in specs] == [
        "pitchpulse-analyst",
        "pitchpulse-commentator",
        "pitchpulse-producer-recap",
    ]
    prompts = [analyst.ANALYST_SYSTEM, commentator.COMMENTATOR_SYSTEM, recap.RECAP_SYSTEM]
    for spec, prompt, schema in zip(specs, prompts, (AnalystOut, CommentatorOut, RecapOut), strict=True):
        d = spec.definition()
        assert d["kind"] == "prompt" and d["model"] == "gpt-4o-mini" and d["instructions"] == prompt.strip()
        fmt = d["text"]["format"]
        assert fmt["type"] == "json_schema" and fmt["name"] == schema.__name__
        assert fmt["schema"] == schema.model_json_schema()
        # The same instructions and schema as the committed agent card.
        card = yaml.safe_load((AGENTS_DIR / spec.card).read_text("utf-8"))
        step = next(s for s in card["model_steps"] if s["agent_service"]["name"] == spec.name)
        assert step["instructions"] == spec.instructions and step["output_schema"] == spec.output_schema
        assert step["agent_service"]["text"]["format"]["name"] == schema.__name__


def test_model_deployment_follows_the_environment(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "crew-model")
    assert {s.model for s in agent_specs()} == {"crew-model"}
    monkeypatch.setenv("MATCHMIND_FOUNDRY_MODEL", "agents-model")
    assert {s.model for s in agent_specs()} == {"agents-model"}


# ---------------------------------------------------------------- the runtime


def test_each_step_is_routed_to_its_own_agent_with_the_crews_payload(moments):  # noqa: F811
    service = FakeAgentService()
    crew = foundry_crew(service)
    bundle = better_option_bundle(crew)
    card = crew.render(bundle, ViewerProfile())
    assert bundle.explanation.produced_by == "ai" and card.produced_by == "ai"
    assert [r["name"] for r in service.runs] == ["pitchpulse-analyst", "pitchpulse-commentator"]
    assert service.runs[0]["input"] == analyst.ai_payload(bundle.moment)
    profile = ViewerProfile()
    assert service.runs[1]["input"] == commentator.ai_payload(
        bundle.moment, bundle.explanation.why, profile.persona, "en", None, None
    )
    assert all(r["version"] == "1" and r["timeout_s"] == crew.timeout_s for r in service.runs)
    full_time = crew.recap(snap(5500.0, period=2), players(), ViewerProfile(), moments)
    assert service.runs[-1]["name"] == "pitchpulse-producer-recap"
    assert full_time.produced_by == "ai"
    status = crew.status()
    assert status.mode == "ai" and status.provider == "foundry_agents" and status.model == "gpt-4o-mini"


def test_agents_are_looked_up_once_and_created_only_when_missing():
    service = FakeAgentService()
    crew = foundry_crew(service)
    bundle = better_option_bundle(crew)
    threads = [
        threading.Thread(target=crew.render, args=(bundle, ViewerProfile(persona=p, language=lang)))
        for p in ("casual", "tactical", "fantasy")
        for lang in ("en", "es", "fr")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert {name: len(v) for name, v in service.agents.items()} == {
        "pitchpulse-analyst": 1,
        "pitchpulse-commentator": 1,
    }
    assert service.gets == 2  # one lookup per agent, however many viewers


def test_an_existing_up_to_date_agent_is_reused_not_recreated():
    service = FakeAgentService()
    register(service, agent_specs("gpt-4o-mini"))
    crew = foundry_crew(service)
    better_option_bundle(crew)
    assert len(service.agents["pitchpulse-analyst"]) == 1 and service.runs[0]["version"] == "1"


def test_timeout_falls_back_to_the_template_with_a_reason():
    crew = foundry_crew(FakeAgentService(delay=0.3), timeout_s=0.05)
    bundle = better_option_bundle(crew)
    assert bundle.explanation.produced_by == "template" and bundle.explanation.fallback_reason == "timeout"
    card = crew.render(bundle, ViewerProfile())
    assert card.produced_by == "template" and card.fallback_reason == "timeout"


def test_breaker_opens_after_three_failures_and_stops_calls():
    now = [1000.0]
    service = FakeAgentService(error=RuntimeError("503 from upstream with request id abc"))
    crew = foundry_crew(service, clock=lambda: now[0])
    bundle = better_option_bundle(crew)
    for persona in ("casual", "tactical", "fantasy"):
        assert crew.render(bundle, ViewerProfile(persona=persona)).fallback_reason == "error"
    assert "commentator" in crew.status().breakers_open
    runs = len(service.runs)
    card = crew.render(bundle, ViewerProfile(persona="player_spotlight"))
    assert card.fallback_reason == "circuit_open" and len(service.runs) == runs
    now[0] += BREAKER_OPEN_S + 1
    service.error = None
    crew.render(bundle, ViewerProfile(language="fr"))
    last = trace_of(crew, bundle.moment.moment_id).steps[-2]
    assert (last.agent, last.status, last.detail) == ("commentator", "ok", "casual/fr: ai")


def test_budget_caps_agent_runs():
    service = FakeAgentService()
    crew = foundry_crew(service, budget=ModelBudget(total=2, per_minute=10_000))
    bundle = better_option_bundle(crew)
    cards = [crew.render(bundle, ViewerProfile(persona=p)) for p in ("casual", "tactical", "fantasy")]
    assert len(service.runs) == 2 and cards[-1].fallback_reason == "budget"


def test_fact_checker_rejects_an_agents_unbacked_number():
    def liar(name, user):
        if name == "pitchpulse-commentator":
            return json.dumps({"headline": "Pass was 72% better", "body": "He should have passed."})
        return good_json(name, user)

    crew = foundry_crew(FakeAgentService(answer=liar))
    bundle = better_option_bundle(crew)
    card = crew.render(bundle, ViewerProfile())
    assert "72" not in card.headline and card.produced_by == "template"
    assert card.fallback_reason.startswith("fact_check:") and crew.status().rejections == 1
    assert any(s.status == "rejected" for s in trace_of(crew, bundle.moment.moment_id).steps)


def test_an_answer_off_the_schema_gets_one_repair_retry():
    answers = iter(["not json", None])

    def flaky(name, user):
        nxt = next(answers, None)
        return nxt if nxt is not None and name == "pitchpulse-analyst" else good_json(name, user)

    service = FakeAgentService(answer=flaky)
    crew = foundry_crew(service)
    assert better_option_bundle(crew).explanation.produced_by == "ai"
    assert len(service.runs) == 2 and "repair" in service.runs[1]["input"]


def test_provider_errors_never_carry_provider_text():
    llm = FoundryAgentsLLM(FakeAgentService(error=RuntimeError("secret detail")), model="m")
    with pytest.raises(LLMError) as err:
        llm.complete_json(analyst.ANALYST_SYSTEM, {"facts": {}}, AnalystOut, 1.0)
    assert str(err.value) == "RuntimeError"


def test_a_prompt_that_differs_from_the_agent_is_refused_and_unknown_schemas_too():
    service = FakeAgentService()
    llm = FoundryAgentsLLM(service, model="m")
    with pytest.raises(LLMError):
        llm.complete_json("Some other prompt", {"facts": {}}, AnalystOut, 1.0)
    with pytest.raises(LLMError):
        llm.complete_json(analyst.ANALYST_SYSTEM, {}, ViewerProfile, 1.0)
    assert service.runs == []


def test_a_deleted_agent_is_looked_up_again_after_a_failure():
    service = FakeAgentService()
    llm = FoundryAgentsLLM(service, model="m")
    payload = {"facts": {"times_better": 2}}
    llm.complete_json(analyst.ANALYST_SYSTEM, payload, AnalystOut, 1.0)
    service.agents.clear()  # deleted in the portal
    service.error = RuntimeError("not found")
    with pytest.raises(LLMError):
        llm.complete_json(analyst.ANALYST_SYSTEM, payload, AnalystOut, 1.0)
    service.error = None
    llm.complete_json(analyst.ANALYST_SYSTEM, payload, AnalystOut, 1.0)
    assert service.gets == 2 and len(service.agents["pitchpulse-analyst"]) == 1


# -------------------------------------------------------------- the switches


def test_provider_switch_is_still_behind_the_paid_ai_switch(monkeypatch):
    monkeypatch.setenv("MATCHMIND_LLM_PROVIDER", "foundry_agents")
    assert isinstance(make_llm(), TemplateLLM)
    assert Crew(TEAMS).status().provider == "templates"
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "true")
    llm = make_llm()
    assert isinstance(llm, FoundryAgentsLLM)  # nothing is called until the first step
    assert Crew(TEAMS, llm=llm).status().provider == "foundry_agents"
    monkeypatch.setenv("MATCHMIND_LLM_PROVIDER", "azure_openai")
    assert isinstance(make_llm(), AzureOpenAILLM)
    monkeypatch.setenv("MATCHMIND_LLM_PROVIDER", "nonsense")
    assert isinstance(make_llm(), AzureOpenAILLM)


def test_live_session_llm_follows_the_provider_switch(monkeypatch):
    from matchmind.api.session import live_llm

    monkeypatch.setenv("MATCHMIND_LLM_PROVIDER", "foundry_agents")
    assert live_llm() is None
    monkeypatch.setenv("MATCHMIND_AI_ENABLED", "true")
    assert isinstance(live_llm(), FoundryAgentsLLM)


# ---------------------------------------------------------------- registration


def test_registration_creates_then_leaves_alone_then_updates_on_a_card_change():
    service = FakeAgentService()
    first = register(service, agent_specs("gpt-4o-mini"))
    assert [(a, r.version) for a, r in first] == [("created", "1")] * 3
    again = register(service, agent_specs("gpt-4o-mini"))
    assert [(a, r.version) for a, r in again] == [("unchanged", "1")] * 3
    assert all(len(v) == 1 for v in service.agents.values())  # no new versions
    changed = register(service, agent_specs("gpt-4.1-mini"))
    assert [(a, r.version) for a, r in changed] == [("updated", "2")] * 3
    body = service.bodies["pitchpulse-analyst"][-1]
    assert body["definition"]["model"] == "gpt-4.1-mini"
    assert body["metadata"][DIGEST_KEY] == agent_specs("gpt-4.1-mini")[0].digest()


def test_dry_run_prints_the_exact_payloads_and_no_secrets(monkeypatch, capsys):
    sentinel = "https://sentinel-account.services.ai.azure.com/api/projects/sentinel"
    monkeypatch.setenv("MATCHMIND_FOUNDRY_PROJECT_ENDPOINT", sentinel)
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "sentinel-secret")
    monkeypatch.setattr(cli, "service_for", lambda endpoint: pytest.fail("dry run must not connect"))
    assert cli.main(["register", "--dry-run", "--model", "gpt-4o-mini"]) == 0
    out = capsys.readouterr().out
    payloads = json.loads(out)
    assert [p["agent_name"] for p in payloads] == [s.name for s in agent_specs("gpt-4o-mini")]
    assert [p["body"] for p in payloads] == [s.body() for s in agent_specs("gpt-4o-mini")]
    lowered = out.lower()
    for forbidden in (
        "sentinel",
        "secret",
        "password",
        "api_key",
        "api-key",
        "bearer",
        "authorization",
        "token",
    ):
        assert forbidden not in lowered, forbidden


def test_register_is_owner_only_and_needs_an_endpoint(monkeypatch, capsys):
    monkeypatch.setattr(cli, "service_for", lambda endpoint: pytest.fail("must not connect"))
    monkeypatch.setenv("CI", "true")
    assert cli.main(["register"]) == 2
    assert "never in CI" in capsys.readouterr().err
    monkeypatch.delenv("CI")
    monkeypatch.delenv("MATCHMIND_FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)
    assert cli.main(["register"]) == 2
    assert cli.main(["register", "--endpoint", "http://plain-http.example"]) == 2


def test_register_command_against_a_fake_project(monkeypatch, capsys):
    monkeypatch.delenv("CI", raising=False)
    service = FakeAgentService()
    seen = []
    monkeypatch.setattr(cli, "service_for", lambda endpoint: seen.append(endpoint) or service)
    endpoint = "https://x.services.ai.azure.com/api/projects/p"
    assert cli.main(["register", "--endpoint", endpoint]) == 0
    assert cli.main(["register", "--endpoint", endpoint]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [ln.split()[0] for ln in lines] == ["created"] * 3 + ["unchanged"] * 3
    assert seen == [endpoint, endpoint]

    service.create_version = lambda name, body: (_ for _ in ()).throw(RuntimeError("raw provider text"))
    service.agents.clear()
    assert cli.main(["register", "--endpoint", endpoint]) == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err and "raw provider text" not in err


def test_trace_demo_needs_consent_and_runs_through_the_agents(monkeypatch, capsys):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    service = FakeAgentService()
    monkeypatch.setattr(cli, "service_for", lambda endpoint: service)
    endpoint = "https://x.services.ai.azure.com/api/projects/p"
    assert cli.main(["trace-demo", "--endpoint", endpoint]) == 2  # no --yes
    assert service.runs == []
    monkeypatch.setenv("CI", "1")
    assert cli.main(["trace-demo", "--yes", "--endpoint", endpoint]) == 2
    monkeypatch.delenv("CI")
    assert cli.main(["trace-demo", "--yes", "--moments", "2", "--endpoint", endpoint]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "provider: foundry_agents" in out[0]
    assert len(out) == 4 and 0 < len(service.runs) <= 8
    assert {r["name"] for r in service.runs} <= {"pitchpulse-analyst", "pitchpulse-commentator"}


# ---------------------------------------------------------- the SDK adapter


class FakeNotFound(Exception):
    pass


def fake_sdk(latest_metadata=None):
    calls: dict[str, list] = {"get": [], "create_version": [], "responses": [], "openai_kwargs": []}

    def get(agent_name):
        calls["get"].append(agent_name)
        if latest_metadata is None:
            raise FakeNotFound()
        latest = SimpleNamespace(version="4", metadata=latest_metadata)
        return SimpleNamespace(versions=SimpleNamespace(latest=latest))

    def create_version(agent_name, body):
        calls["create_version"].append((agent_name, body))
        return SimpleNamespace(version="5", metadata=body["metadata"])

    def create(**kwargs):
        calls["responses"].append(kwargs)
        return SimpleNamespace(status="completed", output_text='{"ok": true}')

    def get_openai_client(**kwargs):
        calls["openai_kwargs"].append(kwargs)
        return SimpleNamespace(responses=SimpleNamespace(create=create))

    project = SimpleNamespace(
        agents=SimpleNamespace(get=get, create_version=create_version), get_openai_client=get_openai_client
    )
    return project, calls


def test_sdk_adapter_maps_to_the_projects_api(monkeypatch):
    monkeypatch.setattr(AzureAgentService, "not_found_error", staticmethod(lambda: FakeNotFound))
    project, calls = fake_sdk()
    service = AzureAgentService("https://x.services.ai.azure.com/api/projects/p", project=project)
    assert service.get_agent("pitchpulse-analyst") is None
    spec = agent_specs("m")[0]
    record = service.create_version(spec.name, spec.body())
    assert record.version == "5" and calls["create_version"] == [(spec.name, spec.body())]
    assert service.respond(spec.name, "5", '{"a": 1}', 3.0, 400) == '{"ok": true}'
    (req,) = calls["responses"]
    assert req["extra_body"] == {
        "agent_reference": {"type": "agent_reference", "name": spec.name, "version": "5"}
    }
    assert req["input"] == '{"a": 1}' and req["timeout"] == 3.0 and req["max_output_tokens"] == 400
    assert "model" not in req  # the agent carries the model and instructions
    assert calls["openai_kwargs"] == [{"max_retries": 0}]

    project, _ = fake_sdk({DIGEST_KEY: "abc"})
    found = AzureAgentService("https://x", project=project).get_agent("pitchpulse-analyst")
    assert found == AgentRecord("pitchpulse-analyst", "4", {DIGEST_KEY: "abc"})


def test_sdk_adapter_treats_an_unfinished_response_as_a_failure():
    project, _ = fake_sdk()
    project.get_openai_client = lambda **kw: SimpleNamespace(
        responses=SimpleNamespace(create=lambda **k: SimpleNamespace(status="incomplete", output_text="{"))
    )
    with pytest.raises(LLMError, match="incomplete"):
        AzureAgentService("https://x", project=project).respond("a", "1", "{}", 1.0, 10)


def test_sdk_adapter_refuses_a_missing_or_plain_http_endpoint():
    with pytest.raises(LLMError):
        AzureAgentService("").project_client()
    with pytest.raises(LLMError):
        AzureAgentService("http://x.example").project_client()


@pytest.mark.skipif(
    importlib.util.find_spec("azure.ai.projects") is None if importlib.util.find_spec("azure") else True,
    reason="needs azure-ai-projects (the foundry extra)",
)
def test_installed_sdk_has_the_calls_the_adapter_makes():
    """Guards the adapter against SDK changes: the methods and parameters it uses exist."""
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.operations import AgentsOperations
    from azure.core.exceptions import ResourceNotFoundError

    assert "agent_name" in inspect.signature(AgentsOperations.get).parameters
    params = inspect.signature(AgentsOperations.create_version).parameters
    assert "agent_name" in params and "body" in params
    assert "agent_name" in inspect.signature(AIProjectClient.get_openai_client).parameters
    assert AzureAgentService.not_found_error() is ResourceNotFoundError
    from openai.resources.responses import Responses

    params = inspect.signature(Responses.create).parameters
    assert {"input", "extra_body", "timeout", "max_output_tokens"} <= set(params)
    from azure.ai.projects.models import PromptAgentDefinition

    definition = PromptAgentDefinition(agent_specs("m")[0].definition())
    assert definition.kind == "prompt" and definition.text.format.type == "json_schema"
    assert definition.as_dict() == agent_specs("m")[0].definition()


def test_module_has_no_sdk_import_at_load_time():
    source = inspect.getsource(agent_service)
    top = source.split("class AzureAgentService")[0]
    assert "import azure" not in top and "from azure" not in top and "openai" not in top.split('"""', 2)[2]
