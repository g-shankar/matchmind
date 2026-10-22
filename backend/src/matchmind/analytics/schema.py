"""Table definitions of the Lakehouse star schema.

One place describes every table and column (name, type, meaning), so the Parquet
writer, the CSV fallback, the `_schema.json` files, the Fabric notebook and the
Eventhouse (KQL) table all agree. Types are neutral names that map onto Parquet,
Spark and KQL: string, int64, float64, bool and timestamp (UTC).
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = "1.0"
DTYPES = ("string", "int64", "float64", "bool", "timestamp")


@dataclass(frozen=True)
class Col:
    name: str
    dtype: str
    desc: str

    def __post_init__(self) -> None:
        if self.dtype not in DTYPES:
            raise ValueError(f"unknown type {self.dtype!r} for column {self.name}")


@dataclass(frozen=True)
class Table:
    name: str
    kind: str  # fact or dim
    desc: str
    key: tuple[str, ...]
    cols: tuple[Col, ...]
    references: dict[str, str] = field(default_factory=dict)  # column -> "table.column"

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.cols]

    def __post_init__(self) -> None:
        names = self.names
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate column in {self.name}")
        missing = [k for k in self.key if k not in names]
        if missing:
            raise ValueError(f"{self.name}: key columns {missing} are not columns")


S, N, F, B, T = "string", "int64", "float64", "bool", "timestamp"

TEAMS = Table(
    "teams",
    "dim",
    "The two fictional clubs.",
    ("team_id",),
    (
        Col("team_id", S, "Club code, e.g. NBR."),
        Col("name", S, "Fictional club name."),
        Col("short_name", S, "Short display name."),
        Col("formation", S, "Formation, e.g. 4-3-3."),
        Col("strength", F, "Simulator strength (0.5 is average)."),
        Col("primary_color", S, "Kit colour, hex."),
        Col("secondary_color", S, "Secondary colour, hex."),
        Col("style", S, "One-line playing style."),
    ),
)

PLAYERS = Table(
    "players",
    "dim",
    "Fictional squads (starting eleven per club).",
    ("player_id",),
    (
        Col("player_id", S, "Player code, e.g. NBR-9."),
        Col("team_id", S, "Club."),
        Col("name", S, "Fictional player name."),
        Col("shirt_number", N, "Shirt number."),
        Col("position", S, "Position, e.g. ST."),
        Col("line", S, "GK, DEF, MID or FWD."),
        Col("base_x", F, "Home position, metres, own attacking frame."),
        Col("base_y", F, "Home position, metres, own attacking frame."),
    ),
    {"team_id": "teams.team_id"},
)

MATCHES = Table(
    "matches",
    "dim",
    "One row per match.",
    ("match_id",),
    (
        Col("match_id", S, "Match id."),
        Col("home_team_id", S, "Home club."),
        Col("away_team_id", S, "Away club."),
        Col("kickoff_utc", T, "Timestamp of the first event (UTC)."),
        Col("seed", N, "Simulator seed (from the match_start event), if recorded."),
        Col(
            "scripted",
            B,
            "True if the match follows a story script; false if the engine's chance model decided.",
        ),
        Col("score_home", N, "Final goals, home."),
        Col("score_away", N, "Final goals, away."),
        Col("xg_home", F, "Final expected goals, home."),
        Col("xg_away", F, "Final expected goals, away."),
        Col("events", N, "Number of events."),
        Col("moments", N, "Number of spotted moments."),
    ),
    {"home_team_id": "teams.team_id", "away_team_id": "teams.team_id"},
)

EVENTS = Table(
    "events",
    "fact",
    "One row per match event, enriched with stats-engine metrics and the running match state.",
    ("match_id", "event_id"),
    (
        Col("match_id", S, "Match id."),
        Col("event_id", S, "Event id."),
        Col("seq", N, "Order within the match."),
        Col("ts", T, "Wall-clock time of the event (UTC)."),
        Col("period", N, "1 or 2."),
        Col("clock_s", F, "Match clock in seconds (period 2 starts at 2700)."),
        Col("match_clock", S, "Broadcast clock, e.g. 67:20 or 90+2:15."),
        Col("minute", N, "Whole match minute (clock_s div 60)."),
        Col("five_min_bucket", N, "Start minute of the five-minute window (0, 5, 10, ...)."),
        Col("type", S, "Event type: pass, shot, carry, ..."),
        Col("team_id", S, "Acting club, if any."),
        Col("opponent_id", S, "The other club."),
        Col("is_home", B, "True if the acting club is the home club."),
        Col("player_id", S, "Acting player."),
        Col("receiver_id", S, "Intended receiver of a pass."),
        Col("possession_id", N, "Possession chain id."),
        Col("start_x", F, "Start x, metres on the 105 x 68 pitch (home attacks towards x = 105)."),
        Col("start_y", F, "Start y, metres."),
        Col("end_x", F, "End x, metres."),
        Col("end_y", F, "End y, metres."),
        Col("att_start_x", F, "Start x in the acting club's attacking frame (always towards 105)."),
        Col("att_start_y", F, "Start y in the acting club's attacking frame."),
        Col("outcome", S, "complete, goal, saved, ..."),
        Col("body_part", S, "Shots: right_foot, left_foot or head."),
        Col("ball_speed_mps", F, "Ball speed, m/s."),
        Col("player_speed_mps", F, "Player speed, m/s."),
        Col("under_pressure", B, "Actor under pressure."),
        Col("pressure_count", N, "Opponents within 3.5 m."),
        Col("pass_type", S, "ground, lofted, cross or through_ball."),
        Col("details_json", S, "Event details as JSON (sorted keys)."),
        Col(
            "truth_labels", S, "Simulator ground-truth labels joined by |. Evaluation only; never a feature."
        ),
        Col("pitch_zone", S, "Defensive Third, Middle Third, Attacking Third or Penalty Box."),
        Col("pass_distance_m", F, "Pass length, metres."),
        Col("pass_difficulty", N, "0-100 pass difficulty (docs/METRICS.md)."),
        Col("progressive", B, "Moves the ball at least 10 m forward and 25% closer to goal."),
        Col("forward_m", F, "Metres gained towards goal."),
        Col("ball_speed_kmh", F, "Ball speed, km/h."),
        Col("player_speed_kmh", F, "Player speed, km/h."),
        Col("sprint", B, "Player faster than 8 m/s."),
        Col("fast_shot", B, "Shot at 100 km/h or more."),
        Col("xg", F, "Shots: expected goals."),
        Col("distance_to_goal_m", F, "Shots: distance to goal centre."),
        Col("xt_delta", F, "Expected threat gained by the move."),
        Col("has_better_option", B, "Shot flagged: a pass was on with a clearly better chance."),
        Col("has_unfound_run", B, "Run flagged: a through ball was on and never came."),
        Col("score_home", N, "Home goals after this event."),
        Col("score_away", N, "Away goals after this event."),
        Col("xg_home", F, "Home cumulative xG after this event."),
        Col("xg_away", F, "Away cumulative xG after this event."),
        Col("shots_home", N, "Home shots after this event."),
        Col("shots_away", N, "Away shots after this event."),
        Col("momentum", F, "-100 to 100, positive means home on top."),
        Col("pressure_home", F, "Home pressure index over the last five minutes (0-100)."),
        Col("pressure_away", F, "Away pressure index over the last five minutes (0-100)."),
        Col("possession_home_pct", F, "Home share of completed passes, last five minutes."),
        Col("control_chaos", F, "-1 chaos to +1 control."),
        Col("tempo", S, "Tempo label."),
    ),
    {"match_id": "matches.match_id", "team_id": "teams.team_id", "player_id": "players.player_id"},
)

MOMENTS = Table(
    "moments",
    "fact",
    "Spotter output: what is worth telling, with the facts that back it.",
    ("match_id", "moment_id"),
    (
        Col("match_id", S, "Match id."),
        Col("moment_id", S, "Moment id."),
        Col("kind", S, "goal, card, big_chance, better_option, unfound_run, ..."),
        Col("event_id", S, "Primary source event."),
        Col("clock_s", F, "Match clock, seconds."),
        Col("match_clock", S, "Broadcast clock."),
        Col("period", N, "1 or 2."),
        Col("team_id", S, "Club the moment is about."),
        Col("player_id", S, "First player involved."),
        Col("priority", N, "0-100 priority."),
        Col("player_ids_json", S, "All players involved, JSON list."),
        Col("source_event_ids_json", S, "All source events, JSON list."),
        Col("facts_json", S, "Facts as JSON (sorted keys). The only numbers any text may use."),
    ),
    {"match_id": "matches.match_id", "event_id": "events.event_id", "team_id": "teams.team_id"},
)

MOMENT_FACTS = Table(
    "moment_facts",
    "fact",
    "The facts of every moment, one row per fact (easier to filter and pivot than JSON).",
    ("match_id", "moment_id", "fact_key"),
    (
        Col("match_id", S, "Match id."),
        Col("moment_id", S, "Moment id."),
        Col("fact_key", S, "Fact name, e.g. shot_xg."),
        Col("value_text", S, "Value as text."),
        Col("value_num", F, "Value if numeric (booleans are 0 or 1), else null."),
    ),
    {"match_id": "matches.match_id", "moment_id": "moments.moment_id"},
)

BETTER_OPTIONS = Table(
    "better_options",
    "fact",
    "Should he have passed? Shots with a clearly better pass on, and runs where the through ball never came.",
    ("match_id", "event_id"),
    (
        Col("match_id", S, "Match id."),
        Col("event_id", S, "The shot or the run."),
        Col("trigger", S, "shot_vs_pass or unfound_run."),
        Col("clock_s", F, "Match clock, seconds."),
        Col("match_clock", S, "Broadcast clock."),
        Col("period", N, "1 or 2."),
        Col("team_id", S, "Club."),
        Col("player_id", S, "Shooter, or the ball carrier for a run."),
        Col("teammate_id", S, "The open teammate, or the runner."),
        Col("shot_xg", F, "Shot trigger: xG of the shot taken."),
        Col("alt_xg", F, "Shot trigger: xG from the teammate's spot."),
        Col("pass_success", F, "Shot trigger: probability the pass arrives."),
        Col("alt_value", F, "Shot trigger: pass_success x alt_xg."),
        Col("times_better", F, "Shot trigger: alt_value / shot_xg."),
        Col("xg_gain", F, "Shot trigger: alt_value - shot_xg."),
        Col("pass_distance_m", F, "Shot trigger: length of the pass that was on."),
        Col("nearest_marker_m", F, "Shot trigger: distance from the teammate to the nearest opponent."),
        Col("pass_on_clock", S, "Run trigger: match clock when the pass was on."),
        Col("pass_on_at_s", F, "Run trigger: seconds into the run."),
        Col("clear_of_line_m", F, "Run trigger: metres beyond the back line."),
        Col("projected_xg", F, "Run trigger: chance quality at the end of the run."),
        Col("one_on_one", B, "Run trigger: no outfield defender between runner and goal."),
        Col("shooter_x", F, "Actor position x (shooter, or carrier), metres."),
        Col("shooter_y", F, "Actor position y."),
        Col("teammate_x", F, "Teammate position x (the run's target for a run)."),
        Col("teammate_y", F, "Teammate position y."),
        Col("keeper_x", F, "Shot trigger: keeper x."),
        Col("keeper_y", F, "Shot trigger: keeper y."),
        Col("defenders_json", S, "Defender positions as JSON [{x, y}]."),
        Col("runner_path_json", S, "Run trigger: runner path as JSON [{x, y}]."),
    ),
    {"match_id": "matches.match_id", "event_id": "events.event_id", "team_id": "teams.team_id"},
)

PLAYER_MATCH = Table(
    "player_match",
    "fact",
    "Per-player aggregates for one match.",
    ("match_id", "player_id"),
    (
        Col("match_id", S, "Match id."),
        Col("player_id", S, "Player."),
        Col("team_id", S, "Club."),
        Col("touches", N, "On-ball actions."),
        Col("passes", N, "Passes attempted."),
        Col("passes_completed", N, "Passes completed."),
        Col("pass_accuracy", F, "Percent of passes completed."),
        Col("key_passes", N, "Passes that led to a shot."),
        Col("shots", N, "Shots."),
        Col("goals", N, "Goals."),
        Col("assists", N, "Assists."),
        Col("xg", F, "Expected goals."),
        Col("xa", F, "Expected assists."),
        Col("tackles_won", N, "Tackles won."),
        Col("interceptions", N, "Interceptions."),
        Col("top_speed_kmh", F, "Top speed, km/h."),
        Col("sprints", N, "Sprints."),
        Col("carry_distance_m", F, "Metres carried."),
        Col("distance_km", F, "Estimated distance covered (a lower bound)."),
        Col("progressive_actions", N, "Progressive passes and carries."),
        Col("avg_pass_difficulty", F, "Mean difficulty of passes attempted."),
        Col("xt_total", F, "Expected threat added by passes and carries."),
        Col("better_option_shots", N, "Shots flagged as 'should have passed'."),
        Col("unfound_runs", N, "Runs made where the through ball never came."),
    ),
    {"match_id": "matches.match_id", "player_id": "players.player_id", "team_id": "teams.team_id"},
)

TEAM_MATCH = Table(
    "team_match",
    "fact",
    "Per-club aggregates for one match.",
    ("match_id", "team_id"),
    (
        Col("match_id", S, "Match id."),
        Col("team_id", S, "Club."),
        Col("opponent_id", S, "Opponent."),
        Col("is_home", B, "Home club."),
        Col("goals", N, "Goals for."),
        Col("goals_against", N, "Goals against."),
        Col("points", N, "3 for a win, 1 for a draw."),
        Col("shots", N, "Shots."),
        Col("xg", F, "Expected goals for."),
        Col("xg_against", F, "Expected goals against."),
        Col("passes", N, "Passes attempted."),
        Col("passes_completed", N, "Passes completed."),
        Col("pass_accuracy", F, "Percent of passes completed."),
        Col("possession_pct", F, "Share of completed passes in the match."),
        Col("progressive_passes", N, "Progressive passes."),
        Col("sprints", N, "Sprints."),
        Col("tackles_won", N, "Tackles won."),
        Col("interceptions", N, "Interceptions."),
        Col("fouls", N, "Fouls committed."),
        Col("yellow_cards", N, "Yellow cards."),
        Col("red_cards", N, "Red cards."),
        Col("peak_pressure_index", F, "Highest five-minute pressure index."),
        Col("avg_pressure_index", F, "Mean five-minute pressure index over the match's events."),
        Col("better_option_shots", N, "Shots flagged as 'should have passed'."),
        Col("moments", N, "Spotted moments about this club."),
    ),
    {"match_id": "matches.match_id", "team_id": "teams.team_id", "opponent_id": "teams.team_id"},
)

DECISION_LABELS = Table(
    "decision_labels",
    "fact",
    "ML training set: one row per shot or pass decision, features from the stats engine, labels below.",
    ("match_id", "event_id"),
    (
        Col("match_id", S, "Match id."),
        Col("event_id", S, "Event id."),
        Col("split", S, "train, val or test, by a hash of match_id so a match never spans splits."),
        Col("decision", S, "shot or pass."),
        Col("team_id", S, "Club."),
        Col("player_id", S, "Actor."),
        Col("clock_s", F, "Match clock, seconds."),
        Col("period", N, "1 or 2."),
        Col("score_diff", N, "Actor's goal difference before the decision."),
        Col("att_start_x", F, "Start x, attacking frame."),
        Col("att_start_y", F, "Start y, attacking frame."),
        Col("pitch_zone", S, "Start zone."),
        Col("under_pressure", B, "Actor under pressure."),
        Col("pressure_count", N, "Opponents within 3.5 m."),
        Col("ball_speed_kmh", F, "Ball speed, km/h."),
        Col("body_part", S, "Shots: body part."),
        Col("pass_type", S, "Passes: ground, lofted, cross or through_ball."),
        Col("pass_distance_m", F, "Passes: length."),
        Col("pass_difficulty", N, "Passes: 0-100 difficulty."),
        Col("forward_m", F, "Passes: metres gained."),
        Col("shot_xg", F, "Shots: xG of the shot taken."),
        Col("distance_to_goal_m", F, "Shots: distance to goal."),
        Col("defenders_near", N, "Shots: outfield opponents within 7 m of the shooter."),
        Col("keeper_distance_m", F, "Shots: distance to the keeper."),
        Col("best_alt_value", F, "Shots: best pass option (success x xG), whatever the threshold."),
        Col("best_alt_nearest_marker_m", F, "Shots: marker distance of the best pass option."),
        Col("label_better_option", B, "Shots: flagged 'should have passed' by the engine's thresholds."),
        Col("label_xg_gain", F, "Shots: max(0, best_alt_value - shot_xg)."),
        Col("label_goal", B, "Shots: scored (false for a goal VAR ruled out)."),
        Col("label_completed", B, "Passes: completed."),
        Col("label_progressive", B, "Passes: progressive."),
        Col("label_leads_to_shot", B, "Passes: same club shoots in the same possession within 15 s."),
        Col("label_next_shot_xg", F, "Passes: xG of that shot (0 if none)."),
    ),
    {"match_id": "matches.match_id", "event_id": "events.event_id", "team_id": "teams.team_id"},
)

STAR_TABLES = (
    TEAMS,
    PLAYERS,
    MATCHES,
    EVENTS,
    MOMENTS,
    MOMENT_FACTS,
    BETTER_OPTIONS,
    PLAYER_MATCH,
    TEAM_MATCH,
)
ALL_TABLES = (*STAR_TABLES, DECISION_LABELS)
BY_NAME = {t.name: t for t in ALL_TABLES}
