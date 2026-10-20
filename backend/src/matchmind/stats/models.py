"""Typed outputs of the stats engine. Every number the crew is allowed to say
comes from one of these models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class XY(BaseModel):
    x: float
    y: float


class EventMetrics(BaseModel):
    """Deterministic metrics for one event (absolute pitch coordinates)."""

    event_id: str
    pass_distance_m: float | None = None
    pass_difficulty: int | None = Field(default=None, ge=0, le=100)
    progressive: bool = False
    forward_m: float | None = None
    ball_speed_kmh: float | None = None
    player_speed_kmh: float | None = None
    sprint: bool = False
    fast_shot: bool = False
    chance_quality: float | None = Field(default=None, ge=0, le=1)
    distance_to_goal_m: float | None = None
    pitch_zone: str | None = None
    better_option: BetterOption | None = None
    unfound_run: UnfoundRun | None = None


class BetterOption(BaseModel):
    """Trigger 1: the shot taken versus the pass that was on."""

    shot_event_id: str
    shooter_id: str
    teammate_id: str
    shot_chance_quality: float
    alt_chance_quality: float
    pass_success: float
    alt_value: float = Field(description="pass_success x alt_chance_quality")
    times_better: float
    pass_distance_m: float
    nearest_marker_m: float
    shooter_pos: XY
    teammate_pos: XY
    defenders: list[XY]
    keeper: XY | None = None


class UnfoundRun(BaseModel):
    """Trigger 2: a run in behind where the through ball was on but never came."""

    run_event_id: str
    runner_id: str
    carrier_id: str
    found: bool
    pass_on_at_s: float = Field(description="Seconds into the run when the pass was on")
    pass_on_clock: str
    clear_of_line_m: float = Field(description="How far beyond the back line the runner got")
    projected_chance_quality: float
    one_on_one: bool
    carrier_pos: XY
    runner_path: list[XY]
    target: XY
    defenders_at_pass: list[XY]


class TeamWindow(BaseModel):
    """Rolling five-minute numbers for one team."""

    possession_pct: float
    field_tilt_pct: float
    pressure_index: float = Field(ge=0, le=100)
    shots: int
    xg: float
    final_third_passes: int
    box_entries: int


class MatchStateSnapshot(BaseModel):
    match_id: str
    clock_s: float
    match_clock: str
    period: int
    home_id: str
    away_id: str
    score_home: int
    score_away: int
    home: TeamWindow
    away: TeamWindow
    momentum: float = Field(ge=-100, le=100, description="+ = home on top")
    control_chaos: float = Field(ge=-1, le=1, description="-1 chaos ... +1 control")
    tempo: str
    events_per_min: float
    turnovers_per_min: float
    avg_chain_passes: float
    xg_home: float
    xg_away: float
    shots_home: int
    shots_away: int


class PlayerStats(BaseModel):
    player_id: str
    team: str
    touches: int = 0
    passes: int = 0
    passes_completed: int = 0
    key_passes: int = 0
    shots: int = 0
    goals: int = 0
    assists: int = 0
    xg: float = 0.0
    xa: float = 0.0
    tackles_won: int = 0
    interceptions: int = 0
    top_speed_kmh: float = 0.0
    sprints: int = 0
    carry_distance_m: float = 0.0

    @property
    def pass_accuracy(self) -> float:
        return round(100 * self.passes_completed / self.passes, 1) if self.passes else 0.0


EventMetrics.model_rebuild()
