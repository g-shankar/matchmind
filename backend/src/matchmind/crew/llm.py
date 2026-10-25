"""Language-model clients for the studio crew.

- `TemplateLLM` (default): free, offline, never produces text. Callers see
  `enabled == False` and use the localised templates.
- `AzureOpenAILLM`: Azure OpenAI through Microsoft Entra ID (no API key),
  JSON response format, validated against a fixed pydantic schema.
- `FoundryAgentsLLM` (`matchmind.foundry.agent_service`): each model step
  runs as a Microsoft Foundry Agent Service agent, one per role.

Paid AI stays off unless `MATCHMIND_AI_ENABLED=true` (owner approval);
`MATCHMIND_LLM_PROVIDER` (azure_openai, the default, or foundry_agents) picks
the client once it is on. The SDKs are imported lazily, so the engine works
without the optional `ai` and `foundry` extras.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError

DEFAULT_API_VERSION = "2024-10-21"
DEFAULT_DEPLOYMENT = "gpt-4o-mini"
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
TEMPERATURE = 0.3
MAX_TOKENS = 400
# Reasoning models (gpt-5 family, o-series) reject `temperature` and `max_tokens`;
# they take `max_completion_tokens`, which also covers their hidden reasoning
# tokens, and `reasoning_effort` (API version 2025-04-01-preview or later).
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
REASONING_MAX_COMPLETION_TOKENS = 2000
REASONING_TIMEOUT_S = 8.0
# "minimal" exists only for the first gpt-5 models; every reasoning model takes "low".
MINIMAL_EFFORT_MODELS = ("gpt-5", "gpt-5-mini", "gpt-5-nano")
REASONING_MIN_API_VERSION = "2025-04-01-preview"
PROVIDERS = ("azure_openai", "foundry_agents")

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The model call failed (network, auth, refusal...)."""


class LLMSchemaError(LLMError):
    """The model answered, but not with JSON matching the schema."""


@runtime_checkable
class LLM(Protocol):
    enabled: bool
    model: str | None
    # Optional: "azure_openai" or "foundry_agents" (see `provider_of`).

    def complete_json(
        self, system: str, user: dict[str, Any], schema: type[BaseModel], timeout_s: float
    ) -> BaseModel: ...


class TemplateLLM:
    """Never called for text: callers check `enabled` and use templates."""

    enabled = False
    model: str | None = None
    provider = "templates"

    def complete_json(
        self, system: str, user: dict[str, Any], schema: type[BaseModel], timeout_s: float
    ) -> BaseModel:
        raise LLMError("template mode: no language model is configured")


def parse_json(raw: str | None, schema: type[BaseModel]) -> BaseModel:
    if not raw:
        raise LLMSchemaError("empty answer")
    try:
        return schema.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMSchemaError(f"answer does not match {schema.__name__}") from exc


def is_reasoning_model(deployment: str | None) -> bool:
    """True for deployments named after a reasoning model (gpt-5*, o1/o3/o4*)."""
    name = (deployment or "").strip().lower()
    return name.startswith(REASONING_PREFIXES) and not name.startswith("gpt-5-chat")


def reasoning_effort(deployment: str | None) -> str:
    name = (deployment or "").strip().lower()
    return "minimal" if name in MINIMAL_EFFORT_MODELS else "low"


def completion_params(deployment: str | None) -> dict[str, Any]:
    """The sampling and length parameters this deployment accepts."""
    if is_reasoning_model(deployment):
        return {
            "max_completion_tokens": max_output_tokens(deployment),
            "reasoning_effort": reasoning_effort(deployment),
        }
    return {"temperature": TEMPERATURE, "max_tokens": MAX_TOKENS}


def max_output_tokens(deployment: str | None) -> int:
    """The answer cap; for reasoning models it also covers their hidden reasoning."""
    return REASONING_MAX_COMPLETION_TOKENS if is_reasoning_model(deployment) else MAX_TOKENS


