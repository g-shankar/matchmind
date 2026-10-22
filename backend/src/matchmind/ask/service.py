"""Ask the studio: one question in, one checked answer out (docs/ASK.md).

    guard (refuse hostile text) -> rule parser -> [model intent, AI switch on only]
    -> deterministic answer from the stats engine -> fact-check -> claims

Every answer is template text in the viewer's language (en, es, fr, ar; other
languages get English, marked as such) with the facts, evidence and claims
behind it. A refusal is one plain sentence. The question is never echoed back,
stored or logged; logs carry the outcome, the intent kind and the length.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from matchmind.crew.claims import text_claims
from matchmind.crew.contracts import (
    RTL_LANGUAGES,
    Claim,
    Evidence,
    FactCheck,
    FactValue,
    Language,
)
from matchmind.crew.fact_checker import check
from matchmind.crew.i18n import fill
from matchmind.crew.llm import LLM
from matchmind.crew.spoilers import catchup_event_ids, catchup_moment_id
from matchmind.crew.spotter import surname

from .about import is_about, names_data
from .answer import AskContext, Composed, _team_name, compose, evidence_for, minute_of
from .guard import RefusalReason, check_question, safe_display_name
from .i18n import answer_language, ask_pack
from .intents import CHIPS, Intent
from .model import model_intent
from .parser import ParseResult, Roster, parse

logger = logging.getLogger("pitchpulse.ask")
ABOUT_INTENT = Intent(kind="about")

AskStatus = Literal["answered", "refused", "hidden", "clarify", "not_yet"]
UnderstoodBy = Literal["chip", "rules", "model"]


class AskClock(BaseModel):
    """The playback position the answer was computed at. Nothing later is read."""

    clock: str
    period: int
    clock_s: float
    ended: bool


class MetricInfo(BaseModel):
    """For explain_metric: the registry entry behind the explanation (GET /api/metrics)."""

    id: str
    name: str
    formula: str
    quality: str


class AskAnswer(BaseModel):
    status: AskStatus
    reason: RefusalReason | None = Field(default=None, description="Why a question was refused")
    intent: Intent | None = None
    understood_by: UnderstoodBy | None = Field(
        default=None,
        description="chip: a suggested question; rules: the parser; model: the optional model path",
    )
    answer: str = Field(description="Plain text. Render as text, never as HTML.")
    language: Language
    text_language: Language
    rtl: bool
    as_of: AskClock
    spoilers: bool = Field(description="False: answered in catch-up mode (no result facts)")
    facts: dict[str, FactValue] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)
    moment_ids: list[str] = Field(default_factory=list, description="Moments behind the answer (claim audit)")
    metric: MetricInfo | None = None
    produced_by: Literal["template"] = "template"
    fact_check: FactCheck = Field(default_factory=lambda: FactCheck(ok=True))


def roster_names(ctx: AskContext) -> tuple[tuple[str, ...], dict[str, str]]:
    """Protected squad and club names (for the wrong-name check) and name -> id (claims)."""
    names: set[str] = set()
    ids: dict[str, str] = {}
    for t in ctx.teams.values():
        for name in (t.name, t.short_name):
            if name:
                names.add(name)
                ids.setdefault(name, t.team_id)
        for p in t.players:
            names.update({p.name, surname(p.name)})
            ids.setdefault(p.name, p.player_id)
            ids.setdefault(surname(p.name), p.player_id)
    return tuple(sorted(names)), ids


def _clock(ctx: AskContext) -> AskClock:
    return AskClock(clock=ctx.clock, period=ctx.period, clock_s=ctx.clock_s, ended=ctx.ended)


def _base(ctx: AskContext, language: str, spoilers: bool) -> dict:
    text_lang = answer_language(language)
    return {
        "language": language,
        "text_language": text_lang,
        "rtl": text_lang in RTL_LANGUAGES,
        "as_of": _clock(ctx),
        "spoilers": spoilers,
    }


def refusal(ctx: AskContext, language: str, spoilers: bool, reason: RefusalReason) -> AskAnswer:
    pack = ask_pack(answer_language(language))
    text = pack["refuse"].get(reason, pack["refuse"]["off_topic"])
    return AskAnswer(status="refused", reason=reason, answer=text, **_base(ctx, language, spoilers))


def ask(
    ctx: AskContext,
    *,
    question: str | None = None,
    chip: str | None = None,
    language: str = "en",
    spoilers: bool = True,
    llm: LLM | None = None,
    metric_info: dict[str, MetricInfo] | None = None,
    client: str = "local",
) -> AskAnswer:
    """Answer one question (or suggested chip) about the match as of `ctx`. `client`
    keys the optional model path's per-client quota (never logged)."""
    roster = Roster.build(ctx.teams, ctx.home_id, ctx.away_id)
    understood: UnderstoodBy
    if chip is not None:
        intent = CHIPS.get(chip)
        if intent is None:
            return _log(refusal(ctx, language, spoilers, "off_topic"), 0)
        understood = "chip"
    else:
        text = question or ""
        guard = check_question(text)
        if guard.refusal == "real_name" and names_data(text) and is_about(text, roster):
            # "Is this real <competition> data?": the honest, fixed answer is that it is synthetic.
            # Without a data word ("es real madrid mejor...") the real name is refused as usual.
            return _log(answer_intent(ctx, ABOUT_INTENT, "rules", language, spoilers), len(text))
        if guard.refusal is not None:
            return _log(refusal(ctx, language, spoilers, guard.refusal), len(text))
        parsed = parse(text, guard.normalised, roster, minute_of(ctx.clock_s, ctx.period))
        if parsed.intent is None and not parsed.clarify and is_about(text, roster):
            parsed = ParseResult(intent=ABOUT_INTENT)
        if parsed.refusal is not None:
            return _log(refusal(ctx, language, spoilers, parsed.refusal), len(text))
        if parsed.clarify:
            return _log(
                _clarify(ctx, language, spoilers, parsed.clarify_number or 0, parsed.clarify), len(text)
            )
        intent = parsed.intent
        understood = "rules"
        if intent is None and llm is not None:
            intent = model_intent(text, llm, roster, client=client)
            understood = "model"
        if intent is None:
            return _log(refusal(ctx, language, spoilers, "off_topic"), len(text))
    return _log(answer_intent(ctx, intent, understood, language, spoilers, metric_info), len(question or ""))


