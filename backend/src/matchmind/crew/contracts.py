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
