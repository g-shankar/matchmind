"""The fixed set of questions Ask the studio answers, as a closed schema.

Every answer starts from one `Intent`. The rule-based parser produces it; the
optional model path (off by default) may produce only this same JSON, which is
validated here and then answered by the same deterministic code. Nothing a
model writes is ever shown to a viewer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TEAM_ID = r"^[A-Z]{2,5}$"
PLAYER_ID = r"^[A-Z]{2,5}-[0-9]{1,3}$"

IntentKind = Literal[
    "score",
    "scorers",
    "team_stat",
    "top_player",
    "player_stats",
    "control",
    "momentum",
    "better_option",
    "var",
    "cards",
    "explain_metric",
    "window",
]
INTENT_KINDS: tuple[str, ...] = IntentKind.__args__  # type: ignore[attr-defined]

# Team metrics: match totals from the stats engine (GET /api/match/stats/basic) and the
# rolling xG in the match state.
TeamMetric = Literal[
    "xg", "shots", "shots_on_target", "possession", "pass_accuracy", "passes", "tackles", "distance"
]
TEAM_METRICS: tuple[str, ...] = TeamMetric.__args__  # type: ignore[attr-defined]
# Player metrics: PlayerStats fields (distance and top speed estimated from synthetic tracking).
PlayerMetric = Literal[
    "distance",
    "top_speed",
    "passes",
    "tackles",
    "xg",
    "shots",
    "sprints",
    "key_passes",
    "interceptions",
    "touches",
]
PLAYER_METRICS: tuple[str, ...] = PlayerMetric.__args__  # type: ignore[attr-defined]
# Registry metric ids (stats/registry.py) that have a plain-words explanation.
ExplainMetric = Literal[
    "chance_quality",
    "times_better",
    "projected_chance_quality",
    "possession_pct",
    "field_tilt_pct",
    "pressure_index",
    "momentum",
    "control_chaos",
    "pass_difficulty",
    "xt_delta",
    "ppda",
    "distance_km",
    "top_speed_kmh",
    "sprints",
    "pass_accuracy",
    "xa",
]
EXPLAIN_METRICS: tuple[str, ...] = ExplainMetric.__args__  # type: ignore[attr-defined]
SPOILER_INTENTS: frozenset[str] = frozenset({"score", "scorers", "var"})
MAX_MINUTE = 130


class Intent(BaseModel):
    """One question, as data. `metric` must suit `kind`; ids are checked against the
    match's own squads before anything is answered."""

    model_config = ConfigDict(extra="forbid")

    kind: IntentKind
    team: str | None = Field(default=None, pattern=TEAM_ID)
    player_id: str | None = Field(default=None, pattern=PLAYER_ID)
    metric: str | None = Field(default=None, pattern=r"^[a-z_]{2,32}$")
    from_minute: int | None = Field(default=None, ge=0, le=MAX_MINUTE)
    to_minute: int | None = Field(default=None, ge=0, le=MAX_MINUTE)

    @model_validator(mode="after")
    def _consistent(self) -> Intent:
        allowed = {
            "team_stat": TEAM_METRICS,
            "top_player": PLAYER_METRICS,
            "player_stats": PLAYER_METRICS,
            "explain_metric": EXPLAIN_METRICS,
        }.get(self.kind)
        if self.metric is not None and (allowed is None or self.metric not in allowed):
            raise ValueError(f"metric {self.metric!r} does not fit {self.kind}")
        if self.kind in ("team_stat", "top_player", "explain_metric") and self.metric is None:
            raise ValueError(f"{self.kind} needs a metric")
        if self.kind == "player_stats" and self.player_id is None:
            raise ValueError("player_stats needs a player_id")
        if self.kind == "window":
            if self.from_minute is None or self.to_minute is None or self.from_minute >= self.to_minute:
                raise ValueError("window needs from_minute < to_minute")
        elif self.from_minute is not None or self.to_minute is not None:
            raise ValueError("only window takes minutes")
        return self


# Suggested questions (UI chips). A chip sends its id, never text, so it needs no parsing.
ChipId = Literal["score", "top_xg", "furthest", "fastest", "on_top", "better_option", "explain_xg"]
CHIPS: dict[str, Intent] = {
    "score": Intent(kind="score"),
    "top_xg": Intent(kind="top_player", metric="xg"),
    "furthest": Intent(kind="top_player", metric="distance"),
    "fastest": Intent(kind="top_player", metric="top_speed"),
    "on_top": Intent(kind="momentum"),
    "better_option": Intent(kind="better_option"),
    "explain_xg": Intent(kind="explain_metric", metric="chance_quality"),
}
