"""Club heart: how a fan of one club watches differently from a neutral.

When a viewer sets `favourite_team`, every moment about a club is either the
viewer's own club ("own") or the other side ("rival"). `POLICY` below is the
single source of truth for what changes:

- selection: shown or dropped for that viewer (the producer's `wanted`);
- priority: added to the moment's priority (the producer's `card_priority`);
- framing: which studio template family voices it (the commentator), keyed
  into each language pack's `heart` section.

The facts never change: framing only picks other words around the same
numbers, and every framed template goes through the same fact-checker.
Moments with no club (kick-off, half-time, full-time) are never dropped or
re-prioritised; only full-time gets a framing (won, lost or drawn).

`policy_markdown()` writes the table in docs/PERSONALISATION.md; a test keeps
the doc and this module in step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from matchmind.crew.contracts import FactValue, Moment, MomentKind

Side = Literal["own", "rival"]

OWN_BOOST = 15
LATE_GOAL_S = 85 * 60  # a goal from 85:00 on leaves little time to respond


@dataclass(frozen=True)
class Treatment:
    show: bool
    boost: int
    frame: str | None  # family in the packs' `heart` section; None keeps the kind's own templates


@dataclass(frozen=True)
class HeartRule:
    kind: MomentKind
    own: Treatment
    rival: Treatment
    note: str


def _own(frame: str | None = None) -> Treatment:
    return Treatment(show=True, boost=OWN_BOOST, frame=frame)


def _rival(frame: str | None = None, boost: int = 0) -> Treatment:
    return Treatment(show=True, boost=boost, frame=frame)


DROP = Treatment(show=False, boost=0, frame=None)

POLICY: tuple[HeartRule, ...] = (
    HeartRule(
        MomentKind.GOAL,
        _own("goal_for"),
        _rival("goal_against"),
        "Own goals celebrated, with level / pull-back / lead variants; goals conceded get a next step "
        "(the score and the clock), or a late-blow line from 85:00 on.",
    ),
    HeartRule(
        MomentKind.CARD,
        _own("card_own"),
        _rival("card_rival"),
        "An own booking asks for discipline; a rival booking is a chance to press the advantage.",
    ),
    HeartRule(
        MomentKind.BIG_CHANCE,
        _own(),
        _rival("let_off"),
        "A rival big chance is shown as danger survived, never celebrated.",
    ),
    HeartRule(
        MomentKind.ROCKET_SHOT,
        _own(),
        _rival("let_off_shot"),
        "A rival rocket that did not go in is a let-off (a rocket that scored is voiced as the goal).",
    ),
    HeartRule(
        MomentKind.BETTER_OPTION,
        _own("lesson_choice"),
        _rival("let_off_choice"),
        "Own 'should he have passed' is framed constructively; the rival's is a let-off.",
    ),
    HeartRule(
        MomentKind.UNFOUND_RUN,
        _own("lesson_run"),
        _rival("let_off_run"),
        "Own unfound run: the run deserved the ball. Rival unfound run: a let-off for the back line.",
    ),
    HeartRule(
        MomentKind.MOMENTUM_SWING,
        _own(),
        _rival("momentum_against", boost=-10),
        "A swing towards the rival is a warning and ranks a little lower than the fan's own moments.",
    ),
    HeartRule(
        MomentKind.PRESSURE_SPELL,
        _own("pressure_for"),
        _rival("hold_firm", boost=-10),
        "Own pressure: turn the screw. Rival pressure: hold firm.",
    ),
    HeartRule(
        MomentKind.KEY_TACKLE,
        _own(),
        _rival("attack_stopped", boost=-10),
        "An own key tackle is shown as it is; a rival's is told as your team's attack being stopped.",
    ),
    HeartRule(MomentKind.SPEED_BURST, _own(), DROP, "Rival speed tags are dropped."),
    HeartRule(MomentKind.DISTANCE_MILESTONE, _own(), DROP, "Rival distance tags are dropped."),
    HeartRule(MomentKind.HARD_PASS, _own(), DROP, "Rival hard-pass tags are dropped."),
    HeartRule(MomentKind.MILESTONE, _own(), DROP, "Rival player milestones are dropped."),
)
RULES: dict[MomentKind, HeartRule] = {rule.kind: rule for rule in POLICY}

# Refinements of a frame from the moment's own facts (score, clock, outcome).
# The commentator tries the specific frame first, then the base frame.
GOAL_FRAMES: dict[str, str] = {
    "goal_for": "Own club scores and was already ahead",
    "goal_for_level": "Own club scores to level the match",
    "goal_for_pull_back": "Own club scores and is still behind",
    "goal_for_lead": "Own club scores from level to lead",
    "goal_against": "Rival scores and the own club is behind",
    "goal_against_level": "Rival scores to level the match",
    "goal_against_lead_cut": "Rival scores and the own club still leads",
    "goal_against_late": "Rival scores from 85:00 on and the own club is behind",
}
NEUTRAL_FRAMES: dict[str, str] = {
    "full_time_won": "Full time, own club won",
    "full_time_lost": "Full time, own club lost",
    "full_time_drawn": "Full time, a draw",
}

# Focus-metric alerts (alerts.py): whose numbers a fan follows, and the
# template family (packs' `metric` section) for each side.
MetricScope = Literal["own_only", "both"]


@dataclass(frozen=True)
class MetricRule:
    metric: str
    scope: MetricScope
    own_template: str
    rival_template: str | None
    note: str


METRIC_POLICY: tuple[MetricRule, ...] = (
    MetricRule("pressure", "own_only", "pressure", None, "Only the fan's club's pressure index."),
    MetricRule("xg", "own_only", "xg", None, "Only the fan's club's xG (or the focus player's)."),
    MetricRule("pass_difficulty", "own_only", "pass_difficulty", None, "Only the fan's club's hard passes."),
    MetricRule("top_speed", "own_only", "top_speed", None, "Only the fan's club's top speed."),
    MetricRule(
        "momentum",
        "both",
        "momentum",
        "momentum_against",
        "Momentum is one number: a move towards the rival is shown as a warning.",
    ),
)
METRIC_RULES: dict[str, MetricRule] = {rule.metric: rule for rule in METRIC_POLICY}


# ------------------------------------------------------------- selection


def side(team: str | None, favourite_team: str | None) -> Side | None:
    """`own` or `rival` for a moment about a club; None without a favourite
    or for a moment with no club. The API only accepts a favourite club that
    plays in the match, so any other club is the rival."""
    if not favourite_team or team is None:
        return None
    return "own" if team == favourite_team else "rival"


def treatment(kind: MomentKind, team: str | None, favourite_team: str | None) -> Treatment | None:
    which = side(team, favourite_team)
    if which is None:
        return None
    rule = RULES[kind]
    return rule.own if which == "own" else rule.rival


def keeps(kind: MomentKind, team: str | None, favourite_team: str | None) -> bool:
    t = treatment(kind, team, favourite_team)
    return t is None or t.show


def boost(kind: MomentKind, team: str | None, favourite_team: str | None) -> int:
    t = treatment(kind, team, favourite_team)
    return 0 if t is None else t.boost


# --------------------------------------------------------------- framing


def _int(facts: dict[str, FactValue], key: str) -> int | None:
    value = facts.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _scores(facts: dict[str, FactValue], favourite_name: str) -> tuple[int, int] | None:
    """(own, rival) goals from the moment's score facts, or None."""
    home, away = _int(facts, "score_home"), _int(facts, "score_away")
    if home is None or away is None:
        return None
    if facts.get("home") == favourite_name:
        return home, away
    if facts.get("away") == favourite_name:
        return away, home
    return None