def step_timeout_s(deployment: str | None, default: float) -> float:
    """MATCHMIND_AI_STEP_TIMEOUT_S if set, else REASONING_TIMEOUT_S for reasoning models."""
    try:
        value = float(os.environ.get("MATCHMIND_AI_STEP_TIMEOUT_S", ""))
        if 0 < value <= 30:
            return value
    except ValueError:
        pass
    return max(default, REASONING_TIMEOUT_S) if is_reasoning_model(deployment) else default


def api_version_for(deployment: str | None, requested: str) -> str:
    """Raise an older API version to the first one that takes `reasoning_effort`."""
    if is_reasoning_model(deployment) and requested[:10] < REASONING_MIN_API_VERSION[:10]:
        return REASONING_MIN_API_VERSION
    return requested


class AzureOpenAILLM:
    enabled = True
    provider = "azure_openai"

    def __init__(
        self,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self.model = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT", DEFAULT_DEPLOYMENT)
        self.api_version = api_version_for(
            self.model, api_version or os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)
        )
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            from openai import AzureOpenAI

            if not self.endpoint:
                raise LLMError("AZURE_OPENAI_ENDPOINT is not set")
            token_provider = get_bearer_token_provider(DefaultAzureCredential(), TOKEN_SCOPE)
            self._client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self.api_version,
                max_retries=0,
            )
        return self._client

    def complete_json(
        self, system: str, user: dict[str, Any], schema: type[BaseModel], timeout_s: float
    ) -> BaseModel:
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                **completion_params(self.model),
                timeout=timeout_s,
            )
            raw = response.choices[0].message.content
        except LLMError:
            raise
        except Exception as exc:  # network, auth, throttling: never leak provider text
            raise LLMError(type(exc).__name__) from exc
        return parse_json(raw, schema)


def ai_enabled() -> bool:
    """The one switch for paid AI: MATCHMIND_AI_ENABLED = true, 1 or yes (any case)."""
    return os.environ.get("MATCHMIND_AI_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


class ModelBudget:
    """Process-wide cap on paid model calls: a total (MATCHMIND_AI_BUDGET, default
    300) and a rolling per-minute rate (MATCHMIND_AI_RATE_PER_MIN, default 30).
    Once either is spent the crew uses templates with fallback_reason 'budget'."""

    def __init__(
        self,
        total: int | None = None,
        per_minute: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.total = total if total is not None else _env_int("MATCHMIND_AI_BUDGET", 300)
        self.per_minute = per_minute if per_minute is not None else _env_int("MATCHMIND_AI_RATE_PER_MIN", 30)
        self.clock = clock
        self.used = 0
        self._recent: deque[float] = deque()
        self._lock = threading.Lock()

    def take(self) -> bool:
        """Spend one call if the budget and the rate allow it."""
        with self._lock:
            now = self.clock()
            while self._recent and now - self._recent[0] >= 60.0:
                self._recent.popleft()
            if self.used >= self.total or len(self._recent) >= self.per_minute:
                return False
            self.used += 1
            self._recent.append(now)
            return True


BUDGET = ModelBudget()


def default_budget() -> ModelBudget:
    return BUDGET


def llm_provider() -> str:
    """MATCHMIND_LLM_PROVIDER: azure_openai (default) or foundry_agents. Anything
    else is logged and read as the default."""
    value = os.environ.get("MATCHMIND_LLM_PROVIDER", "").strip().lower() or "azure_openai"
    if value not in PROVIDERS:
        logger.warning("MATCHMIND_LLM_PROVIDER=%r is not one of %s; using azure_openai", value, PROVIDERS)
        return "azure_openai"
    return value


def provider_of(llm: Any) -> str:
    """What /api/crew/status reports: templates, azure_openai or foundry_agents."""
    if not getattr(llm, "enabled", False):
        return "templates"
    provider = getattr(llm, "provider", "azure_openai")
    return provider if provider in PROVIDERS else "azure_openai"


def make_llm() -> LLM:
    """A paid model client only when the owner has switched paid AI on, from the
    provider MATCHMIND_LLM_PROVIDER names; templates otherwise. No client talks
    to Azure until its first call."""
    if not ai_enabled():
        return TemplateLLM()
    if llm_provider() == "foundry_agents":
        from matchmind.foundry.agent_service import FoundryAgentsLLM

        return FoundryAgentsLLM()
    return AzureOpenAILLM()
