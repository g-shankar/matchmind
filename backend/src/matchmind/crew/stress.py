"""Stress test the crew: one moment, one fault, run in a throwaway sandbox.

A viewer picks a moment and one fault from a fixed list:

- `wrong_number`: the Commentator's draft carries a number that is not in the
  moment's facts. The fact-checker must reject it and the template takes over.
- `analyst_down`: the Analyst's model step fails. The template explanation
  takes over and the card is still voiced.
- `model_down`: the Commentator's model step fails (the model is unreachable).
- `bad_handoff`: the Commentator hands the fact-checker something that is not
  the agreed `CommentatorOut` shape.

Isolation: every run builds a new `Crew` with its own caches, traces, breakers,
budget and health counters, and works on a deep copy of the moment's bundle.
The live crew, the cards other viewers see and the cue sheet are never read for
writing. The sandbox's "model" is `FaultLLM`, a local stand-in that never makes
a network call, so a stress test can never spend on paid AI; the safe card is
voiced by `TemplateLLM()`. Spans and service-level counters are not recorded
for sandbox steps, so a stress test never shows up in the live crew's health.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

from matchmind.crew import analyst, commentator
from matchmind.crew.contracts import MomentBundle, StudioLanguage, ViewerProfile
from matchmind.crew.crew import Crew
from matchmind.crew.fact_checker import check_all
from matchmind.crew.llm import LLMError, ModelBudget, TemplateLLM
from matchmind.crew.translator import OffTranslator
from matchmind.simulator.teams import Team

Fault = Literal["wrong_number", "analyst_down", "model_down", "bad_handoff"]
FAULTS: tuple[Fault, ...] = ("wrong_number", "analyst_down", "model_down", "bad_handoff")
# Reason strings from the fact-checker are kept short and few, so the answer stays bounded.
REASONS_MAX = 3
REASON_CHARS = 160
FIRST_WRONG = 97
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


class _NotTheContract(BaseModel):
    """What a malformed hand-off looks like: the wrong shape for the Commentator."""

    text: str


class FaultLLM:
    """A local stand-in for the model inside the sandbox. Never calls the network."""

    enabled = True
    model = "sandbox"
    provider = "templates"

    def __init__(self, fault: Fault, draft: dict[str, str] | None = None) -> None:
        self.fault = fault
        self.draft = draft or {}

    def complete_json(self, system: str, user: dict[str, Any], schema: type[BaseModel], timeout_s: float):
        if schema is analyst.AnalystOut:
            raise LLMError("sandbox: the Analyst is knocked out")
        if self.fault == "model_down":
            raise LLMError("sandbox: the model is unreachable")
        if self.fault == "bad_handoff":
            return _NotTheContract(text="half a hand-off")
        return commentator.CommentatorOut(headline=self.draft["headline"], body=self.draft["body"])


class _SandboxCrew(Crew):
    """A crew whose steps leave no spans or health counters behind."""

    def _span(self, *args: Any, **kwargs: Any) -> None:
        return None


def wrong_number_for(facts: dict[str, Any]) -> int:
    """The first whole number from 97 upwards that no fact could stand for."""
    values: set[float] = set()
    for v in facts.values():
        if isinstance(v, bool):
            continue
        if isinstance(v, int | float):
            values.update({float(v), round(float(v)), round(float(v) * 100)})
    n = FIRST_WRONG
    while float(n) in values:
        n += 1
    return n


def inject(body: str, wrong: int) -> str:
    """The body with its first number swapped for `wrong` (or `wrong` added)."""
    if _NUMBER.search(body):
        return _NUMBER.sub(str(wrong), body, count=1)
    return f"{body} {wrong}"


CARD_FIELDS = (
    "moment_id",
    "kind",
    "language",
    "rtl",
    "headline",
    "body",
    "why",
    "produced_by",
    "fallback_reason",
)


def card_view(card: dict[str, Any]) -> dict[str, Any]:
    """The few card fields the stress test shows: keeps the answer small."""
    return {k: card.get(k) for k in CARD_FIELDS}


def _reasons(reasons: list[str]) -> list[str]:
    return [r[:REASON_CHARS] for r in reasons[:REASONS_MAX]]


def run(
    teams: dict[str, Team], live_bundle: MomentBundle, fault: Fault, profile: ViewerProfile
) -> dict[str, Any]:
    """Run one moment through a sandbox crew with one fault. Returns the steps and the safe card."""
    if fault not in FAULTS:
        raise ValueError("unknown fault")
    lang: StudioLanguage = profile.language  # type: ignore[assignment]
    bundle = live_bundle.model_copy(deep=True)
    m = bundle.moment
    sandbox = _SandboxCrew(
        teams,
        llm=FaultLLM(fault),
        translator=OffTranslator(),
        orchestrator="in_process",
        budget=ModelBudget(total=4, per_minute=4),
        timeout_s=1.0,
    )
    steps: list[dict[str, Any]] = []
    injected: str | None = None
    try:
        # Analyst: knocked out, or the explanation the live crew already checked.
        if fault == "analyst_down":
            steps.append({"agent": "analyst", "status": "down", "code": "analyst_down"})
            explanation = sandbox.fact_check_explanation(m, sandbox.analyst_step(m))
            bundle = bundle.model_copy(update={"explanation": explanation})
            steps.append(
                {"agent": "analyst", "status": "fallback", "code": "template_explanation", "detail": "error"}
            )
            sandbox.llm = TemplateLLM()  # the rest of the crew carries on in template mode
        else:
            steps.append({"agent": "analyst", "status": "ok", "code": "explained"})

        if fault == "wrong_number":
            template, _ = commentator.template_narrative_with_templates(
                m, profile.persona, lang, sandbox.team_name(profile.favourite_team), profile.focus_player_id
            )
            wrong = wrong_number_for(dict(m.facts))
            injected = str(wrong)
            sandbox.llm = FaultLLM(
                fault, {"headline": template.headline, "body": inject(template.body, wrong)}
            )
        draft = sandbox.commentator_step(bundle, profile)
        if draft is None:
            return {"moment_id": m.moment_id, "fault": fault, "steps": steps, "card": None, "safe": False}

        if fault == "wrong_number":
            steps.append(
                {"agent": "commentator", "status": "injected", "code": "wrong_number", "detail": injected}
            )
        elif fault == "model_down":
            steps.append({"agent": "commentator", "status": "down", "code": "model_down"})
        elif fault == "bad_handoff":
            steps.append({"agent": "commentator", "status": "malformed", "code": "bad_handoff"})
        else:
            steps.append({"agent": "commentator", "status": "ok", "code": "drafted"})

        # Fact-checker: the same check the live crew runs on a model draft.
        if draft.result is not None:
            verdict = check_all(
                {"headline": draft.result.headline, "body": draft.result.body},
                m.facts,
                lang,
                strict_words=True,
                roster=sandbox.protected_names,
            )
            steps.append(
                {
                    "agent": "fact_checker",
                    "status": "ok" if verdict.ok else "rejected",
                    "code": "passed" if verdict.ok else "number_not_in_facts",
                    "detail": injected,
                    "reasons": _reasons(verdict.reasons),
                }
            )
        elif draft.reason:
            steps.append(
                {
                    "agent": "fact_checker",
                    "status": "skipped",
                    "code": "nothing_to_check",
                    "detail": draft.reason,
                }
            )
        else:
            steps.append({"agent": "fact_checker", "status": "ok", "code": "passed"})

        narrative = sandbox.fact_check_narrative(draft)
        if narrative is None:
            return {"moment_id": m.moment_id, "fault": fault, "steps": steps, "card": None, "safe": False}
        if narrative.fallback_reason or fault == "analyst_down":
            steps.append(
                {
                    "agent": "fallback",
                    "status": "took_over",
                    "code": "template",
                    "detail": (narrative.fallback_reason or "error").split(":")[0][:32],
                }
            )
        key = (m.moment_id, profile.persona, lang, profile.favourite_team, profile.focus_player_id)
        card = sandbox.producer_step(draft, narrative, key)
        final = check_all(
            {"headline": card.headline, "body": card.body}, m.facts, lang, roster=sandbox.protected_names
        )
        safe = final.ok and card.produced_by == "template" and (injected is None or injected not in card.body)
        steps.append({"agent": "producer", "status": "ok" if safe else "rejected", "code": "safe_card"})
        return {
            "moment_id": m.moment_id,
            "fault": fault,
            "steps": steps,
            "card": card_view(card.model_dump(mode="json")),
            "safe": safe,
        }
    finally:
        sandbox._pool.shutdown(wait=False, cancel_futures=True)
