"""Typed outputs of the stats engine. Every number the crew is allowed to say
comes from one of these models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

PhysicalSource = Literal["synthetic_tracking", "event_estimate"]


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
    xt_delta: float | None = None
    better_option: BetterOption | None = None
    unfound_run: UnfoundRun | None = None
    sprint_efforts: list[SprintTag] | None = Field(
        default=None,
        description="Sprints (from synthetic tracking) that peaked since the previous event; "
        "None when no tracking is attached. Internal: not sent to clients.",
    )


class SprintTag(BaseModel):
    """A sprint seen in the synthetic tracking (stats.physical)."""

    player_id: str
    period: int
    peak_clock_s: float
    peak_kmh: float
    distance_m: float


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
    tackles_lost: int = Field(default=0, description="Challenges lost: dribbled past by the ball carrier.")
    interceptions: int = 0
    top_speed_kmh: float = 0.0
    sprints: int = 0
    carry_distance_m: float = 0.0
    distance_km: float = 0.0
    # Speed bands, filled from synthetic tracking (stats.physical); 0 without it.
    walk_km: float = 0.0
    jog_km: float = 0.0
    run_km: float = 0.0
    sprint_km: float = 0.0
    physical_source: PhysicalSource = Field(
        default="event_estimate",
        description="synthetic_tracking: distance, speed bands, sprints and top speed come from the "
        "25 Hz synthetic tracking. event_estimate: distance is a lower bound from event positions and "
        "sprints/top speed come from recorded action speeds.",
    )

    @computed_field  # serialised too: the API contract lists pass_accuracy
    @property
    def pass_accuracy(self) -> float:
        return round(100 * self.passes_completed / self.passes, 1) if self.passes else 0.0

    @computed_field
    @property
    def tackles_attempted(self) -> int:
        return self.tackles_won + self.tackles_lost

    @computed_field
    @property
    def tackle_success_pct(self) -> float:
        n = self.tackles_won + self.tackles_lost
        return round(100 * self.tackles_won / n, 1) if n else 0.0


class TeamTotals(BaseModel):
    """Whole-match counting stats for one team (the basic stats layer)."""

    team: str
    passes: int = 0
    passes_completed: int = 0
    shots: int = 0
    shots_on_target: int = Field(default=0, description="Goals plus saved shots.")
    goals: int = 0
    xg: float = 0.0
    tackles_won: int = 0
    tackles_lost: int = 0
    interceptions: int = 0
    fouls: int = 0
    # PPDA parts (docs/METRICS.md): opponent passes in their own 60% of the pitch,
    # and this team's defensive actions in that same zone.
    ppda_opponent_passes: int = 0
    ppda_defensive_actions: int = 0

    @computed_field
    @property
    def pass_accuracy(self) -> float:
        return round(100 * self.passes_completed / self.passes, 1) if self.passes else 0.0

    @computed_field
    @property
    def ppda(self) -> float | None:
        if not self.ppda_defensive_actions:
            return None
        return round(self.ppda_opponent_passes / self.ppda_defensive_actions, 1)


EventMetrics.model_rebuild()
