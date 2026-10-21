"""Typed hand-offs between the studio crew agents and the viewer profile.

Every object here is produced by our own engine or crew, never by a viewer.
Numbers that reach the screen must come from `Moment.facts` (see the
fact-checker). The API serialises these models as-is; see docs/API-CONTRACT.md.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["en", "es", "fr", "ar", "ja"]
LANGUAGES: tuple[Language, ...] = ("en", "es", "fr", "ar", "ja")
RTL_LANGUAGES: frozenset[str] = frozenset({"ar"})

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
    MILESTONE = "milestone"  # kick-off, half-time, full-time


FactValue = str | int | float | bool


class Moment(BaseModel):
    """Spotter output: something worth telling, with the numbers that back it."""

    moment_id: str
    kind: MomentKind
    clock_s: float
    match_clock: str
    period: int
    team: str | None = None
    player_ids: list[str] = Field(default_factory=list)
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
    team: str | None = None
    favourite_side: bool | None = Field(default=None, description="True when about the viewer's club")
    produced_by: Literal["ai", "template"]
    fallback_reason: str | None = None
    replay: dict | None = Field(
        default=None, description="Drawing geometry: BetterOption or UnfoundRun model dump"
    )


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


class AgentStep(BaseModel):
    agent: Literal["spotter", "analyst", "commentator", "fact_checker", "producer", "recap"]
    ms: float
    status: Literal["ok", "fallback", "rejected", "error", "skipped"]
    detail: str | None = None


class CrewTrace(BaseModel):
    moment_id: str
    match_clock: str
    steps: list[AgentStep]


class CrewStatus(BaseModel):
    mode: Literal["ai", "template"]
    model: str | None = None
    breakers_open: list[str] = Field(default_factory=list)
    moments: int = 0
    fallbacks: int = 0
    rejections: int = 0
