"""Shared event contract for Matchmind.

Every component (simulator, ingest, stats engine, agents, overlay API) reads
and writes these models, so the contract lives in exactly one place.

Coordinates are metres on a 105 x 68 pitch. The home team always attacks
towards x = 105 and the away team towards x = 0, for the whole match.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


class EventType(StrEnum):
    MATCH_START = "match_start"
    PERIOD_START = "period_start"
    PASS = "pass"
    CARRY = "carry"
    DRIBBLE = "dribble"
    SHOT = "shot"
    RUN = "run"
    INTERCEPTION = "interception"
    TACKLE = "tackle"
    CLEARANCE = "clearance"
    RECOVERY = "recovery"
    FOUL = "foul"
    CARD = "card"
    MILESTONE = "milestone"
    PERIOD_END = "period_end"
    MATCH_END = "match_end"


class Outcome(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    OUT = "out"
    WON = "won"
    GOAL = "goal"
    SAVED = "saved"
    BLOCKED = "blocked"
    OFF_TARGET = "off_target"
    FOUND = "found"
    NOT_FOUND = "not_found"


class BodyPart(StrEnum):
    RIGHT_FOOT = "right_foot"
    LEFT_FOOT = "left_foot"
    HEAD = "head"


class Point(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: float = Field(ge=0, le=PITCH_LENGTH_M)
    y: float = Field(ge=0, le=PITCH_WIDTH_M)


class FramePlayer(BaseModel):
    """One player's location inside a shot freeze frame or a tracking frame."""

    model_config = ConfigDict(frozen=True)

    player_id: str
    team: str
    x: float = Field(ge=0, le=PITCH_LENGTH_M)
    y: float = Field(ge=0, le=PITCH_WIDTH_M)
    teammate: bool = Field(description="True if on the same team as the event's actor.")
    keeper: bool = False
    actor: bool = False


class TrackingFrame(BaseModel):
    """Positions at one instant inside a run window (every 0.5 s)."""

    t_offset_s: float = Field(ge=0)
    ball: Point
    players: list[FramePlayer]


class LineupPlayer(BaseModel):
    player_id: str
    team: str
    name: str
    number: int
    position: str


class Event(BaseModel):
    """A single match event. One JSON object per line in the JSONL stream."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: str
    match_id: str
    seq: int = Field(ge=0, description="Strictly increasing order within a match.")
    ts: datetime = Field(description="Wall-clock time the event happened (UTC).")
    period: int = Field(ge=1, le=2)
    clock_s: float = Field(ge=0, description="Match clock in seconds; period 2 starts at 2700.")
    match_clock: str = Field(description="Broadcast clock, e.g. '67:20' or '90+2:15'.")
    type: EventType
    team: str | None = None
    player_id: str | None = None
    receiver_id: str | None = Field(
        default=None, description="Intended receiver of a pass (set even if incomplete)."
    )
    possession_id: int | None = None
    start: Point | None = None
    end: Point | None = None
    outcome: Outcome | None = None
    ball_speed_mps: float | None = Field(default=None, ge=0)
    player_speed_mps: float | None = Field(default=None, ge=0)
    under_pressure: bool = False
    pressure_players: list[str] = Field(default_factory=list)
    body_part: BodyPart | None = None
    freeze_frame: list[FramePlayer] | None = Field(
        default=None,
        description="Shots only: everyone in or around the box (final 35 m) at the moment of the shot.",
    )
    tracking: list[TrackingFrame] | None = Field(
        default=None,
        description="Runs only: runner, ball carrier, back line and keeper every 0.5 s for 3 s.",
    )
    lineups: list[LineupPlayer] | None = Field(default=None, description="match_start only.")
    details: dict[str, str | int | float | bool] = Field(default_factory=dict)
    labels: list[str] = Field(
        default_factory=list,
        description=(
            "Ground-truth labels for evaluation (scripted beats, pressure spells). "
            "Consumers must strip these before anything reaches an agent."
        ),
    )

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True)
