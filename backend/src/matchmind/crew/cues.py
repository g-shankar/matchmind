"""The cue sheet: PitchPulse's overlay output contract (docs/CUE-SHEET.md).

A cue sheet is an ordered, append-only list of `Cue`s for one audience (persona
and language): every overlay the producer puts on air, timed in match-clock
terms, plus the lifecycle operations a third-party renderer needs:

- `show`      put something on a layer (a card, a scorebug, a telestration);
- `update`    change a state layer in place (scorebug, momentum ribbon);
- `retract`   take earlier cues down because they no longer hold (a goal VAR
              ruled out); `retracts` names them;
- `supersede` show a cue that replaces earlier ones (the "Goal ruled out by
              VAR" card); `supersedes` names them;
- `clear`     empty the transient layers (half-time, full time).

`CueCompiler` turns the producer's per-viewer cards (plus the moments behind
them and the stats engine's momentum) into cues. It is deterministic: the same
events and profile always give the same cues, ids and sequence numbers. Feeding
the same event twice adds nothing, and a moment that a correction has already
ruled out never goes on air, even if its card arrives late.

Every number in a cue comes from the stats engine or the crew's fact-checked
cards; this module never computes match statistics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from matchmind.crew.contracts import (
    Claim,
    Evidence,
    Language,
    MomentBundle,
    MomentKind,
    OverlayCard,
    Persona,
    ViewerProfile,
)
from matchmind.simulator.script import format_clock

CUE_SCHEMA_VERSION = "1.0"
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
RIBBON_EVERY_S = 60.0  # one momentum-ribbon update per minute of play
MAX_QUEUE_S = 8.0  # a cue never waits longer than this for a busy layer; it is dropped instead
MAX_SHEET_CUES = 5000  # hard bound per sheet; past it only priority >= 80 cues and lifecycle ops are added

CueOp = Literal["show", "update", "retract", "supersede", "clear"]
Layer = Literal[
    "lower_third",
    "side_panel",
    "pitch_tag",
    "metric_alert",
    "full_screen",
    "scorebug",
    "momentum_ribbon",
    "telestration",
]
LAYERS: tuple[Layer, ...] = (
    "lower_third",
    "side_panel",
    "pitch_tag",
    "metric_alert",
    "full_screen",
    "scorebug",
    "momentum_ribbon",
    "telestration",
)
Collision = Literal["replace", "queue", "stack", "latest"]
RetractReason = Literal["var_offside", "var_handball", "var_foul", "period_end", "full_time"]
ShapeKind = Literal["arrow", "line", "polyline", "circle", "marker"]
ShapeRole = Literal[
    "shooter",
    "shot_taken",
    "pass_on",
    "open_player",
    "defender",
    "keeper",
    "carrier",
    "runner_path",
    "through_ball",
    "target",
]

TRANSIENT_LAYERS: tuple[Layer, ...] = (
    "lower_third",
    "side_panel",
    "pitch_tag",
    "metric_alert",
    "full_screen",
    "telestration",
)


@dataclass(frozen=True)
class LayerPolicy:
    """How many cues a layer holds at once and what a new cue does when it is busy."""

    capacity: int
    collision: Collision
    description: str


LAYER_POLICY: dict[Layer, LayerPolicy] = {
    "full_screen": LayerPolicy(
        1,
        "replace",
        "One at a time. An equal or higher priority cue replaces what is on; a lower one "
        "queues behind it (at most 8 s) or is dropped.",
    ),
    "lower_third": LayerPolicy(
        1,
        "queue",
        "One at a time. A new cue waits until the current one ends (at most 8 s); a higher "
        "priority one replaces it.",
    ),
    "side_panel": LayerPolicy(2, "stack", "Up to two, newest on top; a third pushes the oldest off."),
    "pitch_tag": LayerPolicy(3, "stack", "Up to three tags on the pitch; the oldest leaves first."),
    "metric_alert": LayerPolicy(3, "stack", "A ticker of up to three alerts; the oldest leaves first."),
    "telestration": LayerPolicy(
        1, "replace", "One drawing at a time, on air exactly as long as the card it belongs to."
    ),
    "scorebug": LayerPolicy(1, "latest", "A state layer: the newest update is the score."),
    "momentum_ribbon": LayerPolicy(1, "latest", "A state layer: the newest update is the momentum."),
}


# --------------------------------------------------------------------------- model


class CueTime(BaseModel):
    """One instant, in the engine's period-aware match clock."""

    model_config = ConfigDict(extra="forbid")

    period: int = Field(ge=1, le=2)
    clock_s: float = Field(
        ge=0,
        description="Engine match clock in seconds. Period 2 starts at 2700; first-half stoppage "
        "time runs past 2700 while period is still 1, so read it with `period`.",
    )
    match_clock: str = Field(description="Broadcast clock, e.g. '67:30' or '45+1:30'.")
    t_s: float = Field(
        ge=0,
        description="Seconds of play since kick-off with the halves joined end to end (no "
        "half-time break). Always increases, so renderers can sort and time cues by it.",
    )