def answer_intent(
    ctx: AskContext,
    intent: Intent,
    understood: UnderstoodBy,
    language: str,
    spoilers: bool,
    metric_info: dict[str, MetricInfo] | None = None,
) -> AskAnswer:
    lang = answer_language(language)
    composed = compose(intent, ctx, lang, spoilers)
    base = _base(ctx, language, spoilers)
    if composed.status == "hidden":
        return AskAnswer(
            status="hidden", intent=intent, understood_by=understood, answer=ask_pack(lang)["hidden"], **base
        )
    protected, ids = roster_names(ctx)
    problems: list[str] = []
    claims: list[Claim] = []
    for text, template in composed.sentences:
        verdict = check(text, composed.facts, lang, "text", roster=protected)
        problems += verdict.reasons
        claims += text_claims(
            text,
            "body",
            composed.facts,
            lang,
            template=template,
            source_event_ids=composed.source_event_ids,
            roster=ids,
        )
    if problems:
        logger.warning("ask answer failed the fact-check: intent=%s reasons=%s", intent.kind, problems[:3])
        out = refusal(ctx, language, spoilers, "fact_check")
        return out.model_copy(
            update={"intent": intent, "fact_check": FactCheck(ok=False, reasons=problems[:5])}
        )
    sep = "" if lang == "ja" else " "
    if not spoilers:  # catch-up: the same opaque event and moment ids as the stream (crew/spoilers.py)
        claims = [
            c.model_copy(update={"source_event_ids": catchup_event_ids(c.source_event_ids)}) for c in claims
        ]
        composed.source_event_ids = catchup_event_ids(composed.source_event_ids)
        composed.moment_ids = [catchup_moment_id(m) for m in composed.moment_ids]
    return AskAnswer(
        status=composed.status,  # type: ignore[arg-type]
        intent=intent,
        understood_by=understood,
        answer=sep.join(text for text, _ in composed.sentences),
        facts=composed.facts,
        evidence=evidence_for(composed, _labels(composed, lang)),
        claims=claims,
        source_event_ids=list(dict.fromkeys(composed.source_event_ids))[:24],
        moment_ids=list(dict.fromkeys(composed.moment_ids))[:12],
        metric=(metric_info or {}).get(intent.metric or "") if intent.kind == "explain_metric" else None,
        fact_check=FactCheck(ok=True),
        **base,
    )


def _labels(composed: Composed, lang: str) -> dict[str, str]:
    names = {k: str(v) for k, v in composed.facts.items() if isinstance(v, str)}
    return {
        k: v.replace("{home}", names.get("home", "")).replace("{away}", names.get("away", ""))
        for k, v in ask_pack(lang)["evidence"].items()
    }


def _clarify(ctx: AskContext, language: str, spoilers: bool, number: int, ids: tuple[str, ...]) -> AskAnswer:
    lang = answer_language(language)
    options = []
    for pid in ids:
        for t in ctx.teams.values():
            for p in t.players:
                if p.player_id == pid and safe_display_name(p.name):
                    options.append(f"{p.name} ({_team_name(ctx, t.team_id)})")
    facts: dict[str, FactValue] = {"number": number, "options": ", ".join(options)}
    text = fill(ask_pack(lang)["clarify_number"], facts, lang)
    return AskAnswer(status="clarify", answer=text, facts=facts, **_base(ctx, language, spoilers))


def _log(answer: AskAnswer, length: int) -> AskAnswer:
    # Never the question itself: only what happened to it.
    logger.info(
        "ask status=%s reason=%s intent=%s by=%s len=%d",
        answer.status,
        answer.reason,
        answer.intent.kind if answer.intent else None,
        answer.understood_by,
        length,
    )
    return answer
