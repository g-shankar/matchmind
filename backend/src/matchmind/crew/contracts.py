"""Typed hand-offs between the studio crew agents and the viewer profile.

Every object here is produced by our own engine or crew, never by a viewer.
Numbers that reach the screen must come from `Moment.facts` (see the
fact-checker). The API serialises these models as-is; see docs/API-CONTRACT.md.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Studio languages have hand-written phrase packs (crew/i18n) and never go
# through a translation service. World languages are written in English by the
# crew, then translated by Azure AI Translator and fact-checked again (see
# docs/LANGUAGES.md); with the translator off they are shown in English.
StudioLanguage = Literal["en", "es", "fr", "ar", "ja"]
WorldLanguage = Literal["pt", "de", "hi", "zh-Hans", "sw", "id", "tr", "ko"]
Language = Literal["en", "es", "fr", "ar", "ja", "pt", "de", "hi", "zh-Hans", "sw", "id", "tr", "ko"]
STUDIO_LANGUAGES: tuple[StudioLanguage, ...] = ("en", "es", "fr", "ar", "ja")
WORLD_LANGUAGES: tuple[WorldLanguage, ...] = ("pt", "de", "hi", "zh-Hans", "sw", "id", "tr", "ko")
LANGUAGES: tuple[Language, ...] = (*STUDIO_LANGUAGES, *WORLD_LANGUAGES)
RTL_LANGUAGES: frozenset[str] = frozenset({"ar"})
TranslatedBy = Literal["azure_ai_translator"]


def is_world_language(language: str) -> bool:
    return language in WORLD_LANGUAGES


Persona = Literal["casual", "tactical", "fantasy", "player_spotlight"]
PERSONAS: tuple[Persona, ...] = ("casual", "tactical", "fantasy", "player_spotlight")

FocusMetric = Literal["pressure", "xg", "pass_difficulty", "top_speed", "momentum"]


class MomentKind(StrEnum):
    GOAL = "goal"
    CARD = "card"
    BIG_CHANCE = "big_chance"
    BETTER_OPTION = "better_option"  # "Should he have passed?"
    UNFOUND_RUN = "unfound_run"
    MOMENTUM_SWING = "momentum_swing"
    PRESSURE_SPELL = "pressure_spell"
    SPEED_BURST = "speed_burst"  # player sprint over the threshold
    ROCKET_SHOT = "rocket_shot"  # shot speed over the threshold
    DISTANCE_MILESTONE = "distance_milestone"
    HARD_PASS = "hard_pass"  # completed pass with high difficulty
    KEY_TACKLE = "key_tackle"  # tackle won in the own third that stops a dangerous attack
    MILESTONE = "milestone"  # kick-off, half-time, full-time
    CORRECTION = "correction"  # a VAR review ruled an earlier goal out (supersedes it)


FactValue = str | int | float | bool


class PlayerRef(BaseModel):
    """A player's resolved identity, so overlays can tag him by name and shirt
    number without a second lookup. Names come from our fictional squads."""

    player_id: str
    name: str
    number: int
    team: str
    position: str


class Moment(BaseModel):
    """Spotter output: something worth telling, with the numbers that back it."""

    moment_id: str
    kind: MomentKind
    clock_s: float
    match_clock: str
    period: int
    team: str | None = None
    player_ids: list[str] = Field(default_factory=list)
    players: list[PlayerRef] = Field(
        default_factory=list, description="Identity of each player in player_ids, same order."
    )
    facts: dict[str, FactValue] = Field(
        default_factory=dict, description="The only numbers any agent may say about this moment."
    )
    source_event_ids: list[str]
    priority: int = Field(ge=0, le=100)
    retracts: list[str] = Field(
        default_factory=list,
        description="Moment ids this moment rules out (a correction): they no longer count anywhere.",
    )


def retracted_ids(moments: list[Moment]) -> set[str]:
    """Moment ids ruled out by the corrections in `moments`."""
    return {mid for m in moments for mid in m.retracts}


def without_retracted(moments: list[Moment]) -> list[Moment]:
    """The moments that still stand: anything a correction ruled out is dropped."""
    gone = retracted_ids(moments)
    return [m for m in moments if m.moment_id not in gone]


class Evidence(BaseModel):
    label: str
    label_key: str | None = None
    value: FactValue
    unit: str | None = None
    source_event_id: str | None = None


class Explanation(BaseModel):
    """Analyst output: why the moment matters, with evidence."""

    moment_id: str
    why: str
    tactical_tag: str
    evidence: list[Evidence]
    produced_by: Literal["ai", "template"]
    fallback_reason: str | None = None


class Narrative(BaseModel):
    """Commentator output for one audience and language."""

    moment_id: str
    persona: Persona
    language: Language
    headline: str = Field(max_length=80)
    body: str = Field(max_length=400)
    produced_by: Literal["ai", "template"]
    fallback_reason: str | None = None


class MomentBundle(BaseModel):
    """A spotted moment with its fact-checked explanation, before it is voiced."""

    moment: Moment
    explanation: Explanation
    replay: dict | None = None


class FactCheck(BaseModel):
    ok: bool
    reasons: list[str] = Field(default_factory=list)


# --- Claims: each shown sentence tied to the facts and events behind it (docs/TRUST.md) ---------

ClaimCheck = Literal["verified_numeric", "verified_name", "unverified_text"]
ClaimField = Literal["headline", "body", "why", "title", "paragraph", "key_moment"]


class ClaimBinding(BaseModel):
    """One number or name in a sentence and the fact it was matched to."""

    text: str = Field(description="As printed")
    kind: Literal["number", "name", "text"]
    fact_key: str | None = Field(default=None, description="None: matches no fact (never on a shown card)")
    value: FactValue | None = None
    unit: str | None = None
    entity_id: str | None = Field(default=None, description="Squad player or club id for names")


class Claim(BaseModel):
    """One sentence a viewer sees, with what was machine-checked about it.

    `verified_numeric`: every number in it matches a fact (bound in `bindings`).
    `verified_name`: no numbers; its squad names match the facts.
    `unverified_text`: nothing to check (tone, wording), or a check failed (`reason`).
    Wording, tone and causal claims are never machine-verified, whatever `check` says."""

    sentence: str
    field: ClaimField
    fact_keys: list[str] = Field(default_factory=list)
    numbers: list[str] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)
    check: ClaimCheck
    reason: str
    origin: Literal["template", "matched"] = Field(
        default="matched",
        description="template: keys from the template's placeholders; matched: found by value (model "
        "or translated text)",
    )
    bindings: list[ClaimBinding] = Field(default_factory=list)


class ViewerProfile(BaseModel):
    """One viewer's choices. Lives per WebSocket connection, never shared."""

    persona: Persona = "casual"
    language: Language = "en"
    favourite_team: str | None = None
    focus_player_id: str | None = None
    focus_metric: FocusMetric | None = None