class CueText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    body: str = ""
    why: str = ""
    text_language: Language = Field(description="Language the text is really in.")
    claims: list[Claim] = Field(
        default_factory=list,
        description="Each sentence tied to its facts and source events, as on the card (docs/TRUST.md).",
    )


class Scorebug(BaseModel):
    model_config = ConfigDict(extra="forbid")

    home_id: str
    away_id: str
    score_home: int = Field(ge=0)
    score_away: int = Field(ge=0)


class Ribbon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    momentum: float = Field(ge=-100, le=100, description="+ = home on top (stats engine).")
    pressure_home: float = Field(ge=0, le=100)
    pressure_away: float = Field(ge=0, le=100)


class XYm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=PITCH_LENGTH_M)
    y: float = Field(ge=0, le=PITCH_WIDTH_M)


class Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ShapeKind
    role: ShapeRole
    points: list[XYm] = Field(min_length=1)
    radius_m: float | None = Field(default=None, ge=0, description="circle only")
    dashed: bool = False


class Telestration(BaseModel):
    """Drawing for a replay, in pitch metres: 105 x 68, home attacks towards x = 105."""

    model_config = ConfigDict(extra="forbid")

    frame: Literal["pitch_105x68"] = "pitch_105x68"
    shapes: list[Shape]


class Cue(BaseModel):
    """One line of the cue sheet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = CUE_SCHEMA_VERSION
    cue_id: str = Field(description="Stable id: the same cue has the same id on every compile.")
    seq: int = Field(ge=1, description="Position in this sheet; strictly increasing.")
    op: CueOp
    layer: Layer | Literal["all"] = Field(description="'all' only for op clear (see `clears`).")
    moment_id: str | None = None
    kind: MomentKind | None = None
    retracts: list[str] = Field(default_factory=list, description="op retract: cue ids taken down.")
    supersedes: list[str] = Field(
        default_factory=list, description="op supersede: cue ids this cue replaces."
    )
    clears: list[Layer] = Field(default_factory=list, description="op clear: layers emptied.")
    reason: RetractReason | None = Field(default=None, description="Why cues are retracted or cleared.")
    start: CueTime
    duration_s: float | None = Field(
        default=None, ge=0, description="None: stays until updated, retracted or cleared."
    )
    end: CueTime | None = None
    priority: int = Field(ge=0, le=100)
    collision: Collision
    persona: Persona
    language: Language
    rtl: bool = False
    text: CueText | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)
    team: str | None = None
    player_ids: list[str] = Field(default_factory=list)
    produced_by: Literal["ai", "template"] | None = None
    scorebug: Scorebug | None = None
    ribbon: Ribbon | None = None
    telestration: Telestration | None = None


def cue_json_schema() -> dict:
    """The published JSON Schema for one cue (backend/schema/cue.schema.json)."""
    schema = Cue.model_json_schema()
    schema["$id"] = "urn:pitchpulse:cue:1.0"
    schema["title"] = "PitchPulse cue"
    return schema


def cue_schema_text() -> str:
    return json.dumps(cue_json_schema(), indent=2, ensure_ascii=False) + "\n"


# ------------------------------------------------------------------------ compile


@dataclass(frozen=True)
class RibbonSample:
    momentum: float
    pressure_home: float
    pressure_away: float


@dataclass
class _OnAir:
    cue_id: str
    priority: int
    end_t: float  # inf for state layers


@dataclass
class CueCompiler:
    """Compiles one audience's cue sheet, event by event. Small state, cheap to fork."""

    match_id: str
    home_id: str
    away_id: str
    persona: Persona
    language: Language
    sheet_id: str
    seq: int = 0
    last_index: int = -1
    count: int = 0
    _on_air: dict[str, list[_OnAir]] = field(default_factory=dict)
    _by_moment: dict[str, list[str]] = field(default_factory=dict)  # moment id -> cue ids
    _meta: dict[str, tuple[Layer, MomentKind | None]] = field(default_factory=dict)  # cue id -> layer, kind
    _retracted: set[str] = field(default_factory=set)  # cue ids taken down
    _ruled_out: set[str] = field(default_factory=set)  # moment ids a correction ruled out
    _ribbon_bucket: int = -1
    _scorebug_on: bool = False
    _ribbon_on: bool = False
    _period_ended: set[int] = field(default_factory=set)

    @classmethod
    def for_profile(cls, match_id: str, home_id: str, away_id: str, profile: ViewerProfile) -> CueCompiler:
        return cls(
            match_id=match_id,
            home_id=home_id,
            away_id=away_id,
            persona=profile.persona,
            language=profile.language,
            sheet_id=sheet_id(match_id, profile),
        )

    def fork(self) -> CueCompiler:
        """An independent copy (for a new viewer starting from a compiled position)."""
        return CueCompiler(
            match_id=self.match_id,
            home_id=self.home_id,
            away_id=self.away_id,
            persona=self.persona,
            language=self.language,
            sheet_id=self.sheet_id,
            seq=self.seq,
            last_index=self.last_index,
            count=self.count,
            _on_air={k: list(v) for k, v in self._on_air.items()},
            _by_moment={k: list(v) for k, v in self._by_moment.items()},
            _meta=dict(self._meta),
            _retracted=set(self._retracted),
            _ruled_out=set(self._ruled_out),
            _ribbon_bucket=self._ribbon_bucket,
            _scorebug_on=self._scorebug_on,
            _ribbon_on=self._ribbon_on,
            _period_ended=set(self._period_ended),
        )

    # ------------------------------------------------------------------ feeding

    def feed(
        self,
        index: int,
        at: CueTime,
        event_type: str,
        bundles: list[MomentBundle],
        cards: list[OverlayCard],
        sample: RibbonSample | None = None,
    ) -> list[Cue]:
        """Cues for one played event: `index` is its position in the match, `at`
        its time, `bundles` the moments spotted on it and `cards` the producer's
        selection for this viewer. Feeding an index again (a retry, a duplicate
        delivery, a replay of an older event) returns nothing new."""
        if index <= self.last_index:
            return []
        self.last_index = index
        out: list[Cue] = []
        if event_type in ("period_end", "match_end") and at.period not in self._period_ended:
            self._period_ended.add(at.period)
            reason: RetractReason = "full_time" if event_type == "match_end" else "period_end"
            out.append(self._clear(at, reason, bundles))

        # Corrections first, so nothing they rule out goes on air in the same tick.
        for bundle in bundles:
            for target in bundle.moment.retracts:
                out += self._retract_moment(target, at, bundle)
        moments = {b.moment.moment_id: b for b in bundles}
        for card in cards:
            if card.moment_id in self._ruled_out or card.moment_id in self._by_moment:
                continue
            bundle = moments.get(card.moment_id)
            out += self._show_card(card, at, bundle)
        for bundle in bundles:
            out += self._scorebug(bundle, at)
        if sample is not None:
            out += self._ribbon(sample, at)
        return out

    # ------------------------------------------------------------------- helpers

    def _remember(self, moment_id: str, cue_id: str, layer: Layer, kind: MomentKind | None) -> None:
        self._by_moment.setdefault(moment_id, []).append(cue_id)
        self._meta[cue_id] = (layer, kind)

    def _next(self, **fields) -> Cue | None:
        essential = fields.get("op") in ("retract", "supersede", "clear") or fields.get("priority", 0) >= 80
        if self.count >= MAX_SHEET_CUES and not essential:
            return None
        self.seq += 1
        self.count += 1
        return Cue(seq=self.seq, persona=self.persona, language=self.language, **fields)

    def _end(self, start: CueTime, duration: float) -> CueTime:
        clock = round(start.clock_s + duration, 2)
        return CueTime(
            period=start.period,
            clock_s=clock,
            match_clock=format_clock(clock, start.period),
            t_s=round(start.t_s + duration, 2),
        )

    def _shift(self, start: CueTime, to_t: float) -> CueTime:
        return self._end(start, to_t - start.t_s)

    def _place(self, layer: Layer, cue_id: str, priority: int, start: CueTime, duration: float):
        """Resolve a layer collision. Returns (start, collision) or None when dropped."""
        policy = LAYER_POLICY[layer]
        live = [
            a for a in self._on_air.get(layer, []) if a.end_t > start.t_s and a.cue_id not in self._retracted
        ]
        collision = policy.collision
        if len(live) >= policy.capacity:
            if policy.collision == "stack":
                live = live[1:]  # the oldest leaves first
            else:
                top = max(live, key=lambda a: a.priority)
                if priority >= top.priority:
                    collision = "replace"
                    live = []
                else:
                    wait = min(a.end_t for a in live) - start.t_s
                    if wait > MAX_QUEUE_S:
                        return None
                    start = self._shift(start, start.t_s + wait)
                    collision = "queue"
                    live = []
        live.append(_OnAir(cue_id, priority, start.t_s + duration))
        self._on_air[layer] = live
        return start, collision

    def _show_card(self, card: OverlayCard, at: CueTime, bundle: MomentBundle | None) -> list[Cue]:
        layer: Layer = card.slot
        cue_id = f"{card.moment_id}@{layer}"
        placed = self._place(layer, cue_id, card.priority, at, card.duration_s)
        if placed is None:
            return []
        start, collision = placed
        supersedes = [c for mid in card.retracts for c in self._by_moment.get(mid, [])]
        cue = self._next(
            cue_id=cue_id,
            op="supersede" if card.retracts else "show",
            layer=layer,
            moment_id=card.moment_id,
            kind=card.kind,
            supersedes=supersedes,
            reason=_reason(bundle) if card.retracts else None,
            start=start,
            duration_s=card.duration_s,
            end=self._end(start, card.duration_s),
            priority=card.priority,
            collision=collision,
            rtl=card.rtl,
            text=CueText(
                headline=card.headline,
                body=card.body,
                why=card.why,
                text_language=card.text_language or card.language,
                claims=list(card.claims),
            ),
            evidence=card.evidence,
            source_event_ids=list(bundle.moment.source_event_ids) if bundle else [],
            team=card.team,
            player_ids=list(card.player_ids),
            produced_by=card.produced_by,
        )
        if cue is None:
            return []
        self._remember(card.moment_id, cue_id, layer, card.kind)
        out = [cue]
        drawing = telestration(card.replay, card.team, self.home_id)
        if drawing is not None:
            t_id = f"{card.moment_id}@telestration"
            self._place("telestration", t_id, card.priority, start, card.duration_s)
            t_cue = self._next(
                cue_id=t_id,
                op="show",
                layer="telestration",
                moment_id=card.moment_id,
                kind=card.kind,
                start=start,
                duration_s=card.duration_s,
                end=self._end(start, card.duration_s),
                priority=card.priority,
                collision="replace",
                rtl=card.rtl,
                source_event_ids=cue.source_event_ids,
                team=card.team,
                player_ids=list(card.player_ids),
                telestration=drawing,
            )
            if t_cue is not None:
                self._remember(card.moment_id, t_id, "telestration", card.kind)
                out.append(t_cue)
        return out

    def _retract_moment(self, moment_id: str, at: CueTime, bundle: MomentBundle) -> list[Cue]:
        if moment_id in self._ruled_out:
            return []
        self._ruled_out.add(moment_id)
        out: list[Cue] = []
        for target in self._by_moment.get(moment_id, []):
            if target in self._retracted:
                continue
            self._retracted.add(target)
            layer, kind = self._meta[target]
            cue = self._next(
                cue_id=f"retract:{target}",
                op="retract",
                layer=layer,
                moment_id=moment_id,
                kind=kind,
                retracts=[target],
                reason=_reason(bundle),
                start=at,
                duration_s=0.0,
                end=at,
                priority=100,
                collision="replace",
                source_event_ids=list(bundle.moment.source_event_ids),
                team=bundle.moment.team,
                player_ids=list(bundle.moment.player_ids),
            )
            if cue is not None:
                out.append(cue)
        return out

    def _scorebug(self, bundle: MomentBundle, at: CueTime) -> list[Cue]:
        m = bundle.moment
        if m.moment_id in self._ruled_out:
            return []
        kick_off = m.kind == MomentKind.MILESTONE and m.facts.get("phase") == "kick_off"
        scored = m.kind in (MomentKind.GOAL, MomentKind.CORRECTION)
        if not (kick_off or scored):
            return []
        home, away = (0, 0) if kick_off else (m.facts.get("score_home"), m.facts.get("score_away"))
        if not isinstance(home, int) or not isinstance(away, int):
            return []
        cue_id = f"scorebug@{m.moment_id}"
        supersedes: list[str] = []
        if m.kind == MomentKind.CORRECTION:
            supersedes = [f"scorebug@{mid}" for mid in m.retracts]
        cue = self._next(
            cue_id=cue_id,
            op="update" if self._scorebug_on else "show",
            layer="scorebug",
            moment_id=m.moment_id,
            kind=m.kind,
            supersedes=supersedes,
            reason=_reason(bundle) if m.kind == MomentKind.CORRECTION else None,
            start=at,
            priority=100,
            collision="latest",
            source_event_ids=list(m.source_event_ids),
            team=m.team,
            scorebug=Scorebug(home_id=self.home_id, away_id=self.away_id, score_home=home, score_away=away),
        )
        if cue is None:
            return []
        self._scorebug_on = True
        self._remember(m.moment_id, cue_id, "scorebug", m.kind)
        return [cue]

    def _ribbon(self, sample: RibbonSample, at: CueTime) -> list[Cue]:
        bucket = int(at.t_s // RIBBON_EVERY_S)
        if bucket <= self._ribbon_bucket:
            return []
        self._ribbon_bucket = bucket
        cue = self._next(
            cue_id=f"ribbon@{bucket}",
            op="update" if self._ribbon_on else "show",
            layer="momentum_ribbon",
            start=at,
            priority=10,
            collision="latest",
            ribbon=Ribbon(
                momentum=max(-100.0, min(100.0, sample.momentum)),
                pressure_home=sample.pressure_home,
                pressure_away=sample.pressure_away,
            ),
        )
        if cue is None:
            return []
        self._ribbon_on = True
        return [cue]

    def _clear(self, at: CueTime, reason: RetractReason, bundles: list[MomentBundle]) -> Cue:
        for layer in TRANSIENT_LAYERS:
            self._on_air[layer] = []
        cue = self._next(
            cue_id=f"clear@{at.period}:{reason}",
            op="clear",
            layer="all",
            clears=list(TRANSIENT_LAYERS),
            reason=reason,
            start=at,
            duration_s=0.0,
            end=at,
            priority=100,
            collision="replace",
        )
        assert cue is not None  # lifecycle ops are never dropped
        return cue


def sheet_id(match_id: str, profile: ViewerProfile) -> str:
    """Names one audience's sheet. Club, focus player and focus metric change
    what a viewer sees, so they are part of the id when set."""
    parts = [match_id, profile.persona, profile.language]
    extras = [
        f"club={profile.favourite_team}" if profile.favourite_team else "",
        f"focus={profile.focus_player_id}" if profile.focus_player_id else "",
        f"metric={profile.focus_metric}" if profile.focus_metric else "",
    ]
    return "/".join(parts + [e for e in extras if e])


def _reason(bundle: MomentBundle | None) -> RetractReason | None:
    if bundle is None or bundle.moment.kind != MomentKind.CORRECTION:
        return None
    reason = str(bundle.moment.facts.get("reason", "offside"))
    return {"offside": "var_offside", "handball": "var_handball", "foul": "var_foul"}.get(
        reason, "var_offside"
    )


def active_cues(cues: list[Cue], now_t: float) -> list[Cue]:
    """What is on air at `now_t` after applying every op in order: cues still in
    their window that nothing retracted, superseded or cleared, plus the latest
    state of each state layer. Bounded by the layer capacities."""
    on: dict[str, Cue] = {}
    for cue in cues:
        if cue.start.t_s > now_t:
            continue  # not on yet (a queued cue can start after later-numbered ones)
        if cue.op == "clear":
            for cid in [cid for cid, c in on.items() if c.layer in cue.clears]:
                del on[cid]
            continue
        for cid in [*cue.retracts, *cue.supersedes]:
            on.pop(cid, None)
        if cue.op == "retract":
            continue
        if LAYER_POLICY[cue.layer].collision == "latest":  # type: ignore[index]
            for cid in [cid for cid, c in on.items() if c.layer == cue.layer]:
                del on[cid]
        on[cue.cue_id] = cue
    live = [c for c in on.values() if c.end is None or c.end.t_s > now_t]
    out: list[Cue] = []
    for layer in LAYERS:
        mine = [c for c in live if c.layer == layer]
        out += mine[-LAYER_POLICY[layer].capacity :]
    return sorted(out, key=lambda c: c.seq)


# ------------------------------------------------------------------- telestration


def _pt(p: dict | None) -> XYm | None:
    if not isinstance(p, dict) or "x" not in p or "y" not in p:
        return None
    try:
        x = min(PITCH_LENGTH_M, max(0.0, float(p["x"])))
        y = min(PITCH_WIDTH_M, max(0.0, float(p["y"])))
    except (TypeError, ValueError):
        return None
    return XYm(x=round(x, 2), y=round(y, 2))


def telestration(replay: dict | None, team: str | None, home_id: str) -> Telestration | None:
    """Pitch drawing for a "Should he have passed?" replay (BetterOption) or an
    unfound run (UnfoundRun). Geometry comes straight from the stats engine."""
    if not replay:
        return None
    shapes: list[Shape] = []
    if "shot_event_id" in replay:
        shooter, mate = _pt(replay.get("shooter_pos")), _pt(replay.get("teammate_pos"))
        if shooter is None or mate is None:
            return None
        goal = XYm(x=PITCH_LENGTH_M if team == home_id else 0.0, y=PITCH_WIDTH_M / 2)
        shapes += [
            Shape(kind="marker", role="shooter", points=[shooter]),
            Shape(kind="arrow", role="shot_taken", points=[shooter, goal], dashed=True),
            Shape(kind="arrow", role="pass_on", points=[shooter, mate]),
            Shape(
                kind="circle",
                role="open_player",
                points=[mate],
                radius_m=round(float(replay.get("nearest_marker_m") or 0.0), 1),
            ),
        ]
        for d in replay.get("defenders") or []:
            if (p := _pt(d)) is not None:
                shapes.append(Shape(kind="marker", role="defender", points=[p]))
        if (k := _pt(replay.get("keeper"))) is not None:
            shapes.append(Shape(kind="marker", role="keeper", points=[k]))
    elif "run_event_id" in replay:
        carrier, target = _pt(replay.get("carrier_pos")), _pt(replay.get("target"))
        path = [p for p in (_pt(q) for q in replay.get("runner_path") or []) if p is not None]
        if carrier is None or target is None or not path:
            return None
        shapes += [
            Shape(kind="marker", role="carrier", points=[carrier]),
            Shape(kind="polyline", role="runner_path", points=path),
            Shape(kind="arrow", role="through_ball", points=[carrier, target], dashed=True),
            Shape(kind="marker", role="target", points=[target]),
        ]
        for d in replay.get("defenders_at_pass") or []:
            if (p := _pt(d)) is not None:
                shapes.append(Shape(kind="marker", role="defender", points=[p]))
    else:
        return None
    return Telestration(shapes=shapes)


if __name__ == "__main__":  # python -m matchmind.crew.cues > schema/cue.schema.json
    import sys

    sys.stdout.write(cue_schema_text())
