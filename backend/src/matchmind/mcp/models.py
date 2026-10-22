"""Typed inputs and outputs of the PitchPulse MCP tools.

Inputs are closed: identifiers with a fixed pattern, enums and bounded numbers.
No tool takes free text, so nothing a caller types can reach a model prompt.

Outputs describe the payloads of docs/API-CONTRACT.md. The tools hand back the
very payload the REST API serves (see `matchmind.api.reads`); these models
publish its JSON Schema and validate it on the way out.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from matchmind.api.session import NO_BOOKMARK_KINDS
from matchmind.autoevent.score import AutoEventingStatus
from matchmind.crew.contracts import (
    CrewStatus,
    CrewTrace,
    Explanation,
    Language,
    LanguageInfo,
    Moment,
    MomentKind,
    OverlayCard,
    Persona,
    Recap,  # noqa: F401 - a tool output as-is
    ViewerProfile,
)
from matchmind.simulator.teams import TEAMS
from matchmind.stats.models import MatchStateSnapshot, PlayerStats

MOMENT_ID = r"^[A-Za-z0-9_.:+-]{1,80}$"
TEAM_ID = r"^[A-Z]{2,5}$"
PLAYER_ID = r"^[A-Z]{2,5}-[0-9]{1,3}$"
MAX_CLOCK_S = 10_000

BookmarkKind = Literal[tuple(k.value for k in MomentKind if k.value not in NO_BOOKMARK_KINDS)]  # type: ignore[valid-type]
TeamCode = Literal[tuple(TEAMS)]  # type: ignore[valid-type]  # the fictional clubs in teams.py


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Inputs -------------------------------------------------------------------------------------


class NoInput(_In):
    pass


class ListMomentsIn(_In):
    kind: BookmarkKind | None = Field(default=None, description="Only moments of this kind.")
    period: Literal[1, 2] | None = Field(default=None, description="Only this half.")
    from_clock_s: float | None = Field(
        default=None, ge=0, le=MAX_CLOCK_S, description="Only moments at or after this match clock (s)."
    )
    to_clock_s: float | None = Field(
        default=None, ge=0, le=MAX_CLOCK_S, description="Only moments at or before this match clock (s)."
    )
    played_only: bool = Field(
        default=False, description="Only moments already played at the live position (no spoilers)."
    )
    limit: int = Field(default=50, ge=1, le=200, description="Most moments to return, earliest first.")


class MomentIn(_In):
    moment_id: str = Field(pattern=MOMENT_ID, description="A moment id from list_moments.")


class CardIn(_In):
    moment_id: str = Field(pattern=MOMENT_ID, description="A moment id from list_moments.")
    persona: Persona = Field(default="casual", description="Audience the card is voiced for.")
    language: Language = Field(default="en", description="Language of the card text.")
    favourite_team: str | None = Field(
        default=None, pattern=TEAM_ID, description="Viewer's club id (marks cards about that side)."
    )


class RecapIn(_In):
    persona: Persona = Field(default="casual", description="Audience the recap is written for.")
    language: Language = Field(default="en", description="Language of the recap text.")


class PlayerStatsIn(_In):
    player_id: str | None = Field(
        default=None, pattern=PLAYER_ID, description="Fictional player id, e.g. NBR-9. Omit for everyone."
    )


class CrewIn(_In):
    trace_limit: int = Field(default=20, ge=0, le=100, description="Most recent crew traces to include.")


class EventsIn(_In):
    limit: int = Field(default=20, ge=1, le=100, description="How many of the latest events to return.")


class SimulateIn(_In):
    seed: int = Field(
        ge=1, le=99_999, description="Seed for the simulator; the same seed gives the same match."
    )
    home: TeamCode = Field(default="NBR", description="Home club id (the other fictional club plays away).")


# --- Outputs ------------------------------------------------------------------------------------


class RosterPlayer(BaseModel):
    player_id: str
    name: str = Field(description="Fictional name")
    number: int
    position: str
    line: Literal["GK", "DEF", "MID", "FWD"]


class TeamOut(BaseModel):
    team_id: str
    name: str = Field(description="Fictional club name")
    short_name: str
    primary_color: str
    secondary_color: str
    formation: str
    style: str
    players: list[RosterPlayer]


class TeamsOut(BaseModel):
    home: TeamOut
    away: TeamOut


class ControlChaos(BaseModel):
    home_control_pct: float
    away_control_pct: float
    chaos_index: float
    current_tempo: str
    rolling_momentum_home: float


class Playback(BaseModel):
    is_running: bool
    speed_multiplier: int
    clock_s: float
    match_clock: str
    period: int
    ended: bool


class BookmarkOut(BaseModel):
    moment_id: str
    kind: str
    match_clock: str
    clock_s: float
    period: int
    title: str


class PlayerStatsOut(PlayerStats):
    """A player's stats with his identity from the fictional squads."""

    name: str | None = Field(default=None, description="Fictional name")
    number: int | None = Field(default=None, description="Shirt number")
    position: str | None = Field(default=None, description="Position code, e.g. ST")


class SnapshotOut(BaseModel):
    """INITIAL_SNAPSHOT.data for the default viewer profile."""

    match_id: str
    clock: str
    period: int
    home_score: int
    away_score: int
    teams: TeamsOut
    state: MatchStateSnapshot
    control_chaos: ControlChaos
    profile: ViewerProfile
    playback: Playback
    recent_cards: list[OverlayCard]
    bookmarks: list[BookmarkOut]
    players: list[PlayerStatsOut]
    crew: CrewStatus
    languages: list[LanguageInfo]
    auto_eventing: AutoEventingStatus | None


class MomentsOut(BaseModel):
    count: int
    moments: list[BookmarkOut]


class MomentDetailOut(BaseModel):
    moment: Moment = Field(description="Facts (the only numbers any agent may say) and source event ids")
    explanation: Explanation = Field(description="Why it matters, with evidence")
    replay: dict[str, Any] | None = Field(description="Drawing geometry for better-option and unfound-run")
    played: bool = Field(description="Whether the live position has reached this moment")


class PlayersOut(BaseModel):
    players: list[PlayerStatsOut]


class CrewOut(BaseModel):
    status: CrewStatus
    traces: list[CrewTrace]


class XYOut(BaseModel):
    x: float
    y: float


class MetricsOut(BaseModel):
    pass_distance_m: float | None
    pass_difficulty: int | None
    progressive: bool
    ball_speed_kmh: float | None
    player_speed_kmh: float | None
    sprint: bool
    fast_shot: bool
    chance_quality: float | None
    distance_to_goal_m: float | None
    pitch_zone: str | None
    xt_delta: float | None


class EventOut(BaseModel):
    event_id: str
    seq: int
    match_clock: str
    clock_s: float
    period: int
    type: str
    team: str | None
    player_id: str | None
    receiver_id: str | None
    start: XYOut | None
    end: XYOut | None
    outcome: str | None
    under_pressure: bool
    details: dict[str, str | int | float | bool]
    metrics: MetricsOut


class EventsOut(BaseModel):
    count: int
    events: list[EventOut]


class GoalOut(BaseModel):
    event_id: str
    match_clock: str
    period: int
    team: str | None
    player_id: str | None


class SimulationOut(BaseModel):
    source: Literal["synthetic_simulator"]
    match_id: str
    seed: int
    home: TeamOut
    away: TeamOut
    score_home: int
    score_away: int
    events: int
    goals: list[GoalOut]
    final_state: MatchStateSnapshot