Slot = Literal["lower_third", "side_panel", "pitch_tag", "metric_alert", "full_screen"]


class OverlayCard(BaseModel):
    """Producer output: one timed, machine-readable overlay for one viewer."""

    card_id: str
    moment_id: str
    kind: MomentKind
    slot: Slot
    priority: int = Field(ge=0, le=100)
    show_at_s: float = Field(description="Match clock seconds")
    duration_s: float
    persona: Persona
    language: Language
    rtl: bool = False
    headline: str
    body: str
    why: str
    tactical_tag: str
    evidence: list[Evidence]
    player_ids: list[str] = Field(default_factory=list)
    players: list[PlayerRef] = Field(
        default_factory=list, description="Identity of each player in player_ids, same order."
    )
    team: str | None = None
    favourite_side: bool | None = Field(default=None, description="True when about the viewer's club")
    produced_by: Literal["ai", "template"]
    fallback_reason: str | None = None
    replay: dict | None = Field(
        default=None, description="Drawing geometry: BetterOption or UnfoundRun model dump"
    )
    text_language: Language | None = Field(
        default=None,
        description="Language the text is really in: `language`, or 'en' when a world language "
        "could not be translated",
    )
    translated_by: TranslatedBy | None = None
    retracts: list[str] = Field(
        default_factory=list,
        description="Correction cards only: moment ids this card rules out (their cards come down)",
    )
    claims: list[Claim] = Field(
        default_factory=list, description="Each sentence of headline, body and why, tied to its facts"
    )

    @model_validator(mode="after")
    def _text_language(self) -> OverlayCard:
        if self.text_language is None:
            self.text_language = self.language
        return self


class RecapMoment(BaseModel):
    match_clock: str
    kind: MomentKind
    headline: str
    moment_id: str


class Recap(BaseModel):
    match_id: str
    persona: Persona
    language: Language
    rtl: bool = False
    title: str
    headline: str
    summary_paragraphs: list[str]
    key_moments: list[RecapMoment]
    player_of_the_match_id: str | None
    player_of_the_match: str | None
    stats: dict[str, FactValue]
    generated_at_clock: str
    produced_by: Literal["ai", "template"]
    fact_check: FactCheck
    text_language: Language | None = None
    translated_by: TranslatedBy | None = None
    fallback_reason: str | None = None
    claims: list[Claim] = Field(default_factory=list, description="Each sentence, tied to its facts")

    @model_validator(mode="after")
    def _text_language(self) -> Recap:
        if self.text_language is None:
            self.text_language = self.language
        return self


