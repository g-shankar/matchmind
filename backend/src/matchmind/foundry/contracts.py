"""The exact JSON each model step receives and each deterministic agent takes.

The crew builds model requests as plain dicts (`analyst.ai_payload`, ...).
These models describe those dicts for the agent manifests; a test checks the
real payloads against them (`extra="forbid"`), so they cannot drift apart.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from matchmind.crew.analyst import TacticalTag
from matchmind.crew.contracts import (
    FactValue,
    Language,
    Moment,
    MomentBundle,
    Narrative,
    ViewerProfile,
)
from matchmind.crew.fact_checker import Field as TextField
from matchmind.schema import Event
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

REPAIR = "Present only on the one repair retry after an answer that did not match the schema."


class AnalystIn(BaseModel):
    """What the Analyst model step receives."""

    model_config = ConfigDict(extra="forbid")
    kind: str
    match_clock: str
    facts: dict[str, FactValue] = Field(description="The only numbers and names the answer may use.")
    allowed_tactical_tags: list[TacticalTag]
    verdict: str | None = Field(
        default=None, description="Better-option moments: the decision the text must state."
    )
    repair: str | None = Field(default=None, description=REPAIR)


class CommentatorIn(BaseModel):
    """What the Commentator model step receives."""

    model_config = ConfigDict(extra="forbid")
    kind: str
    match_clock: str
    audience: str = Field(description="The persona brief (casual, tactical, fantasy, player spotlight).")
    language: str = Field(description="Language name, e.g. 'Spanish'.")
    why_it_matters: str = Field(description="The fact-checked Analyst explanation.")
    facts: dict[str, FactValue]
    verdict: str | None = Field(
        default=None, description="Better-option moments: the decision the text must state."
    )
    favourite_team: str | None = None
    your_team_wording: str | None = None
    focus_player_id: str | None = None
    repair: str | None = Field(default=None, description=REPAIR)


class RecapIn(BaseModel):
    """What the Producer's recap model step receives (full time only)."""

    model_config = ConfigDict(extra="forbid")
    audience: str
    language: str
    full_time: Literal[True]
    facts: dict[str, FactValue]
    favourite_team: str | None = None
    repair: str | None = Field(default=None, description=REPAIR)


class SpotterIn(BaseModel):
    """One event with the stats engine's numbers at that moment."""

    event: Event
    metrics: EventMetrics
    snapshot: MatchStateSnapshot
    players: dict[str, PlayerStats]


class SpotterOut(BaseModel):
    moments: list[Moment]


class FactCheckIn(BaseModel):
    text: str
    facts: dict[str, FactValue]
    language: Language = "en"
    field: TextField = "text"
    strict_words: bool = Field(
        default=False, description="True for model text: number words are checked too."
    )


class ProducerIn(BaseModel):
    bundle: MomentBundle
    narrative: Narrative
    why: str
    profile: ViewerProfile
