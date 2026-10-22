"""Focus-metric alerts: when a viewer picks one metric to follow, flag each
meaningful move of it as a `metric_alert` card.

Steps that count as meaningful:
- pressure index moves by 15 or more,
- xG rises by 0.1 or more,
- a completed pass rated 75+ for difficulty,
- a new top speed,
- momentum moves by 25 or more.
The subject is the focus player when set, else the favourite club, else both
clubs; `club_heart.METRIC_POLICY` says which metrics follow only the fan's club
and which template family voices a move towards the rival (momentum is one
shared number, so a swing to the rival is worded as a warning). Baselines are
per viewer and per subject, so changing the focus starts fresh instead of
comparing against another player's numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from matchmind.crew import club_heart
from matchmind.crew.contracts import FactValue, Moment, MomentKind, ViewerProfile
from matchmind.crew.producer import ViewerState
from matchmind.crew.spotter import DIFFICULTY_SCALE, HARD_PASS_DIFFICULTY, _elapsed, r1, r2, surname
from matchmind.schema import Event, EventType, Outcome
from matchmind.simulator.teams import Team
from matchmind.stats.models import EventMetrics, MatchStateSnapshot, PlayerStats

PRESSURE_STEP = 15.0
XG_STEP = 0.1
MOMENTUM_STEP = 25.0
TOP_SPEED_STEP = 0.1
ALERT_GAP_S = 20.0

KIND_BY_METRIC: dict[str, MomentKind] = {
    "pressure": MomentKind.PRESSURE_SPELL,
    "xg": MomentKind.BIG_CHANCE,
    "pass_difficulty": MomentKind.HARD_PASS,
    "top_speed": MomentKind.SPEED_BURST,
    "momentum": MomentKind.MOMENTUM_SWING,
}


@dataclass
class Alert:
    metric: str
    moment: Moment
    template: str = ""  # family in the packs' `metric` section; defaults to `metric`

    def __post_init__(self) -> None:
        if not self.template:
            self.template = self.metric


class AlertWatcher:
    def __init__(self, teams: dict[str, Team]) -> None:
        self.teams = teams
        self.names: dict[str, str] = {p.player_id: p.name for t in teams.values() for p in t.players}

    def _team_name(self, team_id: str) -> str:
        team = self.teams.get(team_id)
        return team.name if team else team_id

    def _moment(
        self,
        metric: str,
        event: Event,
        facts: dict[str, FactValue],
        team: str | None,
        player_ids: list[str],
        suffix: str,
        priority: int = 50,
    ) -> Moment:
        facts = {"match_clock": event.match_clock, "metric": metric, **facts}
        return Moment(
            moment_id=f"metric-{metric}{suffix}-{event.event_id}",
            kind=KIND_BY_METRIC[metric],
            clock_s=event.clock_s,
            match_clock=event.match_clock,
            period=event.period,
            team=team,
            player_ids=player_ids,
            facts=facts,
            source_event_ids=[event.event_id],
            priority=priority,
        )

    def _teams_in_scope(self, snapshot: MatchStateSnapshot, profile: ViewerProfile) -> list[str]:
        rule = club_heart.METRIC_RULES[profile.focus_metric or "pressure"]
        if rule.scope == "own_only" and profile.favourite_team in (snapshot.home_id, snapshot.away_id):
            return [profile.favourite_team]  # type: ignore[list-item]
        return [snapshot.home_id, snapshot.away_id]

    def _gate(self, state: ViewerState, key: str, event: Event) -> bool:
        """Rate limit: one alert per subject per 20 s of match clock."""
        now = _elapsed(event.period, event.clock_s)
        last = state.last_metric_alert.get(key)
        if last is not None and 0 <= now - _elapsed(*last) < ALERT_GAP_S:
            return False
        state.last_metric_alert[key] = (event.period, event.clock_s)
        return True

    def watch(
        self,
        event: Event,
        metrics: EventMetrics,
        snapshot: MatchStateSnapshot,
        players: dict[str, PlayerStats],
        profile: ViewerProfile,
        state: ViewerState,
    ) -> list[Alert]:
        metric = profile.focus_metric
        if metric is None:
            return []
        handler = getattr(self, f"_{metric}")
        return [
            Alert(metric, m, club_heart.metric_template(metric, m.team, profile.favourite_team))
            for m in handler(event, metrics, snapshot, players, profile, state)
        ]

    # ------------------------------------------------------------ metrics

    def _step(self, state: ViewerState, key: str, value: float, step: float, rising_only: bool = False):
        base = state.metric_baseline.get(key)
        if base is None:
            state.metric_baseline[key] = value
            return None
        change = value - base
        moved = change >= step - 1e-9 if rising_only else abs(change) >= step - 1e-9
        if not moved:
            return None
        state.metric_baseline[key] = value
        return change

    def _pressure(self, event, metrics, snapshot, players, profile, state) -> list[Moment]:
        out = []
        for team_id in self._teams_in_scope(snapshot, profile):
            window = snapshot.home if team_id == snapshot.home_id else snapshot.away
            key = f"pressure:{team_id}"
            change = self._step(state, key, window.pressure_index, PRESSURE_STEP)
            if change is None or not self._gate(state, key, event):
                continue
            facts: dict[str, FactValue] = {
                "team": self._team_name(team_id),
                "pressure_index": int(round(window.pressure_index)),
                "change": int(round(abs(change))),
            }
            out.append(self._moment("pressure", event, facts, team_id, [], f"-{team_id}"))
        return out

    def _xg(self, event, metrics, snapshot, players, profile, state) -> list[Moment]:
        pid = profile.focus_player_id
        if pid:
            ps = players.get(pid)
            if ps is None or pid not in self.names:
                return []
            subjects = [(f"xg:{pid}", ps.xg, self.names[pid], ps.team, [pid])]
        else:
            subjects = []
            for team_id in self._teams_in_scope(snapshot, profile):
                xg = snapshot.xg_home if team_id == snapshot.home_id else snapshot.xg_away
                subjects.append((f"xg:{team_id}", xg, self._team_name(team_id), team_id, []))
        out = []
        for key, value, name, team_id, ids in subjects:
            change = self._step(state, key, r2(value), XG_STEP, rising_only=True)
            if change is None or not self._gate(state, key, event):
                continue
            facts: dict[str, FactValue] = {"subject": name, "xg": r2(value), "change": r2(change)}
            out.append(self._moment("xg", event, facts, team_id, ids, f"-{key.split(':')[1]}"))
        return out

    def _pass_difficulty(
        self, event, metrics: EventMetrics, snapshot, players, profile, state
    ) -> list[Moment]:
        if (
            event.type != EventType.PASS
            or event.outcome != Outcome.COMPLETE
            or (metrics.pass_difficulty or 0) < HARD_PASS_DIFFICULTY
            or not event.player_id
            or event.player_id not in self.names
        ):
            return []
        if profile.focus_player_id and event.player_id != profile.focus_player_id:
            return []
        if not profile.focus_player_id and event.team not in self._teams_in_scope(snapshot, profile):
            return []
        key = f"pass_difficulty:{event.player_id}"
        if not self._gate(state, key, event):
            return []
        name = self.names[event.player_id]
        facts: dict[str, FactValue] = {
            "player": name,
            "player_short": surname(name),
            "pass_difficulty": int(metrics.pass_difficulty or 0),
            "difficulty_scale": DIFFICULTY_SCALE,
        }
        return [self._moment("pass_difficulty", event, facts, event.team, [event.player_id], "")]

    def _top_speed(
        self, event, metrics, snapshot, players: dict[str, PlayerStats], profile, state
    ) -> list[Moment]:
        pid = profile.focus_player_id
        if pid:
            pool = [players[pid]] if pid in players else []
            key = f"top_speed:{pid}"
        else:
            scope = set(self._teams_in_scope(snapshot, profile))
            pool = [p for p in players.values() if p.team in scope]
            key = "top_speed:" + "+".join(sorted(scope))
        pool = [p for p in pool if p.player_id in self.names and p.top_speed_kmh > 0]
        if not pool:
            return []
        best = max(pool, key=lambda p: (p.top_speed_kmh, p.player_id))
        change = self._step(state, key, r1(best.top_speed_kmh), TOP_SPEED_STEP, rising_only=True)
        if change is None or not self._gate(state, key, event):
            return []
        facts: dict[str, FactValue] = {
            "subject": self.names[best.player_id],
            "top_speed_kmh": r1(best.top_speed_kmh),
        }
        return [self._moment("top_speed", event, facts, best.team, [best.player_id], "")]

    def _momentum(
        self, event, metrics, snapshot: MatchStateSnapshot, players, profile, state
    ) -> list[Moment]:
        key = "momentum"
        change = self._step(state, key, snapshot.momentum, MOMENTUM_STEP)
        if change is None or not self._gate(state, key, event):
            return []
        team_id = snapshot.home_id if change > 0 else snapshot.away_id
        facts: dict[str, FactValue] = {"team": self._team_name(team_id), "change": int(round(abs(change)))}
        return [self._moment("momentum", event, facts, team_id, [], "")]