class AgentStep(BaseModel):
    agent: Literal["spotter", "analyst", "commentator", "fact_checker", "producer", "recap", "translator"]
    ms: float
    status: Literal["ok", "fallback", "rejected", "error", "skipped"]
    detail: str | None = None


class CrewTrace(BaseModel):
    moment_id: str
    match_clock: str
    steps: list[AgentStep]


class TranslatorStatus(BaseModel):
    """Azure AI Translator, as the crew sees it right now."""

    mode: Literal["azure", "off"] = "off"
    available: bool = False
    breaker_open: bool = False
    cache_hits: int = 0
    translated: int = 0
    fallbacks: int = 0
    rejections: int = 0


class LanguageInfo(BaseModel):
    """One language the viewer can pick, and whether it can be shown in it now."""

    code: Language
    name: str = Field(description="The language's own name, e.g. 'Português'")
    english_name: str
    source: Literal["studio", "translator"]
    available: bool
    rtl: bool = False
    reason: Literal["translator_off"] | None = None


class AgentLatency(BaseModel):
    agent: str
    samples: int = Field(description="Steps in the rolling window")
    p50_ms: float
    p95_ms: float
    max_ms: float


class CrewHealth(BaseModel):
    """Rolling-window service levels (bounded memory; resets with the crew)."""

    window: int = Field(default=0, description="Most recent steps kept per agent")
    latency: list[AgentLatency] = Field(default_factory=list)
    model_steps: int = Field(default=0, description="Analyst, Commentator and recap steps in the window")
    fallback_steps: int = 0
    fallback_rate: float | None = Field(default=None, description="fallback_steps / model_steps")
    checks: int = Field(default=0, description="Fact-check verdicts in the window")
    rejected_checks: int = 0
    rejection_rate: float | None = Field(default=None, description="rejected_checks / checks")
    moments_per_min: int = Field(default=0, description="Moments spotted in the last 60 s of wall clock")


class CrewStatus(BaseModel):
    mode: Literal["ai", "template"]
    model: str | None = None
    # Who runs the model steps: "templates" (no model), Azure OpenAI chat
    # completions, or Microsoft Foundry Agent Service agents.
    provider: Literal["templates", "azure_openai", "foundry_agents"] = "templates"
    # Who chains the agents: our in-process orchestrator or a Microsoft Agent
    # Framework workflow.
    orchestrator: Literal["in_process", "agent_framework"] = "in_process"
    breakers_open: list[str] = Field(default_factory=list)
    moments: int = 0
    fallbacks: int = 0
    rejections: int = 0
    translator: TranslatorStatus = Field(default_factory=TranslatorStatus)
    health: CrewHealth = Field(default_factory=CrewHealth)


# --- Moment audit: GET /api/match/moment/{id}/audit ---------------------------------------------


class FactParity(BaseModel):
    """Do all renderings of one moment use only its facts and agree on the key ones?"""

    ok: bool
    key_facts: list[str] = Field(default_factory=list)
    anchors: list[list[str]] = Field(
        default_factory=list, description="Each rendering states at least one fact of every group"
    )
    renderings: int = 0
    withheld: int = Field(default=0, description="Audiences with no card (no template fits)")
    stated: dict[str, list[str]] = Field(
        default_factory=dict, description="'persona/language' -> key facts it states"
    )
    problems: list[str] = Field(default_factory=list)


class RenderingAudit(BaseModel):
    persona: Persona
    language: Language
    text_language: Language | None = None
    source: Literal["template_sweep", "live"]
    produced_by: Literal["ai", "template"]
    fallback_reason: str | None = None
    translated_by: TranslatedBy | None = None
    headline: str
    body: str
    why: str
    fact_check: FactCheck
    claims: list[Claim] = Field(default_factory=list)


class MomentAudit(BaseModel):
    moment_id: str
    kind: MomentKind
    match_clock: str
    period: int
    team: str | None = None
    player_ids: list[str] = Field(default_factory=list)
    facts: dict[str, FactValue]
    source_event_ids: list[str]
    explanation: Explanation
    renderings: list[RenderingAudit]
    parity: FactParity
    trace: list[AgentStep] = Field(default_factory=list)
    not_checked: list[str] = Field(default_factory=list)
    retracts: list[str] = Field(default_factory=list, description="A correction: the moment ids it rules out")
    ruled_out_by: str | None = Field(
        default=None, description="Set when a later correction (VAR) ruled this moment out: that moment's id"
    )
