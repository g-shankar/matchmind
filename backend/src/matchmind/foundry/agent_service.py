"""Microsoft Foundry Agent Service runtime for the crew's model steps.

With `MATCHMIND_AI_ENABLED=true` and `MATCHMIND_LLM_PROVIDER=foundry_agents`,
each model step runs as a persistent Foundry agent, one per role:

    Analyst      -> pitchpulse-analyst
    Commentator  -> pitchpulse-commentator
    Recap        -> pitchpulse-producer-recap

Each agent is a prompt agent built from its agent card (`foundry/agents/*.yaml`,
generated from the crew code by `matchmind-foundry export`): the card's
instructions, the model deployment, temperature, and the step's output schema
as a JSON-schema response format. Agents are looked up by name and created, or
given a new version, only when the card changed (a digest of the definition is
kept in the agent's metadata), so registration is idempotent. The crew still
owns everything around the call: the 3 s timeout, the repair retry, the
circuit breakers, the model budget and the fact-checker gate on every answer.

Spotter, Fact-checker and the Producer's card placement stay deterministic code
in the app: numbers come from the stats engine, never from a model, so those
agents are not Foundry agents.

Sign-in is Microsoft Entra ID only (`DefaultAzureCredential`: the app's managed
identity in Azure, `az login` on a laptop). The project endpoint comes from
MATCHMIND_FOUNDRY_PROJECT_ENDPOINT, or AZURE_AI_PROJECT_ENDPOINT (set by the
Bicep template). The SDKs (`azure-ai-projects`, the `foundry` extra) are
imported on first use, and the client is behind a small interface
(`AgentServiceClient`), so every test runs offline against a fake.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from pydantic import BaseModel

from matchmind.crew import llm as llm_mod
from matchmind.crew.llm import LLMError, parse_json

DIGEST_KEY = "pitchpulse_digest"
CARD_KEY = "pitchpulse_card"
RESPONSE_STATUSES = ("completed", "incomplete", "failed", "cancelled", "in_progress", "queued")


def project_endpoint() -> str:
    return (
        os.environ.get("MATCHMIND_FOUNDRY_PROJECT_ENDPOINT", "").strip()
        or os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "").strip()
    )


def model_deployment() -> str:
    return (
        os.environ.get("MATCHMIND_FOUNDRY_MODEL", "").strip()
        or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
        or llm_mod.DEFAULT_DEPLOYMENT
    )


# --------------------------------------------------------------- agent specs


@dataclass(frozen=True)
class AgentSpec:
    """One Foundry prompt agent, read from an agent card's model step."""

    name: str
    step: str
    card: str
    description: str
    instructions: str
    schema_name: str
    output_schema: dict[str, Any]
    model: str
    temperature: float

    def definition(self) -> dict[str, Any]:
        """The prompt agent definition, exactly as sent to Agent Service."""
        definition: dict[str, Any] = {
            "kind": "prompt",
            "model": self.model,
            "instructions": self.instructions,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": self.schema_name,
                    "schema": self.output_schema,
                    # The schema has length limits strict mode does not take; every
                    # answer is validated against it (and fact-checked) by the crew.
                    "strict": False,
                }
            },
        }
        # Reasoning models (gpt-5 family, o-series) reject a temperature.
        if llm_mod.is_reasoning_model(self.model):
            definition["reasoning"] = {"effort": llm_mod.reasoning_effort(self.model)}
        else:
            definition["temperature"] = self.temperature
        return definition

    def digest(self) -> str:
        payload = {"definition": self.definition(), "description": self.description}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:32]

    def body(self) -> dict[str, Any]:
        """The create-version request body: definition, description, metadata."""
        return {
            "definition": self.definition(),
            "description": self.description,
            "metadata": {CARD_KEY: f"foundry/agents/{self.card}", DIGEST_KEY: self.digest()},
        }