def _goal_frame(moment: Moment, own_side: bool, favourite_name: str) -> list[str]:
    base = "goal_for" if own_side else "goal_against"
    scores = _scores(moment.facts, favourite_name)
    if scores is None:
        return [base]
    own, rival = scores
    if own_side:
        before = own - 1
        if own == rival:
            return ["goal_for_level", base]
        if own < rival:
            return ["goal_for_pull_back", base]
        if before == rival:
            return ["goal_for_lead", base]
        return [base]
    if own == rival:
        return ["goal_against_level", base]
    if own > rival:
        return ["goal_against_lead_cut", base]
    if moment.clock_s >= LATE_GOAL_S:
        return ["goal_against_late", base]
    return [base]


def frames_for(moment: Moment, favourite_name: str | None) -> list[str]:
    """The heart template families for this moment and fan, most specific
    first; empty when the kind's own templates are used."""
    if not favourite_name:
        return []
    facts = moment.facts
    if favourite_name not in (facts.get("home"), facts.get("away")):
        return []
    team = facts.get("team")
    if not isinstance(team, str) or not team:
        if moment.kind == MomentKind.MILESTONE and facts.get("phase") == "full_time":
            scores = _scores(facts, favourite_name)
            if scores is None:
                return []
            own, rival = scores
            return [
                "full_time_won" if own > rival else "full_time_lost" if own < rival else "full_time_drawn"
            ]
        return []
    own_side = team == favourite_name
    rule = RULES[moment.kind]
    t = rule.own if own_side else rule.rival
    if t.frame is None or not t.show:
        return []
    if moment.kind == MomentKind.GOAL:
        return _goal_frame(moment, own_side, favourite_name)
    if moment.kind == MomentKind.ROCKET_SHOT and facts.get("outcome") == "goal":
        return []
    return [t.frame]


