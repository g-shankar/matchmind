"""Language-model clients for the studio crew.

- `TemplateLLM` (default): free, offline, never produces text. Callers see
  `enabled == False` and use the localised templates.
- `AzureOpenAILLM`: Azure OpenAI through Microsoft Entra ID (no API key),
  JSON response format, validated against a fixed pydantic schema.

Paid AI stays off unless `MATCHMIND_AI_ENABLED=true` (owner approval). The
`openai` and `azure-identity` packages are imported lazily, so the engine
works without the optional `ai` extra.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError

DEFAULT_API_VERSION = "2024-10-21"
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


class LLMError(RuntimeError):
    """The model call failed (network, auth, refusal...)."""


class LLMSchemaError(LLMError):
    """The model answered, but not with JSON matching the schema."""


@runtime_checkable
class LLM(Protocol):
    enabled: bool
    model: str | None

    def complete_json(
        self, system: str, user: dict[str, Any], schema: type[BaseModel], timeout_s: float
    ) -> BaseModel: ...


class TemplateLLM:
    """Never called for text: callers check `enabled` and use templates."""

    enabled = False
    model: str | None = None

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


class AzureOpenAILLM:
    enabled = True

    def __init__(
        self,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self.model = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        self.api_version = api_version or os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)
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
                temperature=0.3,
                max_tokens=400,
                timeout=timeout_s,
            )
            raw = response.choices[0].message.content
        except LLMError:
            raise
        except Exception as exc:  # network, auth, throttling: never leak provider text
            raise LLMError(type(exc).__name__) from exc
        return parse_json(raw, schema)


def ai_enabled() -> bool:
    return os.environ.get("MATCHMIND_AI_ENABLED", "false").strip().lower() == "true"


def make_llm() -> LLM:
    """Azure only when the owner has switched paid AI on; templates otherwise."""
    return AzureOpenAILLM() if ai_enabled() else TemplateLLM()