@lru_cache(maxsize=4)
def _card_steps() -> tuple[tuple[str, str, dict[str, Any]], ...]:
    from matchmind.foundry import manifests

    out = []
    for manifest in manifests.manifests():
        card = manifest["name"].removeprefix("pitchpulse-") + ".yaml"
        for step in manifest["model_steps"]:
            out.append((card, manifest["role"], step))
    return tuple(out)


def agent_specs(model: str | None = None) -> list[AgentSpec]:
    """The model-backed agents, in pipeline order, from the agent cards."""
    model = model or model_deployment()
    specs = []
    for card, role, step in _card_steps():
        service = step["agent_service"]
        specs.append(
            AgentSpec(
                name=service["name"],
                step=step["step"],
                card=card,
                description=role if step["step"] != "recap" else "Writes the match recap at full time.",
                instructions=step["instructions"],
                schema_name=service["text"]["format"]["name"],
                output_schema=step["output_schema"],
                model=model,
                temperature=step["temperature"],
            )
        )
    return specs


# ---------------------------------------------------------- service client


@dataclass(frozen=True)
class AgentRecord:
    name: str
    version: str
    metadata: dict[str, str] = field(default_factory=dict)
    # The version's model and instructions as the service reports them (None if not read).
    model: str | None = None
    instructions: str | None = None


class AgentServiceClient(Protocol):
    """The three Agent Service calls PitchPulse makes."""

    def get_agent(self, name: str) -> AgentRecord | None:
        """The agent's latest version, or None if there is no agent by that name."""

    def create_version(self, name: str, body: dict[str, Any]) -> AgentRecord: ...

    def respond(
        self, name: str, version: str, text: str, timeout_s: float, max_output_tokens: int
    ) -> str | None:
        """Run the agent on one input; the answer text."""


def ensure_agent(client: AgentServiceClient, spec: AgentSpec) -> tuple[str, AgentRecord]:
    """Create the agent, give it a new version if its card changed, or leave it.
    Returns ("created" | "updated" | "unchanged", the version to call)."""
    existing = client.get_agent(spec.name)
    if existing is not None and _matches(existing, spec):
        return "unchanged", existing
    record = client.create_version(spec.name, spec.body())
    return ("created" if existing is None else "updated"), record


def _matches(record: AgentRecord, spec: AgentSpec) -> bool:
    """Our digest, and (when the service reports them) the same model and
    instructions: a version edited by hand in the portal is replaced, even if
    it kept our metadata."""
    if record.metadata.get(DIGEST_KEY) != spec.digest():
        return False
    if record.model is not None and record.model != spec.model:
        return False
    return record.instructions is None or record.instructions == spec.instructions


def register(
    client: AgentServiceClient, specs: list[AgentSpec] | None = None
) -> list[tuple[str, AgentRecord]]:
    return [ensure_agent(client, spec) for spec in specs or agent_specs()]