def all_frames() -> list[str]:
    """Every heart template family a pack must define."""
    names: list[str] = []
    for rule in POLICY:
        for t in (rule.own, rule.rival):
            if t.frame and t.frame not in names and not t.frame.startswith("goal_"):
                names.append(t.frame)
    return [*GOAL_FRAMES, *names, *NEUTRAL_FRAMES]


def metric_template(metric: str, team: str | None, favourite_team: str | None) -> str:
    """Template family (packs' `metric` section) for an alert about `team`."""
    rule = METRIC_RULES[metric]
    if side(team, favourite_team) == "rival" and rule.rival_template:
        return rule.rival_template
    return rule.own_template


# ------------------------------------------------------------------ docs


def _cell(t: Treatment) -> tuple[str, str, str]:
    if not t.show:
        return ("dropped", "-", "-")
    sign = f"+{t.boost}" if t.boost > 0 else str(t.boost)
    return ("shown", sign, f"`{t.frame}`" if t.frame else "kind's own wording")


def policy_markdown() -> str:
    """The club-heart tables for docs/PERSONALISATION.md."""
    lines = [
        "| Moment | Own club: shown | priority | framing | Rival: shown | priority | framing | Why |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for rule in POLICY:
        own, rival = _cell(rule.own), _cell(rule.rival)
        lines.append(f"| `{rule.kind.value}` | {' | '.join(own)} | {' | '.join(rival)} | {rule.note} |")
    lines += ["", "| Framing variant | When |", "|---|---|"]
    lines += [f"| `{name}` | {when} |" for name, when in {**GOAL_FRAMES, **NEUTRAL_FRAMES}.items()]
    lines += [
        "",
        "| Focus metric | Whose numbers | Own wording | Rival wording | Why |",
        "|---|---|---|---|---|",
    ]
    for m in METRIC_POLICY:
        scope = "own club only" if m.scope == "own_only" else "both clubs"
        rival = f"`{m.rival_template}`" if m.rival_template else "-"
        lines.append(f"| `{m.metric}` | {scope} | `{m.own_template}` | {rival} | {m.note} |")
    return "\n".join(lines)
