"""OpenTelemetry spans for the studio crew, one per agent step.

Spans follow the OpenTelemetry GenAI semantic conventions (`invoke_agent`
operation, `gen_ai.agent.name`, `gen_ai.request.model`, ...), so Azure
Monitor Application Insights and the Microsoft Foundry tracing view can show
each agent's steps, fallbacks and fact-check verdicts.

What a span carries, and nothing else: agent, step status, duration, model
deployment (AI mode only), moment id and kind, a fallback reason from a fixed
list, and the fact-check verdict. Never model prompts or answers, card text,
fact-check reason text, or anything about a viewer (persona, language, club,
focus player).

Off unless both are true: the optional `observability` extra is installed and
APPLICATIONINSIGHTS_CONNECTION_STRING is set. With
APPLICATIONINSIGHTS_AUTHENTICATION_STRING = "Authorization=AAD;ClientId=<id>"
the exporter signs in with Microsoft Entra ID (the managed identity), so the
connection string alone cannot write telemetry. Everything else (missing
packages, a failed setup) leaves tracing as a no-op: the crew never depends
on it.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

TRACER_NAME = "matchmind.crew"
PROVIDER = "azure.ai.openai"  # gen_ai.provider.name (current conventions)
SYSTEM = "az.ai.openai"  # gen_ai.system (earlier conventions; still read by Azure tooling)
MODEL_AGENTS = frozenset({"analyst", "commentator", "recap"})
AGENT_NAMES = {
    "spotter": "Spotter",
    "analyst": "Analyst",
    "commentator": "Commentator",
    "fact_checker": "Fact-checker",
    "producer": "Producer",
    "recap": "Producer (recap)",
}
# The only fallback reasons a span may carry; anything else is dropped.
FALLBACK_REASONS = ("fact_check", "circuit_open", "budget", "timeout", "schema", "error")
_REASON_RE = re.compile(r"\b(" + "|".join(FALLBACK_REASONS) + r")\b")

_UNSET: Any = object()
_tracer: Any = _UNSET
_lock = threading.Lock()


def fallback_reason(status: str, detail: str | None) -> str | None:
    """The fallback reason category in a step's detail text, or None."""
    if status != "fallback" or not detail:
        return None
    found = _REASON_RE.search(detail)
    return found.group(1) if found else "other"


def produced_by(agent: str, status: str, detail: str | None) -> str | None:
    if agent not in MODEL_AGENTS or not detail:
        return None
    if status == "ok" and re.search(r"\bai\b", detail):
        return "ai"
    return "template"


def set_tracer(tracer: Any | None) -> None:
    """Use this tracer (tests, or an app that set up OpenTelemetry itself).
    None switches tracing off; `reset()` goes back to the environment."""
    global _tracer
    with _lock:
        _tracer = tracer


def reset() -> None:
    set_tracer(_UNSET)


def _configure_from_env() -> Any | None:
    conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if not conn:
        return None
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry import trace
    except ImportError:
        logger.info("Tracing is off: the observability extra is not installed")
        return None
    kwargs: dict[str, Any] = {
        "connection_string": conn,
        # Crew spans only: no request, log or library telemetry, so nothing a
        # viewer sends can reach the telemetry store.
        "disable_logging": True,
        "disable_metrics": True,
        "enable_live_metrics": False,
        "instrumentation_options": {
            name: {"enabled": False}
            for name in (
                "azure_sdk",
                "django",
                "fastapi",
                "flask",
                "httpx",
                "psycopg2",
                "requests",
                "urllib",
                "urllib3",
            )
        },
    }
    auth = os.environ.get("APPLICATIONINSIGHTS_AUTHENTICATION_STRING", "")
    if "authorization=aad" in auth.lower():
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError:
            logger.warning("Tracing is off: Entra ID sign-in needs azure-identity")
            return None
        client_id = re.search(r"clientid=([0-9a-fA-F-]+)", auth, re.IGNORECASE)
        kwargs["credential"] = DefaultAzureCredential(
            managed_identity_client_id=client_id.group(1) if client_id else None
        )
    # The exporter's own usage pings ("statsbeat") stay off: our resource only.
    os.environ.setdefault("APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL", "true")
    try:
        configure_azure_monitor(**kwargs)
    except Exception as exc:  # noqa: BLE001 - tracing must never stop the crew
        logger.warning("Tracing is off: Azure Monitor setup failed (%s)", type(exc).__name__)
        return None
    return trace.get_tracer(TRACER_NAME)


def tracer() -> Any | None:
    """The crew's tracer, set up once from the environment; None means off."""
    global _tracer
    if _tracer is _UNSET:
        with _lock:
            if _tracer is _UNSET:
                _tracer = _configure_from_env()
    return _tracer


def record_step(
    *,
    agent: str,
    status: str,
    ms: float,
    moment_id: str,
    moment_kind: str | None,
    detail: str | None,
    model: str | None,
) -> None:
    """One `invoke_agent` span for one finished crew step. Never raises."""
    t = tracer()
    if t is None:
        return
    try:
        attributes: dict[str, Any] = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": AGENT_NAMES.get(agent, agent),
            "gen_ai.agent.id": f"pitchpulse-{agent.replace('_', '-')}",
            "pitchpulse.step.status": status,
            "pitchpulse.moment.id": moment_id,
            "pitchpulse.crew.mode": "ai" if model else "template",
        }
        if moment_kind:
            attributes["pitchpulse.moment.kind"] = moment_kind
        if agent in MODEL_AGENTS and model:
            attributes["gen_ai.system"] = SYSTEM
            attributes["gen_ai.provider.name"] = PROVIDER
            attributes["gen_ai.request.model"] = model
        made_by = produced_by(agent, status, detail)
        if made_by:
            attributes["pitchpulse.produced_by"] = made_by
        reason = fallback_reason(status, detail)
        if reason:
            attributes["pitchpulse.fallback_reason"] = reason
            attributes["error.type"] = reason
        if agent == "fact_checker":
            attributes["pitchpulse.fact_check.verdict"] = "pass" if status == "ok" else "rejected"
        end_ns = time.time_ns()
        start_ns = end_ns - int(max(0.0, ms) * 1_000_000)
        span = t.start_span(
            f"invoke_agent {AGENT_NAMES.get(agent, agent)}", start_time=start_ns, attributes=attributes
        )
        if status == "error":
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.ERROR))
        span.end(end_time=end_ns)
    except Exception:  # noqa: BLE001 - tracing must never stop the crew
        logger.debug("crew span dropped", exc_info=True)