class AzureAgentService:
    """`AgentServiceClient` on the `azure-ai-projects` SDK (Foundry projects API):
    `AIProjectClient.agents.get / create_version`, and the project's OpenAI
    Responses client with an `agent_reference` to run an agent version."""

    def __init__(
        self, endpoint: str | None = None, credential: Any | None = None, project: Any | None = None
    ):
        self.endpoint = endpoint if endpoint is not None else project_endpoint()
        self._credential = credential
        self._project = project
        self._openai: Any | None = None
        self._lock = threading.Lock()

    def project_client(self) -> Any:
        """The `AIProjectClient`, built on first use."""
        with self._lock:
            if self._project is None:
                if not self.endpoint.startswith("https://"):
                    raise LLMError(
                        "the Foundry project endpoint is not set (MATCHMIND_FOUNDRY_PROJECT_ENDPOINT)"
                    )
                from azure.ai.projects import AIProjectClient
                from azure.identity import DefaultAzureCredential

                self._project = AIProjectClient(
                    endpoint=self.endpoint, credential=self._credential or DefaultAzureCredential()
                )
            return self._project

    def _openai_client(self) -> Any:
        project = self.project_client()
        with self._lock:
            if self._openai is None:
                # No hidden retries: the crew's own timeout, retry and breaker apply.
                self._openai = project.get_openai_client(max_retries=0)
            return self._openai

    @staticmethod
    def not_found_error() -> type[Exception]:
        from azure.core.exceptions import ResourceNotFoundError

        return ResourceNotFoundError

    def get_agent(self, name: str) -> AgentRecord | None:
        not_found = self.not_found_error()
        try:
            details = self.project_client().agents.get(agent_name=name)
        except not_found:
            return None
        return _record(name, details.versions.latest)

    def create_version(self, name: str, body: dict[str, Any]) -> AgentRecord:
        return _record(name, self.project_client().agents.create_version(agent_name=name, body=body))

    def respond(
        self, name: str, version: str, text: str, timeout_s: float, max_output_tokens: int
    ) -> str | None:
        response = self._openai_client().responses.create(
            input=text,
            extra_body={"agent_reference": {"type": "agent_reference", "name": name, "version": version}},
            max_output_tokens=max_output_tokens,
            timeout=timeout_s,
        )
        status = getattr(response, "status", None) or "completed"
        if status != "completed":
            raise LLMError(status if status in RESPONSE_STATUSES else "not_completed")
        return response.output_text


def _record(name: str, version: Any) -> AgentRecord:
    definition = getattr(version, "definition", None)
    return AgentRecord(
        name=name,
        version=str(version.version),
        metadata=dict(getattr(version, "metadata", None) or {}),
        model=getattr(definition, "model", None),
        instructions=getattr(definition, "instructions", None),
    )


# --------------------------------------------------------------- the client


class FoundryAgentsLLM:
    """The crew's `LLM` with each model step run by its Foundry agent.

    The agent is picked by the step's output schema (AnalystOut, CommentatorOut,
    RecapOut), and the crew's system prompt must equal the agent's registered
    instructions, so a stale agent can never answer for a newer prompt.
    Provider failures surface as `LLMError` with the exception's class name
    only (never provider text); the crew turns them into template fallbacks."""

    enabled = True
    provider = "foundry_agents"

    def __init__(
        self,
        client: AgentServiceClient | None = None,
        *,
        endpoint: str | None = None,
        model: str | None = None,
    ) -> None:
        self.model = model or model_deployment()
        self._client = client if client is not None else AzureAgentService(endpoint)
        self._specs = {spec.schema_name: spec for spec in agent_specs(self.model)}
        self._versions: dict[str, str] = {}
        self._locks = {spec.name: threading.Lock() for spec in self._specs.values()}

    def agent_for(self, schema: type[BaseModel]) -> AgentSpec:
        spec = self._specs.get(schema.__name__)
        if spec is None:
            raise LLMError(f"no Foundry agent answers with {schema.__name__}")
        return spec

    def _version(self, spec: AgentSpec) -> str:
        version = self._versions.get(spec.name)
        if version is not None:
            return version
        with self._locks[spec.name]:
            version = self._versions.get(spec.name)
            if version is None:
                _, record = ensure_agent(self._client, spec)
                version = self._versions[spec.name] = record.version
            return version

    def complete_json(
        self, system: str, user: dict[str, Any], schema: type[BaseModel], timeout_s: float
    ) -> BaseModel:
        spec = self.agent_for(schema)
        if system.strip() != spec.instructions:
            raise LLMError("the agent's instructions differ from the crew's prompt")
        try:
            version = self._version(spec)
            raw = self._client.respond(
                spec.name,
                version,
                json.dumps(user, ensure_ascii=False),
                timeout_s,
                llm_mod.max_output_tokens(spec.model),
            )
        except Exception as exc:  # network, auth, throttling, a deleted agent: never leak provider text
            self._versions.pop(spec.name, None)  # look the agent up again next time
            if isinstance(exc, LLMError):
                raise
            raise LLMError(type(exc).__name__) from exc
        return parse_json(raw, schema)
